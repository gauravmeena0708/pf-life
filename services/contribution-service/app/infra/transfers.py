"""Form 13 transfers and dates of exit (Phase 2, slice 1).

The transfer runs on the process engine (config/processes/transfer-form13.yaml); this service owns its effect:
when the case is APPROVED the whole balance of the previous member ID (employee and employer shares) moves to
the current one as one balanced journal, keyed by the case, so a redelivered event never posts twice. It then
publishes TransferPosted.v1 and keeps the posting for the member's Annexure K."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.claims_ledger import _post, member_shares
from epfo_persistence import add_event

PRODUCER = "contribution-service"


async def on_member_exit(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(text("UPDATE establishment_members SET date_of_exit=:d, status='EXITED' WHERE account_link_id=:a"),
                          {"d": date.fromisoformat(p["date_of_exit"]), "a": p["account_link_id"]})


async def on_process_transitioned(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["process"] == "establishment_freeze":             # a frozen establishment files no ECR (P2.5c)
        if p["to_state"] == "FROZEN":
            if not (await session.execute(text("SELECT 1 FROM establishment_freezes WHERE establishment_id=:e"), {"e": p["subject_ref"]})).first():
                await session.execute(text("INSERT INTO establishment_freezes (establishment_id, case_id, order_ref, frozen_at) VALUES (:e, :c, :o, :t)"),
                                      {"e": p["subject_ref"], "c": p["instance_id"], "o": (p.get("data") or {}).get("order_ref"), "t": datetime.now(UTC)})
        elif p["to_state"] == "ACTIVE":
            await session.execute(text("DELETE FROM establishment_freezes WHERE establishment_id=:e"), {"e": p["subject_ref"]})
        return
    if p["process"] != "transfer_form13" or p["to_state"] != "APPROVED":
        return
    data = p.get("data") or {}
    await post_transfer(session, p["instance_id"], p["subject_ref"], data["from_account_link_id"], data["to_account_link_id"],
                        p.get("actor_subject", ""), event["correlation_id"])


async def on_auto_transfer(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.8b: the member confirmed an auto-transfer on a change of job; post it as Form 13 would be once approved."""
    p = event["payload"]
    if (await session.execute(text("SELECT 1 FROM transfer_postings WHERE from_account_link_id=:f"), {"f": p["from_account_link_id"]})).first():
        return                                                   # already transferred (e.g. by a Form 13 meanwhile)
    await post_transfer(session, p["transfer_id"], p["uan"], p["from_account_link_id"], p["to_account_link_id"],
                        "AUTO_TRANSFER", event["correlation_id"])


async def post_transfer(session: AsyncSession, transfer_id: str, uan: str, frm: str, to: str, approved_by: str,
                        correlation_id: str | None) -> None:
    """Move the member ID's whole balance (a balanced journal) and publish TransferPosted.v1."""
    if (await session.execute(text("SELECT 1 FROM transfer_postings WHERE transfer_id=:t"), {"t": transfer_id})).first():
        return
    shares = await member_shares(session, frm)
    lines = []
    for share in ("employee", "employer"):
        if shares[share] > 0:
            lines += [{"account_code": "AC01_EPF", "side": "debit", "amount_paise": shares[share], "account_link_id": frm, "share": share},
                      {"account_code": "AC01_EPF", "side": "credit", "amount_paise": shares[share], "account_link_id": to, "share": share}]
    journal_id = await _post(session, f"TRANSFER-{transfer_id}", "TRANSFER", None, lines) if lines else None
    subject = (await session.execute(text("SELECT member_subject FROM establishment_members WHERE account_link_id=:a"),
                                     {"a": to})).scalar_one_or_none()
    await session.execute(text(
        "INSERT INTO transfer_postings (transfer_id, uan, member_subject, from_account_link_id, to_account_link_id, employee_paise, "
        "employer_paise, journal_id, approved_by, posted_at) VALUES (:t, :u, :s, :f, :to, :ee, :er, :j, :by, CURRENT_TIMESTAMP)"),
        {"t": transfer_id, "u": uan, "s": subject, "f": frm, "to": to, "ee": max(shares["employee"], 0),
         "er": max(shares["employer"], 0), "j": journal_id, "by": approved_by})
    await add_event(session, producer=PRODUCER, event_type="TransferPosted.v1", aggregate_type="ledger_journal",
                    aggregate_id=transfer_id, correlation_id=correlation_id, payload={
                        "transfer_id": transfer_id, "uan": uan, "from_account_link_id": frm, "to_account_link_id": to,
                        "employee_paise": max(shares["employee"], 0), "employer_paise": max(shares["employer"], 0),
                        "journal_id": journal_id or "", "postings": lines})


async def on_member_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    """A joinee registered by the employer (a new UAN, or a new member ID under an existing one)."""
    p = event["payload"]
    await session.execute(text(
        "INSERT INTO establishment_members (uan, name, date_of_birth, account_link_id, member_subject, establishment_id, "
        "date_of_joining, date_of_exit, status) VALUES (:u, :n, :dob, :a, :s, :e, :j, NULL, 'ACTIVE') ON CONFLICT (account_link_id) DO NOTHING"),
        {"u": p["uan"], "n": p["name"], "dob": date.fromisoformat(p["date_of_birth"]), "a": p["account_link_id"],
         "s": p.get("member_subject"), "e": p["establishment_id"], "j": date.fromisoformat(p["date_of_joining"])})
