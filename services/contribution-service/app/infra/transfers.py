"""Form 13 transfers and dates of exit (Phase 2, slice 1).

The transfer runs on the process engine (config/processes/transfer-form13.yaml); this service owns its effect:
when the case is APPROVED the PF leg is recorded once. EPFO balances move through a balanced journal;
trust sources wait for a reconciled Annexure K. The EPS leg is updated by the pension service."""
import json
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
    """Post the PF leg once; the EPS leg is completed by the pension service."""
    if (await session.execute(text("SELECT 1 FROM transfer_legs WHERE transfer_id=:t"), {"t": transfer_id})).first():
        return
    # A transfer posted before this projection was introduced still has its original journal.
    if (await session.execute(text("SELECT 1 FROM transfer_postings WHERE transfer_id=:t"), {"t": transfer_id})).first():
        await session.execute(text("""INSERT INTO transfer_legs
            (transfer_id,uan,from_account_link_id,to_account_link_id,pf_leg,eps_leg,direction,detail,updated_at)
            VALUES (:t,:u,:f,:to,'COMPLETED','WAITING_FOR_PF','EPFO_TO_EPFO','{}',:at)"""),
            {"t": transfer_id, "u": uan, "f": frm, "to": to, "at": datetime.now(UTC)})
        return
    accounts = (await session.execute(text("""SELECT m.account_link_id,m.uan,m.date_of_joining,m.date_of_exit,e.establishment_id,e.trust_id,e.trust_name
        FROM establishment_members m LEFT JOIN exempted_establishments e ON e.establishment_id=m.establishment_id
        AND e.pf_exempt=true AND (e.status='ACTIVE' OR e.ended_on>COALESCE(m.date_of_exit,CURRENT_DATE))
        AND e.effective_from<=COALESCE(m.date_of_exit,CURRENT_DATE)
        WHERE m.account_link_id IN (:f,:to)"""), {"f": frm, "to": to})).mappings().all()
    by_id = {r["account_link_id"]: r for r in accounts}
    if frm not in by_id or to not in by_id or by_id[frm]["uan"] != uan or by_id[to]["uan"] != uan:
        raise ValueError("transfer member IDs must belong to the same UAN")
    source, destination = by_id[frm], by_id[to]
    cancelled_destination = (await session.execute(text("SELECT 1 FROM establishment_members m "
        "JOIN exempted_establishments e ON e.establishment_id=m.establishment_id "
        "WHERE m.account_link_id=:to AND e.pf_exempt=true AND e.status='CANCELLED' "
        "AND (e.ended_on IS NULL OR m.date_of_joining IS NULL OR m.date_of_joining<e.ended_on)"),
        {"to": to})).first()
    if cancelled_destination:
        # A cancelled exemption cannot receive a new PF transfer into its trust.
        raise ValueError("new transfer into a cancelled trust is refused")
    if source["trust_id"] and destination["trust_id"]:
        raise ValueError("a trust-to-trust PF transfer requires a separate process")
    direction = "TRUST_TO_EPFO" if source["trust_id"] else "EPFO_TO_TRUST" if destination["trust_id"] else "EPFO_TO_EPFO"
    pf = "AWAITING_TRUST" if direction == "TRUST_TO_EPFO" else "SENT_TO_TRUST" if direction == "EPFO_TO_TRUST" else "COMPLETED"
    detail = {"trust_name": (source if source["trust_id"] else destination)["trust_name"]}
    await session.execute(text("""INSERT INTO transfer_legs
        (transfer_id,uan,from_account_link_id,to_account_link_id,pf_leg,eps_leg,direction,detail,updated_at)
        VALUES (:t,:u,:f,:to,:pf,'WAITING_FOR_PF',:direction,:detail,:at)"""),
        {"t": transfer_id, "u": uan, "f": frm, "to": to, "pf": pf, "direction": direction,
         "detail": json.dumps(detail), "at": datetime.now(UTC)})
    if direction == "TRUST_TO_EPFO":
        await add_event(session, producer=PRODUCER, event_type="TrustTransferRequested.v1",
                        aggregate_type="transfer", aggregate_id=transfer_id, correlation_id=correlation_id,
                        payload={"transfer_id": transfer_id, "uan": uan, "from_account_link_id": frm,
                                 "to_account_link_id": to, "establishment_id": source["establishment_id"],
                                 "trust_id": source["trust_id"]})
        return
    shares = await member_shares(session, frm)
    lines = []
    for share in ("employee", "employer"):
        if shares[share] > 0:
            lines += [{"account_code": "AC01_EPF", "side": "debit", "amount_paise": shares[share], "account_link_id": frm, "share": share},
                      ({"account_code": "PAYABLE_TO_TRUSTS", "side": "credit", "amount_paise": shares[share]}
                       if direction == "EPFO_TO_TRUST" else
                       {"account_code": "AC01_EPF", "side": "credit", "amount_paise": shares[share], "account_link_id": to, "share": share})]
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
                        "journal_id": journal_id or "", "postings": lines,
                        "source": "EPFO", "destination": "TRUST" if direction == "EPFO_TO_TRUST" else "EPFO",
                        "service_from": str(source["date_of_joining"]) if source["date_of_joining"] else None,
                        "service_to": str(source["date_of_exit"]) if source["date_of_exit"] else None})


