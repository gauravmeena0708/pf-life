"""Events claim-service consumes. Each handler runs inside the inbox transaction (apply_once), so a
redelivered event is applied once; state guards make an out-of-order event a logged no-op."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import load_claim, notify, record_decision, transition
from app.domain.claims import HOLDABLE, route
from app.infra.tables import (accounts, annexure_k_files, auto_transfers, claim_beneficiaries, claims, member_bank_accounts,
                              nominations, risk_flags)
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
    "contribution-service.LedgerAdjusted.v1",
    "member-service.PrimaryMemberIdChanged.v1",
    "contribution-service.InterestCredited.v1",
    "member-service.MemberExitMarked.v1",
    "contribution-service.TransferPosted.v1",
    "member-service.MemberRegistered.v1",
    "member-service.MemberKycUpdated.v1",
    "member-service.NominationRegistered.v1",
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
            interest_paise=accounts.c.interest_paise + int(p["employee_paise"]) + int(p["employer_paise"]),
            employee_paise=accounts.c.employee_paise + int(p["employee_paise"]),
            employer_paise=accounts.c.employer_paise + int(p["employer_paise"])))


async def on_member_exit(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(accounts).where(accounts.c.account_link_id == p["account_link_id"])
                          .values(date_of_exit=date.fromisoformat(p["date_of_exit"])))
    await on_member_death(session, event)


async def on_member_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    """A new member ID: it starts with no balance, in the office of the establishment's other accounts."""
    p = event["payload"]
    if (await session.execute(select(accounts.c.account_link_id).where(accounts.c.account_link_id == p["account_link_id"]))).first():
        return
    office = (await session.execute(select(accounts.c.office_id).where(accounts.c.establishment_id == p["establishment_id"]).limit(1))).scalar_one_or_none()
    office = office or (await session.execute(select(accounts.c.office_id).limit(1))).scalar_one()
    await session.execute(insert(accounts).values(
        account_link_id=p["account_link_id"], member_subject=p.get("member_subject"), uan=p["uan"], establishment_id=p["establishment_id"],
        office_id=office, date_of_joining=date.fromisoformat(p["date_of_joining"]), employee_paise=0, employer_paise=0,
        pan_verified=bool(p.get("pan_verified"))))


async def on_kyc_updated(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(accounts).where(accounts.c.uan == p["uan"]).values(pan_verified=bool(p["pan_verified"])))
    if p.get("kyc_type") == "AADHAAR" and p.get("status") == "VERIFIED":
        await session.execute(update(accounts).where(accounts.c.uan == p["uan"]).values(aadhaar_verified=True))
    if p.get("kyc_type") == "BANK" and p.get("bank_ifsc") and p.get("bank_account_last4") and not (await session.execute(
            select(member_bank_accounts.c.uan).where(member_bank_accounts.c.uan == p["uan"], member_bank_accounts.c.bank_ifsc == p["bank_ifsc"],
                                                     member_bank_accounts.c.bank_account_last4 == p["bank_account_last4"]))).first():
        await session.execute(insert(member_bank_accounts).values(uan=p["uan"], bank_ifsc=p["bank_ifsc"],
                                                                  bank_account_last4=p["bank_account_last4"]))


async def on_nomination(session: AsyncSession, event: dict[str, Any]) -> None:
    """e-Nomination (P2.8b): the signed nomination replaces the nominees on record; a nominee's login and bank
    details, when known, are kept for the same name."""
    p = event["payload"]
    old = {r["name"]: dict(r) for r in (await session.execute(select(nominations).where(nominations.c.uan == p["uan"]))).mappings().all()}
    await session.execute(nominations.delete().where(nominations.c.uan == p["uan"]))
    for i, n in enumerate(p["nominees"], start=1):
        was = old.get(n["name"], {})
        await session.execute(insert(nominations).values(nomination_id=f"{p['nomination_id']}-{i}", uan=p["uan"], name=n["name"],
                                                         relation=n["relation"], share_bp=n["share_bp"], subject=was.get("subject"),
                                                         bank_ifsc=was.get("bank_ifsc"), bank_account_last4=was.get("bank_account_last4")))


