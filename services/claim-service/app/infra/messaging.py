"""Events claim-service consumes. Each handler runs inside the inbox transaction (apply_once), so a
redelivered event is applied once; state guards make an out-of-order event a logged no-op."""
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import load_claim, notify, record_decision, transition
from app.infra.tables import accounts, claims, risk_flags
from epfo_observability import Problem, get_logger

log = get_logger("claim-service")

BINDINGS = [
    "contribution-service.ContributionPosted.v1",
    "contribution-service.ClaimDebitPosted.v1",
    "workflow-service.CaseDecisionSubmitted.v1",
    "payment-simulator.PaymentConfirmed.v1",
    "payment-simulator.PaymentReturned.v1",
    "intelligence-service.RiskSignalRaised.v1",
    "intelligence-service.RiskSignalReviewed.v1",
]


async def _member_lines(session: AsyncSession, postings: list[dict[str, Any]], sign: int) -> None:
    for line in postings:
        if line.get("account_code") != "AC01_EPF" or not line.get("account_link_id") or line.get("share") not in ("employee", "employer"):
            continue
        column = accounts.c.employee_paise if line["share"] == "employee" else accounts.c.employer_paise
        await session.execute(update(accounts).where(accounts.c.account_link_id == line["account_link_id"])
                              .values({column: column + sign * int(line["amount_paise"])}))


async def _claim_or_none(session: AsyncSession, claim_id: str) -> dict[str, Any] | None:
    try:
        return await load_claim(session, claim_id, lock=True)
    except Problem:
        log.warning("event_for_unknown_claim", claim_id=claim_id)
        return None


async def on_contribution_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    await _member_lines(session, event["payload"]["postings"], +1)


async def on_claim_debit_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    claim = await _claim_or_none(session, p["claim_id"])
    if not claim or claim["debit_journal_id"]:
        return
    await _member_lines(session, [{**x, "side": "debit"} for x in p["postings"] if x["side"] == "debit"], -1)
    await session.execute(update(claims).where(claims.c.claim_id == claim["claim_id"]).values(debit_journal_id=p["journal_id"]))


async def on_case_decision(session: AsyncSession, event: dict[str, Any]) -> None:
    p, cid = event["payload"], event["correlation_id"]
    claim = await _claim_or_none(session, p["claim_id"])
    if not claim:
        return
    role, decision, reason = p["officer_role"], p["decision"], p.get("reason")
    expected = {"RECOMMEND": {"UNDER_REVIEW"}, "APPROVE": {"RECOMMENDED", "AWAITING_NEXT_APPROVAL"},
                "REJECT": {"RECOMMENDED", "AWAITING_NEXT_APPROVAL"}, "RETURN": {"RECOMMENDED", "AWAITING_NEXT_APPROVAL"}}
    if claim["state"] not in expected[decision]:
        log.warning("case_decision_ignored", claim_id=claim["claim_id"], state=claim["state"], decision=decision)
        return
    if decision == "RECOMMEND":
        await transition(session, claim, "RECOMMENDED", role, "Reviewed and recommended for approval.")
    elif decision == "RETURN":
        await transition(session, claim, "UNDER_REVIEW", role, f"Returned for rework: {reason}")
    elif decision == "REJECT":
        claim = await transition(session, claim, "REJECTED_WITH_REASON", role, f"Rejected: {reason}", decision_reason=reason)
        await record_decision(session, claim, "REJECTED", "OFFICER_REJECTED", cid)
        await notify(session, claim, "CLAIM_REJECTED", cid, reason=reason)
    elif p["final"]:
        claim = await transition(session, claim, "APPROVED", role, "Approved.", decision_reason=reason)
        await record_decision(session, claim, "APPROVED", "OFFICER_APPROVED", cid)
        await notify(session, claim, "CLAIM_APPROVED", cid)
    else:
        await transition(session, claim, "AWAITING_NEXT_APPROVAL", role, "Approved at this level; sent to the next approver.")


async def on_payment_result(session: AsyncSession, event: dict[str, Any]) -> None:
    p, cid = event["payload"], event["correlation_id"]
    if p.get("purpose") != "CLAIM_SETTLEMENT":
        return
    claim_id = p.get("reference_id") or p.get("reference")
    claim = await _claim_or_none(session, claim_id)
    if not claim or claim["state"] != "PAYMENT_PENDING" or claim["payment_id"] != p["payment_id"]:
        return
    if event["event_type"] == "PaymentConfirmed.v1":
        claim = await transition(session, claim, "SETTLED", "bank", "Paid into your bank account (mock bank).")
        await notify(session, claim, "CLAIM_SETTLED", cid)
    else:
        claim = await transition(session, claim, "PAYMENT_RETURNED", "bank",
                                 f"The bank returned the payment ({p.get('return_reason')}).")
        await notify(session, claim, "CLAIM_PAYMENT_RETURNED", cid, reason=p.get("return_reason"))


async def on_risk_signal(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    status = "OPEN" if event["event_type"] == "RiskSignalRaised.v1" else p["outcome"]
    updated = await session.execute(update(risk_flags).where(risk_flags.c.signal_id == p["signal_id"]).values(status=status))
    if not updated.rowcount:
        await session.execute(insert(risk_flags).values(signal_id=p["signal_id"], subject=p["subject_ref"], status=status))


HANDLERS = {
    "RiskSignalRaised.v1": on_risk_signal,
    "RiskSignalReviewed.v1": on_risk_signal,
    "ContributionPosted.v1": on_contribution_posted,
    "ClaimDebitPosted.v1": on_claim_debit_posted,
    "CaseDecisionSubmitted.v1": on_case_decision,
    "PaymentConfirmed.v1": on_payment_result,
    "PaymentReturned.v1": on_payment_result,
}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)
