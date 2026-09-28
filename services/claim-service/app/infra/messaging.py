"""Events claim-service consumes. Each handler runs inside the inbox transaction (apply_once), so a
redelivered event is applied once; state guards make an out-of-order event a logged no-op."""
from datetime import date
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import load_claim, notify, record_decision, transition
from app.domain.claims import HOLDABLE, route
from app.infra.tables import accounts, claims, risk_flags
from epfo_observability import Problem, get_logger
from epfo_persistence.policy import on_policy_published, rules_by_version

log = get_logger("claim-service")

BINDINGS = [
    "contribution-service.ContributionPosted.v1",
    "contribution-service.ClaimDebitPosted.v1",
    "workflow-service.CaseDecisionSubmitted.v1",
    "payment-simulator.PaymentConfirmed.v1",
    "payment-simulator.PaymentReturned.v1",
    "intelligence-service.RiskSignalRaised.v1",
    "intelligence-service.RiskSignalReviewed.v1",
    "member-service.AccountFrozen.v1",
    "member-service.AccountDefrozen.v1",
    "platform-service.PolicyPublished.v1",
    "contribution-service.LedgerReversed.v1",
    "contribution-service.InterestCredited.v1",
    "member-service.MemberExitMarked.v1",
    "contribution-service.TransferPosted.v1",
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


async def on_interest_credited(session: AsyncSession, event: dict[str, Any]) -> None:
    """Annual interest (or a rate revision's difference; negative when a rate is lowered) moves the balances."""
    for p in event["payload"]["postings"]:
        await session.execute(update(accounts).where(accounts.c.account_link_id == p["account_link_id"]).values(
            employee_paise=accounts.c.employee_paise + int(p["employee_paise"]),
            employer_paise=accounts.c.employer_paise + int(p["employer_paise"])))


async def on_member_exit(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(accounts).where(accounts.c.account_link_id == p["account_link_id"])
                          .values(date_of_exit=date.fromisoformat(p["date_of_exit"])))


async def on_transfer_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    """Form 13: the previous member ID's shares move to the current one."""
    p = event["payload"]
    for link, sign in ((p["from_account_link_id"], -1), (p["to_account_link_id"], 1)):
        await session.execute(update(accounts).where(accounts.c.account_link_id == link).values(
            employee_paise=accounts.c.employee_paise + sign * int(p["employee_paise"]),
            employer_paise=accounts.c.employer_paise + sign * int(p["employer_paise"])))


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
        await transition(session, claim, "RECOMMENDED", role, "Reviewed and recommended for approval.", recommended=True)
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
        await notify(session, claim, "CLAIM_SETTLED", cid,        # a re-payment goes to the corrected account; the net of TDS is paid
                     **({"bank_account_last4": claim["payee_account_last4"]} if claim.get("payee_account_last4") else {}),
                     **({"amount_paise": claim["tax"]["net_paise"], "tds_paise": claim["tax"]["tds_paise"]} if claim.get("tax") else {}))
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


async def on_freeze(session: AsyncSession, event: dict[str, Any]) -> None:
    """Freeze: open claims before payment go on hold. De-freeze (init.md §7): a claim frozen before any
    recommendation resumes (or is routed again if it had been approved automatically); a claim with a
    recommendation restarts under the stricter after-de-freeze chain with earlier approvals void."""
    p = event["payload"]
    if p["target_type"] != "member":
        return
    frozen = event["event_type"] == "AccountFrozen.v1"
    await session.execute(update(accounts).where(accounts.c.uan == p["target_id"]).values(frozen=frozen))
    links = (await session.execute(select(accounts.c.account_link_id).where(accounts.c.uan == p["target_id"]))).scalars().all()
    rows = (await session.execute(select(claims).where(claims.c.account_link_id.in_(links),
                                                       claims.c.state.in_(HOLDABLE if frozen else {"ON_HOLD_FROZEN"})))).mappings().all()
    cid = event["correlation_id"]
    for row in rows:
        claim = dict(row)
        if frozen:
            await transition(session, claim, "ON_HOLD_FROZEN", "system", "On hold while the account is being verified.",
                             reason="ACCOUNT_FROZEN", prior_state=claim["state"])
        elif claim["recommended"]:
            await transition(session, claim, "UNDER_REVIEW", "system",
                             "Account verified. Earlier approvals are void; the claim is reviewed again under the stricter chain.",
                             reason="DEFROZEN_APPROVALS_VOID", recommended=False, prior_state=None)
        elif claim["prior_state"] in ("SUBMITTED", "AUTO_APPROVED"):
            claim = await transition(session, claim, "SUBMITTED", "system", "Account verified; the claim is checked again.",
                                     reason="DEFROZEN_RESUBMITTED", prior_state=None)
            rules = await rules_by_version(session, claim["rule_version"])
            if route(claim["amount_paise"], rules, claim["claim_type"]) == "AUTO":
                claim = await transition(session, claim, "AUTO_APPROVED", "system", "Within the automatic settlement limit.",
                                         reason="DEFROZEN_AUTO")
                await record_decision(session, claim, "AUTO_APPROVED", "WITHIN_AUTO_LIMIT", cid)
            else:
                await transition(session, claim, "UNDER_REVIEW", "system", "Sent to your regional office for review.",
                                 reason="DEFROZEN_REVIEW")
        else:
            await transition(session, claim, claim["prior_state"] or "UNDER_REVIEW", "system", "Account verified; the claim continues.",
                             reason="DEFROZEN_RESUMED", prior_state=None)


async def on_ledger_reversed(session: AsyncSession, event: dict[str, Any]) -> None:
    """A rejected claim's debit was reversed: the member's balance comes back."""
    p = event["payload"]
    await _member_lines(session, [x for x in p["postings"] if x["side"] == "credit"], +1)
    await session.execute(update(claims).where(claims.c.claim_id == p["claim_id"]).values(debit_journal_id=None))


HANDLERS = {
    "LedgerReversed.v1": on_ledger_reversed,
    "PolicyPublished.v1": on_policy_published,
    "AccountFrozen.v1": on_freeze,
    "AccountDefrozen.v1": on_freeze,
    "RiskSignalRaised.v1": on_risk_signal,
    "RiskSignalReviewed.v1": on_risk_signal,
    "ContributionPosted.v1": on_contribution_posted,
    "InterestCredited.v1": on_interest_credited,
    "MemberExitMarked.v1": on_member_exit,
    "TransferPosted.v1": on_transfer_posted,
    "ClaimDebitPosted.v1": on_claim_debit_posted,
    "CaseDecisionSubmitted.v1": on_case_decision,
    "PaymentConfirmed.v1": on_payment_result,
    "PaymentReturned.v1": on_payment_result,
}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)