async def redirect_cancelled_trust_transfers(session: AsyncSession, establishment_id: str) -> None:
    """Complete PF legs already sent to a trust whose exemption has since been cancelled."""
    lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    rows = (await session.execute(text("SELECT l.transfer_id,l.to_account_link_id,p.uan,p.from_account_link_id, "
        "p.employee_paise,p.employer_paise FROM transfer_legs l "
        "JOIN transfer_postings p ON p.transfer_id=l.transfer_id "
        "JOIN establishment_members m ON m.account_link_id=l.to_account_link_id "
        "WHERE m.establishment_id=:e AND l.direction='EPFO_TO_TRUST' AND l.pf_leg='SENT_TO_TRUST'" + lock),
        {"e": establishment_id})).mappings().all()
    for row in rows:
        amount = int(row["employee_paise"]) + int(row["employer_paise"])
        if amount <= 0:
            continue
        lines = [{"account_code": "PAYABLE_TO_TRUSTS", "side": "debit", "amount_paise": amount}]
        lines += [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": int(row[key]),
                   "account_link_id": row["to_account_link_id"], "share": share}
                  for key, share in (("employee_paise", "employee"), ("employer_paise", "employer")) if row[key]]
        # Exemption cancellation: clear the trust payable and credit the EPFO member account.
        await _post(session, f"CANCELLED-TRUST-{row['transfer_id']}", "TRUST_TRANSFER_REDIRECT", None, lines)
        await session.execute(text("UPDATE transfer_legs SET direction='EPFO_TO_EPFO',pf_leg='COMPLETED',"
                                   "updated_at=:at WHERE transfer_id=:t"),
                              {"at": datetime.now(UTC), "t": row["transfer_id"]})


async def on_trust_annexure_k(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    leg = (await session.execute(text("SELECT * FROM transfer_legs WHERE transfer_id=:t" + lock),
                                 {"t": p["transfer_id"]})).mappings().first()
    if not leg or leg["direction"] != "TRUST_TO_EPFO" or leg["to_account_link_id"] != p["to_account_link_id"]:
        raise ValueError("Annexure K does not match an awaiting trust transfer")
    if leg["pf_leg"] == "COMPLETED":
        return
    ee, er = int(p["employee_paise"]), int(p["employer_paise"])
    if ee < 0 or er < 0 or ee + er <= 0:
        raise ValueError("Annexure K amounts must be positive")
    lines = [{"account_code": "BANK_COLLECTION", "side": "debit", "amount_paise": ee + er}]
    lines += [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": amount,
               "account_link_id": leg["to_account_link_id"], "share": share}
              for share, amount in (("employee", ee), ("employer", er)) if amount]
    journal_id = await _post(session, f"TRUST-{p['annexure_id']}", "TRUST_TRANSFER", None, lines)
    if not journal_id:
        return
    previous = leg["detail"] if isinstance(leg["detail"], dict) else json.loads(leg["detail"])
    detail = {**previous, "annexure_id": p["annexure_id"], "service_from": p.get("service_from"),
              "service_to": p.get("service_to"), "breaks_months": p.get("breaks_months")}
    await session.execute(text("UPDATE transfer_legs SET pf_leg='ANNEXURE_K_RECEIVED',detail=:d,updated_at=:at WHERE transfer_id=:t"),
                          {"d": json.dumps(detail), "at": datetime.now(UTC), "t": p["transfer_id"]})
    await session.execute(text("UPDATE transfer_legs SET pf_leg='COMPLETED',updated_at=:at WHERE transfer_id=:t"),
                          {"at": datetime.now(UTC), "t": p["transfer_id"]})
    await add_event(session, producer=PRODUCER, event_type="TransferPosted.v1", aggregate_type="ledger_journal",
                    aggregate_id=p["transfer_id"], correlation_id=event["correlation_id"], payload={
                        "transfer_id": p["transfer_id"], "uan": leg["uan"], "from_account_link_id": leg["from_account_link_id"],
                        "to_account_link_id": leg["to_account_link_id"], "employee_paise": ee, "employer_paise": er,
                        "journal_id": journal_id, "postings": lines, "source": "TRUST", "destination": "EPFO",
                        "service_from": p.get("service_from"), "service_to": p.get("service_to"),
                        "breaks_months": p.get("breaks_months")})


async def on_eps_service_transferred(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    exists = (await session.execute(text("SELECT 1 FROM transfer_legs WHERE transfer_id=:t AND from_account_link_id=:f "
                                         "AND to_account_link_id=:to" + lock), {"t": p["transfer_id"],
                                         "f": p["from_account_link_id"], "to": p["to_account_link_id"]})).first()
    if not exists:
        return
    eps_detail = {
        "service_months": int(p["service_months"]),
        "breaks_months": int(p["breaks_months"]),
        "eps_breaks_months": int(p["breaks_months"]),
    }
    await session.execute(text(
        "UPDATE transfer_legs SET eps_leg='COMPLETED',eps_detail=:ed,updated_at=:at "
        "WHERE transfer_id=:t AND from_account_link_id=:f AND to_account_link_id=:to"
    ), {"ed": json.dumps(eps_detail), "at": datetime.now(UTC), "t": p["transfer_id"],
        "f": p["from_account_link_id"], "to": p["to_account_link_id"]})


async def on_member_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    """A joinee registered by the employer (a new UAN, or a new member ID under an existing one)."""
    p = event["payload"]
    await session.execute(text(
        "INSERT INTO establishment_members (uan, name, date_of_birth, account_link_id, member_subject, establishment_id, "
        "date_of_joining, date_of_exit, status) VALUES (:u, :n, :dob, :a, :s, :e, :j, NULL, 'ACTIVE') ON CONFLICT (account_link_id) DO NOTHING"),
        {"u": p["uan"], "n": p["name"], "dob": date.fromisoformat(p["date_of_birth"]), "a": p["account_link_id"],
         "s": p.get("member_subject"), "e": p["establishment_id"], "j": date.fromisoformat(p["date_of_joining"])})