async def on_transfer_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    """Form 13: the previous member ID's shares move to the current one."""
    p = event["payload"]
    offices = dict((await session.execute(select(accounts.c.account_link_id, accounts.c.office_id).where(
        accounts.c.account_link_id.in_((p["from_account_link_id"], p["to_account_link_id"]))))).all())
    if not (await session.execute(select(annexure_k_files.c.annexure_id).where(annexure_k_files.c.annexure_id == p["transfer_id"]))).first():
        await session.execute(insert(annexure_k_files).values(       # ANNEXURE K FILE, outward and inward (P2.5c)
            annexure_id=p["transfer_id"], uan=p["uan"], from_account_link_id=p["from_account_link_id"], to_account_link_id=p["to_account_link_id"],
            from_office_id=offices.get(p["from_account_link_id"], "-"), to_office_id=offices.get(p["to_account_link_id"], "-"),
            employee_paise=int(p["employee_paise"]), employer_paise=int(p["employer_paise"]), reco_status="PENDING"))
    for link, sign in ((p["from_account_link_id"], -1), (p["to_account_link_id"], 1)):
        await session.execute(update(accounts).where(accounts.c.account_link_id == link).values(
            employee_paise=accounts.c.employee_paise + sign * int(p["employee_paise"]),
            employer_paise=accounts.c.employer_paise + sign * int(p["employer_paise"])))
    await session.execute(update(auto_transfers).where(auto_transfers.c.transfer_id == p["transfer_id"]).values(   # P2.8b
        state="POSTED", posted_at=datetime.now(UTC)))


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
    rejecting = p.get("recommendation") == "REJECT"
    if decision == "RECOMMEND":
        await transition(session, claim, "RECOMMENDED", role,
                          "Reviewed; recommended for rejection." if rejecting else "Reviewed and recommended for approval.", recommended=True)
    elif decision == "RETURN":
        await transition(session, claim, "UNDER_REVIEW", role, f"Returned for rework: {reason}")
    elif decision == "REJECT":
        claim = await transition(session, claim, "REJECTED_WITH_REASON", role, f"Rejected: {reason}", decision_reason=reason)
        await record_decision(session, claim, "REJECTED", "OFFICER_REJECTED", cid)
        await notify(session, claim, "CLAIM_REJECTED", cid, reason=reason)
    elif p["final"] and claim["claim_type"] == "DEATH_EDLI":   # P2.8c: the EDLI section decides the benefit
        await transition(session, claim, "PENDING_EDLI_DECISION", role,
                         "Admitted; sent to the EDLI section to verify the wages and decide the benefit.", decision_reason=reason)
    elif p["final"]:
        claim = await transition(session, claim, "APPROVED", role, "Approved.", decision_reason=reason)
        await record_decision(session, claim, "APPROVED", "OFFICER_APPROVED", cid)
        await notify(session, claim, "CLAIM_APPROVED", cid)
    else:
        await transition(session, claim, "AWAITING_NEXT_APPROVAL", role,
                         "Rejection recommended at this level; sent to the next approver." if rejecting
                         else "Approved at this level; sent to the next approver.")


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
        if claim.get("death_of_uan"):                          # each beneficiary gets their share, less any legacy settlement
            await record_disbursements(session, claim)
        await notify(session, claim, "CLAIM_SETTLED", cid,        # a re-payment goes to the corrected account; the net of TDS is paid
                     **({"bank_account_last4": claim["payee_account_last4"]} if claim.get("payee_account_last4") else {}),
                     **({"amount_paise": claim["tax"]["net_paise"], "tds_paise": claim["tax"]["tds_paise"]} if claim.get("tax") else {}))
    else:
        claim = await transition(session, claim, "PAYMENT_RETURNED", "bank",
                                 f"The bank returned the payment ({p.get('return_reason')}).")
        await notify(session, claim, "CLAIM_PAYMENT_RETURNED", cid, reason=p.get("return_reason"))


async def record_disbursements(session: AsyncSession, claim: dict[str, Any]) -> None:
    net = (claim.get("tax") or {}).get("net_paise", claim["amount_paise"])
    for b in (await session.execute(select(claim_beneficiaries).where(claim_beneficiaries.c.claim_id == claim["claim_id"]))).mappings().all():
        await session.execute(update(claim_beneficiaries).where(claim_beneficiaries.c.beneficiary_id == b["beneficiary_id"]).values(
            disbursed_paise=max(0, net * b["share_bp"] // 10_000 - b["legacy_settled_paise"])))


async def on_member_death(session: AsyncSession, event: dict[str, Any]) -> None:
    """An exit marked for death in service records the date of death on the member's accounts."""
    p = event["payload"]
    if p.get("reason") == "DEATH_IN_SERVICE":
        await session.execute(update(accounts).where(accounts.c.uan == p["uan"]).values(deceased_on=date.fromisoformat(p["date_of_exit"])))


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
    """A reversing journal (a rejected claim's debit, a contribution, a transfer recredit, an Appendix E): member
    lines credited add to the balance, lines debited take from it."""
    p = event["payload"]
    await _member_lines(session, [x for x in p["postings"] if x["side"] == "credit"], +1)
    await _member_lines(session, [x for x in p["postings"] if x["side"] == "debit"], -1)
    if p.get("claim_id"):
        await session.execute(update(claims).where(claims.c.claim_id == p["claim_id"]).values(debit_journal_id=None))


async def on_ledger_adjusted(session: AsyncSession, event: dict[str, Any]) -> None:
    """Appendix E posted: the member ID's balances move by its lines."""
    await on_ledger_reversed(session, {**event, "payload": {**event["payload"], "claim_id": ""}})


async def on_primary_changed(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.7d: the member's primary member ID (and Aadhaar-verified set) as member-service works it out."""
    p = event["payload"]
    key = ",".join(sorted(p["set_uans"]))
    await session.execute(update(accounts).where(accounts.c.uan.in_(p["set_uans"])).values(
        is_primary=accounts.c.account_link_id == p["primary_account_link_id"], set_key=key))


HANDLERS = {
    "PrimaryMemberIdChanged.v1": on_primary_changed,
    "LedgerReversed.v1": on_ledger_reversed,
    "LedgerAdjusted.v1": on_ledger_adjusted,
    "PolicyPublished.v1": on_policy_published,
    "AccountFrozen.v1": on_freeze,
    "AccountDefrozen.v1": on_freeze,
    "RiskSignalRaised.v1": on_risk_signal,
    "RiskSignalReviewed.v1": on_risk_signal,
    "ContributionPosted.v1": on_contribution_posted,
    "InterestCredited.v1": on_interest_credited,
    "MemberExitMarked.v1": on_member_exit,
    "TransferPosted.v1": on_transfer_posted,
    "MemberRegistered.v1": on_member_registered,
    "MemberKycUpdated.v1": on_kyc_updated,
    "NominationRegistered.v1": on_nomination,
    "ClaimDebitPosted.v1": on_claim_debit_posted,
    "CaseDecisionSubmitted.v1": on_case_decision,
    "PaymentConfirmed.v1": on_payment_result,
    "PaymentReturned.v1": on_payment_result,
}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)
