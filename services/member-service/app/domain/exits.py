"""Dates of exit and the member's applications (Phase 2, slice 1).

An exit is recorded here, whoever marks it: the member (Manage › Mark Exit, when the employer has not), or the
employer (the employer_exit process: an operator marks it, the signatory approves). Either way this service
publishes MemberExitMarked.v1, so the ledger, the claims projection and the process engine see the same date."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import employments, member_applications, members
from epfo_persistence import add_event

PRODUCER = "member-service"


def month_after(month: str, n: int) -> date:
    y, m = int(month[:4]), int(month[5:7]) - 1 + n
    return date(y + m // 12, m % 12 + 1, 1)


def self_exit_problems(job: dict[str, Any], day: date, today: date) -> list[str]:
    """Why a member may not mark this exit now (empty: they may). Illustrative rules from the portal's notes."""
    if job["date_of_exit"]:
        return ["The date of exit is already marked for this member ID."]
    last = job.get("last_contribution_month")
    if not last:
        return ["No contribution is recorded for this member ID; ask your employer to mark the exit."]
    problems = []
    if today < month_after(last, 3):
        problems.append(f"You can mark the exit two months after the last contribution ({last}), from {month_after(last, 3).isoformat()}.")
    if day.strftime("%Y-%m") != last:
        problems.append(f"The date of exit must be in the month of the last contribution received ({last}).")
    if day < job["date_of_joining"]:
        problems.append("The date of exit cannot be before the date of joining.")
    return problems


async def open_applications(session: AsyncSession, uan: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(member_applications).where(member_applications.c.uan == uan,
                                                                    member_applications.c.terminal.is_(False)))).mappings().all()
    return [dict(r) for r in rows]


async def track(session: AsyncSession, application_id: str, uan: str, process: str, title: str, state: str, terminal: bool,
                account_link_id: str | None = None) -> None:
    now = datetime.now(UTC)
    if (await session.execute(select(member_applications.c.application_id).where(
            member_applications.c.application_id == application_id))).first():
        await session.execute(update(member_applications).where(member_applications.c.application_id == application_id)
                              .values(state=state, terminal=terminal, updated_at=now))
    else:
        await session.execute(insert(member_applications).values(application_id=application_id, uan=uan, process=process, title=title,
                                                                 state=state, terminal=terminal, account_link_id=account_link_id,
                                                                 submitted_at=now, updated_at=now))


async def record_exit(session: AsyncSession, job: dict[str, Any], day: date, reason: str, marked_by: str,
                      correlation_id: str | None, corrects: str | None = None) -> None:
    """marked_by: MEMBER | EMPLOYER | CIVIL_REGISTRY (P2.21b: a death reported by the registry closes the open member IDs)."""
    member = (await session.execute(select(members).where(members.c.member_id == job["member_id"]))).mappings().one()
    await session.execute(update(employments).where(employments.c.account_link_id == job["account_link_id"])
                          .values(date_of_exit=day, exit_reason=reason, exit_marked_by=marked_by))
    await add_event(session, producer=PRODUCER, event_type="MemberExitMarked.v1", aggregate_type="member_account",
                    aggregate_id=job["account_link_id"], correlation_id=correlation_id, payload={
                        "uan": member["uan"], "account_link_id": job["account_link_id"], "date_of_exit": day.isoformat(),
                        "reason": reason, "marked_by": marked_by, **({"corrects": corrects} if corrects else {})})
    if reason == "DEATH_IN_SERVICE" and marked_by != "CIVIL_REGISTRY" and not corrects:
        from app.domain.life_events import announce_death          # the registry's feed announces the death itself
        await announce_death(session, member["uan"], day, marked_by, None, correlation_id)
    if member["subject"] and reason != "DEATH_IN_SERVICE":
        await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=job["account_link_id"], correlation_id=correlation_id, payload={
                            "recipient_subject": member["subject"], "template": "EXIT_CORRECTED" if corrects else "EXIT_RECORDED",
                            "reference_id": job["account_link_id"],
                            "params": {"date_of_exit": day.isoformat(), "marked_by": marked_by.lower()}})


async def on_contribution_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    """A credited return moves the member ID's last contribution month forward."""
    p = event["payload"]
    for link in {x["account_link_id"] for x in p.get("postings", []) if x.get("account_link_id")}:
        job = (await session.execute(select(employments.c.last_contribution_month).where(
            employments.c.account_link_id == link))).scalar_one_or_none()
        if not job or p["wage_month"] > job:
            await session.execute(update(employments).where(employments.c.account_link_id == link)
                                  .values(last_contribution_month=p["wage_month"]))
    await _recompute_for_links(session, {x["account_link_id"] for x in p.get("postings", []) if x.get("account_link_id")}, event)


async def _recompute_for_links(session: AsyncSession, links: set[str], event: dict[str, Any]) -> None:
    """A first contribution to a new member ID makes it primary (P2.7d)."""
    from app.domain.primary import recompute
    uans = set((await session.execute(select(members.c.uan).join(employments, employments.c.member_id == members.c.member_id)
                                      .where(employments.c.account_link_id.in_(links)))).scalars()) if links else set()
    for uan in sorted(uans):
        await recompute(session, uan, event.get("correlation_id"))


async def on_transfer_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(employments).where(employments.c.account_link_id == p["from_account_link_id"])
                          .values(transferred_to=p["to_account_link_id"]))
    await _recompute_for_links(session, {p["from_account_link_id"], p["to_account_link_id"]}, event)
    member = (await session.execute(select(members).where(members.c.uan == p["uan"]))).mappings().first()
    if member and member["subject"]:
        await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=p["transfer_id"], correlation_id=event["correlation_id"], payload={
                            "recipient_subject": member["subject"], "template": "TRANSFER_POSTED", "reference_id": p["transfer_id"],
                            "params": {"amount_paise": int(p["employee_paise"]) + int(p["employer_paise"]),
                                       "from": p["from_account_link_id"], "to": p["to_account_link_id"]}})


async def on_ledger_reversed(session: AsyncSession, event: dict[str, Any]) -> None:
    """A recredited transfer (P2.7b): the previous member ID holds its balance again and is no longer transferred."""
    p = event["payload"]
    if p.get("reversed_kind") != "TRANSFER":
        return
    frm = next((x["account_link_id"] for x in p["postings"] if x.get("account_link_id") and x["side"] == "credit"), None)
    if frm:
        await session.execute(update(employments).where(employments.c.account_link_id == frm).values(transferred_to=None))
        await _recompute_for_links(session, {frm}, event)
