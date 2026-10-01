"""Claim journals (Journey B6): the member-account debit when a claim is approved, and the bank
settlement when the mock bank pays it. Journals are keyed by business key, so a redelivered event
can never post twice; every journal balances."""
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from epfo_persistence import add_event

PRODUCER = "contribution-service"


async def _post(session: AsyncSession, business_key: str, kind: str, claim_id: str, lines: list[dict[str, Any]],
                reverses: str | None = None) -> str | None:
    """Insert a balanced journal once. Returns the journal ID, or None if it already exists."""
    if (await session.execute(text("SELECT id FROM journals WHERE business_key=:k"), {"k": business_key})).first():
        return None
    debit = sum(x["amount_paise"] for x in lines if x["side"] == "debit")
    credit = sum(x["amount_paise"] for x in lines if x["side"] == "credit")
    if debit != credit:
        raise ValueError(f"unbalanced {kind} journal for {claim_id}: {debit} != {credit}")
    journal_id = str(uuid.uuid4())
    await session.execute(text("INSERT INTO journals (id, business_key, kind, occurred_at, filing_id, claim_id, reverses_journal_id) "
                               "VALUES (:id, :k, :kind, :at, NULL, :c, :r)"),
                          {"id": journal_id, "k": business_key, "kind": kind, "at": datetime.now(UTC), "c": claim_id, "r": reverses})
    for line in lines:
        await session.execute(text("INSERT INTO journal_lines (journal_id, account_code, side, amount_paise, account_link_id, share) "
                                   "VALUES (:j, :a, :s, :n, :l, :h)"),
                              {"j": journal_id, "a": line["account_code"], "s": line["side"], "n": line["amount_paise"],
                               "l": line.get("account_link_id"), "h": line.get("share")})
    return journal_id


async def member_shares(session: AsyncSession, account_link_id: str) -> dict[str, int]:
    rows = (await session.execute(text(
        "SELECT share, SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) FROM journal_lines "
        "WHERE account_code='AC01_EPF' AND account_link_id=:a AND share IN ('employee','employer') GROUP BY share"),
        {"a": account_link_id})).all()
    shares = {"employee": 0, "employer": 0}
    shares.update({share: int(total) for share, total in rows})
    return shares


async def on_higher_pension_transfer(session: AsyncSession, event: dict[str, Any]) -> None:
    """Move higher pension dues from the member's PF shares to EPS once per option."""
    p = event["payload"]
    option_id, account = p["option_id"], p["account_link_id"]
    amount = int(p["amount_paise"])
    if amount <= 0:
        raise ValueError("higher pension transfer amount must be positive")
    lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    member = (await session.execute(text("SELECT uan FROM establishment_members WHERE account_link_id=:a" + lock),
                                    {"a": account})).scalar_one_or_none()
    if member != p["uan"]:
        raise ValueError(f"higher pension account {account} does not match UAN {p['uan']}")
    if (await session.execute(text("SELECT 1 FROM journals WHERE business_key=:k"),
                              {"k": f"HP-{option_id}"})).first():
        return
    shares = await member_shares(session, account)
    if shares["employee"] + shares["employer"] < amount:
        await add_event(session, producer=PRODUCER, event_type="HigherPensionTransferPosted.v1",
                        aggregate_type="higher_pension_option", aggregate_id=option_id,
                        correlation_id=event["correlation_id"], payload={"option_id": option_id,
                            "status": "INSUFFICIENT_BALANCE", "posted_paise": 0, "journal_id": None})
        return
    employer = min(amount, shares["employer"])
    lines = [{"account_code": "AC01_EPF", "side": "debit", "amount_paise": part,
              "account_link_id": account, "share": share}
             for share, part in (("employer", employer), ("employee", amount - employer)) if part]
    lines.append({"account_code": "AC10_EPS", "side": "credit", "amount_paise": amount})
    journal_id = await _post(session, f"HP-{option_id}", "HIGHER_PENSION_TRANSFER", None, lines)
    if journal_id:
        await add_event(session, producer=PRODUCER, event_type="HigherPensionTransferPosted.v1",
                        aggregate_type="higher_pension_option", aggregate_id=option_id,
                        correlation_id=event["correlation_id"], payload={"option_id": option_id,
                            "status": "POSTED", "posted_paise": amount, "journal_id": journal_id})
        await add_event(session, producer=PRODUCER, event_type="LedgerAdjusted.v1",
                        aggregate_type="ledger_journal", aggregate_id=journal_id,
                        correlation_id=event["correlation_id"], payload={"adjustment_id": option_id,
                            "journal_id": journal_id, "account_link_id": account,
                            "appendix_type": "EPS_DIVERSION", "postings": lines})


