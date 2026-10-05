"""member-service owns the freeze and Joint Declaration contracts; the engine in workflow-service runs the
processes (ADR-0005). On each ProcessTransitioned.v1 this service does what the contract promises:

* member_freeze       records the account state and publishes AccountFrozen.v1 / AccountDefrozen.v1;
* joint_declaration   tells the member at each step, and on APPROVED applies the correction, keeps the history
                      and publishes MemberChangeApproved.v1 (so, for example, ECR name checks use the new name);
* employer_exit       on APPROVED records the exit, or its correction, and publishes MemberExitMarked.v1;
* every process marked visible_to_member is kept as one of the member's applications."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exits import record_exit, track
from app.infra.tables import employments, member_changes, members
from epfo_persistence import add_event

CORE_FIELDS = {"NAME": "name", "DATE_OF_BIRTH": "date_of_birth", "GENDER": "gender"}
JD_NOTICES = {"EMPLOYER_ATTESTED": "JD_EMPLOYER_ATTESTED", "RETURNED_BY_EMPLOYER": "JD_RETURNED_BY_EMPLOYER",
              "REJECTED_BY_EMPLOYER": "JD_REJECTED_BY_EMPLOYER", "APPROVED": "JD_APPROVED", "REJECTED": "JD_REJECTED"}


async def on_process_transitioned(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    data = p.get("data") or {}
    if p.get("visible_to_member"):                   # the member's pending / processed applications
        await track(session, p["instance_id"], p["subject_ref"], p["process"], p.get("title", p["process"]), p["to_state"],
                    bool(p.get("terminal")), data.get("account_link_id") or data.get("from_account_link_id"))
    if p["process"] == "member_freeze":
        await _freeze(session, event)
    elif p["process"] == "joint_declaration":
        await _joint_declaration(session, event)
    elif p["process"] == "employer_exit" and p["to_state"] == "APPROVED":
        job = (await session.execute(select(employments).where(employments.c.account_link_id == data["account_link_id"]))).mappings().first()
        day = date.fromisoformat(data["date_of_exit"])
        if job and not job["date_of_exit"]:
            await record_exit(session, dict(job), day, data["reason"], "EMPLOYER", event["correlation_id"])
        elif job and data.get("correction_note") and (job["date_of_exit"], job["exit_reason"]) != (day, data["reason"]):
            await record_exit(session, dict(job), day, data["reason"], "EMPLOYER", event["correlation_id"],
                              corrects=job["date_of_exit"].isoformat())       # a corrected date of exit (P2.8b)


def _event_time(event: dict[str, Any]) -> datetime:
    ts = event.get("occurred_at")
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def _freeze(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["to_state"] not in ("FROZEN", "ACTIVE"):
        return
    uan, data = p["subject_ref"], p.get("data") or {}
    to = p["to_state"]
    at = _event_time(event)
    member = (await session.execute(select(members).where(members.c.uan == uan))).mappings().first()
    if not member:
        return
    current_at = member["account_state_updated_at"]
    if current_at is not None:
        if current_at.tzinfo is None:
            current_at = current_at.replace(tzinfo=UTC)
        if current_at > at:
            return
    if member["account_state"] == to:
        if current_at is None or current_at < at:
            await session.execute(update(members).where(members.c.uan == uan,
                                                        or_(members.c.account_state_updated_at.is_(None),
                                                            members.c.account_state_updated_at <= at))
                                  .values(account_state_updated_at=at))
        return
    res = await session.execute(update(members).where(members.c.uan == uan,
                                                      or_(members.c.account_state_updated_at.is_(None),
                                                          members.c.account_state_updated_at <= at))
                                .values(account_state=to, account_state_updated_at=at))
    if not res.rowcount:
        return
    if to == "FROZEN":
        await add_event(session, producer="member-service", event_type="AccountFrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "category": data.get("category", ""),
                            "order_ref": data.get("order_ref", "")})
    else:
        await add_event(session, producer="member-service", event_type="AccountDefrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "order_ref": p["instance_id"]})


async def _joint_declaration(session: AsyncSession, event: dict[str, Any]) -> None:
    p, data = event["payload"], event["payload"].get("data") or {}
    member = (await session.execute(select(members).where(members.c.uan == p["subject_ref"]))).mappings().first()
    if not member:
        return
    template = JD_NOTICES.get(p["to_state"])
    if template:
        await add_event(session, producer="member-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=p["instance_id"], correlation_id=event["correlation_id"], payload={
                            "recipient_subject": member["subject"], "template": template, "reference_id": p["instance_id"],
                            "params": {"parameter": data.get("parameter", "").replace("_", " ").lower(), "reason": data.get("reason") or data.get("note")}})
    if p["to_state"] != "APPROVED":
        return
    if (await session.execute(select(member_changes.c.id).where(member_changes.c.request_id == p["instance_id"]))).first():
        return                                                          # already applied
    parameter, value = data["parameter"], data["corrected_value"].strip()
    column = CORE_FIELDS.get(parameter)
    if column == "date_of_birth":
        old, new = member["date_of_birth"].isoformat(), date.fromisoformat(value)
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(date_of_birth=new))
    elif column:
        old, new = member[column], value.upper()                     # names and gender are stored in capitals
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values({column: new}))
    else:
        extra = dict(member["profile_extra"] or {})
        old, new = extra.get(parameter.lower()), value
        extra[parameter.lower()] = value
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(profile_extra=extra))
    await session.execute(insert(member_changes).values(request_id=p["instance_id"], member_id=member["member_id"],
                                                        parameter=parameter, old_value=str(old) if old is not None else None,
                                                        new_value=str(new), approved_by=p.get("actor_subject", "")))
    await add_event(session, producer="member-service", event_type="MemberChangeApproved.v1", aggregate_type="member_change_request",
                    aggregate_id=p["instance_id"], correlation_id=event["correlation_id"], payload={
                        "request_id": p["instance_id"], "uan": p["subject_ref"],
                        "parameters": [{"parameter": parameter, "value": str(new)}], "approver_subject": p.get("actor_subject", "")})


async def on_issue_tracker(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.8e: an Issue Tracker request the IS Division executed — freeze or de-freeze the account (as the freeze process
    does, publishing AccountFrozen.v1 / AccountDefrozen.v1), or show the member a notice at the next login."""
    p = event["payload"]
    member = (await session.execute(select(members).where(members.c.uan == p["target_uan"]))).mappings().first()
    if not member:
        return
    if p["kind"] in ("FREEZE_MEMBER", "DEFREEZE_MEMBER"):
        to = "FROZEN" if p["kind"] == "FREEZE_MEMBER" else "ACTIVE"
        at = _event_time(event)
        current_at = member["account_state_updated_at"]
        if current_at is not None:
            if current_at.tzinfo is None:
                current_at = current_at.replace(tzinfo=UTC)
            if current_at > at:
                return
        if member["account_state"] == to:
            if current_at is None or current_at < at:
                await session.execute(update(members).where(members.c.uan == p["target_uan"],
                                                            or_(members.c.account_state_updated_at.is_(None),
                                                                members.c.account_state_updated_at <= at))
                                      .values(account_state_updated_at=at))
            return
        res = await session.execute(update(members).where(members.c.uan == p["target_uan"],
                                                          or_(members.c.account_state_updated_at.is_(None),
                                                              members.c.account_state_updated_at <= at))
                                    .values(account_state=to, account_state_updated_at=at))
        if not res.rowcount:
            return
        if to == "FROZEN":
            await add_event(session, producer="member-service", event_type="AccountFrozen.v1", aggregate_type="account",
                            aggregate_id=p["target_uan"], correlation_id=event["correlation_id"], payload={
                                "target_type": "member", "target_id": p["target_uan"], "category": "ISSUE_TRACKER", "order_ref": p["order_ref"]})
        else:
            await add_event(session, producer="member-service", event_type="AccountDefrozen.v1", aggregate_type="account",
                            aggregate_id=p["target_uan"], correlation_id=event["correlation_id"], payload={
                                "target_type": "member", "target_id": p["target_uan"], "order_ref": p["order_ref"]})
    elif member["subject"]:
        await add_event(session, producer="member-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=p["request_id"], correlation_id=event["correlation_id"], payload={
                            "recipient_subject": member["subject"], "template": "OFFICE_NOTICE", "reference_id": p["request_id"],
                            "params": {"reason": p.get("notice") or ""}})