async def on_claim_decision(session: AsyncSession, event: dict[str, Any]) -> None:
    """Approved claim → debit the member's EPF account (employee share first) and credit CLAIMS_PAYABLE."""
    p = event["payload"]
    if p["decision"] == "REJECTED":
        await reverse_claim_debit(session, event)
        return
    if p["decision"] not in ("APPROVED", "AUTO_APPROVED"):
        return
    amount, account = int(p["amount_paise"]), p["account_link_id"]
    if p.get("fund") in ("EDLI", "EPS"):   # EDLI assurance / EPS withdrawal benefit: paid from the fund, not the member's PF
        lines = [{"account_code": "AC21_EDLI" if p["fund"] == "EDLI" else "AC10_EPS", "side": "debit", "amount_paise": amount},
                 {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": amount}]
        journal_id = await _post(session, f"CLAIM-DEBIT-{p['claim_id']}", f"{p['fund']}_CLAIM_DEBIT", p["claim_id"], lines)
        if journal_id:
            await add_event(session, producer=PRODUCER, event_type="ClaimDebitPosted.v1", aggregate_type="ledger_journal",
                            aggregate_id=journal_id, correlation_id=event["correlation_id"],
                            payload={"journal_id": journal_id, "claim_id": p["claim_id"], "postings": lines})
        return
    shares = await member_shares(session, account)
    if shares["employee"] + shares["employer"] < amount:
        raise ValueError(f"claim {p['claim_id']} exceeds the ledger balance of {account}")
    from_employee = min(amount, shares["employee"])
    lines = [{"account_code": "AC01_EPF", "side": "debit", "amount_paise": part, "account_link_id": account, "share": share}
             for share, part in (("employee", from_employee), ("employer", amount - from_employee)) if part]
    lines.append({"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": amount})
    journal_id = await _post(session, f"CLAIM-DEBIT-{p['claim_id']}", "CLAIM_DEBIT", p["claim_id"], lines)
    if journal_id:
        await add_event(session, producer=PRODUCER, event_type="ClaimDebitPosted.v1", aggregate_type="ledger_journal",
                        aggregate_id=journal_id, correlation_id=event["correlation_id"],
                        payload={"journal_id": journal_id, "claim_id": p["claim_id"], "postings": lines})


async def on_claim_paid(session: AsyncSession, event: dict[str, Any]) -> None:
    """The mock bank paid the claim → CLAIMS_PAYABLE is discharged against BANK_SETTLEMENT."""
    p = event["payload"]
    amount = int(p["amount_paise"])
    await _post(session, p["payment_id"], "CLAIM_SETTLEMENT", p["reference_id"], [
        {"account_code": "CLAIMS_PAYABLE", "side": "debit", "amount_paise": amount},
        {"account_code": "BANK_SETTLEMENT", "side": "credit", "amount_paise": amount}])


async def reverse_claim_debit(session: AsyncSession, event: dict[str, Any]) -> None:
    """A claim rejected after its account was debited (for example re-reviewed after a de-freeze): the member's
    money comes back through a reversing journal — journals are never edited (ADR-0003)."""
    claim_id = event["payload"]["claim_id"]
    debit = (await session.execute(text("SELECT id FROM journals WHERE business_key=:k"), {"k": f"CLAIM-DEBIT-{claim_id}"})).first()
    if not debit:
        return                                                     # nothing was debited: nothing to reverse
    rows = (await session.execute(text("SELECT account_code, side, amount_paise, account_link_id, share FROM journal_lines "
                                       "WHERE journal_id=:j"), {"j": debit[0]})).mappings().all()
    lines = [{"account_code": r["account_code"], "side": "credit" if r["side"] == "debit" else "debit", "amount_paise": r["amount_paise"],
              **({"account_link_id": r["account_link_id"]} if r["account_link_id"] else {}), **({"share": r["share"]} if r["share"] else {})}
             for r in rows]
    journal_id = await _post(session, f"CLAIM-REVERSAL-{claim_id}", "CLAIM_REVERSAL", claim_id, lines, reverses=debit[0])
    if journal_id:
        await add_event(session, producer=PRODUCER, event_type="LedgerReversed.v1", aggregate_type="ledger_journal",
                        aggregate_id=journal_id, correlation_id=event["correlation_id"], payload={
                            "journal_id": journal_id, "reverses_journal_id": debit[0], "reason": "Claim rejected after its account was debited",
                            "claim_id": claim_id, "postings": lines, "reversed_kind": "CLAIM_DEBIT", "reference_id": claim_id})


async def on_tax_deducted(session: AsyncSession, event: dict[str, Any]) -> None:
    """TDS withheld from a withdrawal: that part of CLAIMS_PAYABLE is owed to the tax department, not the bank."""
    p = event["payload"]
    tds = int(p["tds_paise"])
    if tds:
        await _post(session, f"TDS-{p['claim_id']}", "TDS", p["claim_id"], [
            {"account_code": "CLAIMS_PAYABLE", "side": "debit", "amount_paise": tds},
            {"account_code": "TDS_PAYABLE", "side": "credit", "amount_paise": tds}])
