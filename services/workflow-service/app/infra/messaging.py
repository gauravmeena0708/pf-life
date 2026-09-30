"""Events workflow-service consumes: claims open cases; payment results move the cash-section task."""
from datetime import date
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import grievance_case, last_decision, open_case
from app.infra.tables import cases, claim_dockets, member_accounts, subject_offices
from epfo_persistence.policy import after_defreeze_chain, approval_chain, on_policy_published, rules_by_version

BINDINGS = [
    "claim-service.ClaimSubmitted.v1",
    "claim-service.ClaimDecisionRecorded.v1",
    "claim-service.PaymentInstructed.v1",
    "payment-simulator.PaymentConfirmed.v1",
    "payment-simulator.PaymentReturned.v1",
    "grievance-service.GrievanceRegistered.v1",
    "grievance-service.GrievanceEscalated.v1",
    "grievance-service.GrievanceResolved.v1",
    "platform-service.PolicyPublished.v1",
    "claim-service.ClaimStateChanged.v1",
    "member-service.MemberExitMarked.v1",
    "contribution-service.TransferPosted.v1",
    "member-service.MemberRegistered.v1",
    "claim-service.CADGenerated.v1",
    "contribution-service.LedgerReversed.v1",
    "member-service.PrimaryMemberIdChanged.v1",
]


async def _move(session: AsyncSession, claim_id: str, from_states: tuple[str, ...], **values: Any) -> None:
    await session.execute(update(cases).where(cases.c.claim_id == claim_id, cases.c.state.in_(from_states))
                          .values(version=cases.c.version + 1, **values))


async def on_claim_submitted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await open_case(session, p, "IN_REVIEW" if p["route"] == "REVIEW" else "AUTO_PENDING")


async def on_claim_decision(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["decision"] == "AUTO_APPROVED":
        if not (await session.execute(select(cases.c.case_id).where(cases.c.claim_id == p["claim_id"]))).first():
            raise LookupError(f"case for {p['claim_id']} not opened yet")   # retried until ClaimSubmitted.v1 is applied
        await _move(session, p["claim_id"], ("AUTO_PENDING",), state="AWAITING_PAYMENT", current_role="fo.cash")


async def on_payment_instructed(session: AsyncSession, event: dict[str, Any]) -> None:
    await _move(session, event["payload"]["claim_id"], ("AWAITING_PAYMENT", "PAYMENT_RETURNED"),
                state="PAYMENT_ISSUED", current_role=None)


async def on_payment_result(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p.get("purpose") != "CLAIM_SETTLEMENT":
        return
    if event["event_type"] == "PaymentConfirmed.v1":
        await _move(session, p["reference_id"], ("PAYMENT_ISSUED",), state="CLOSED", current_role=None)
    else:                                   # returned: the member corrects the bank details first (nobody's queue)
        await _move(session, p["reference"], ("PAYMENT_ISSUED",), state="RETURNED_AWAITING_MEMBER", current_role=None)


async def on_claim_state(session: AsyncSession, event: dict[str, Any]) -> None:
    """Keep the case in step with the claim (init.md §7): holds, de-freeze restarts, re-disbursement."""
    p = event["payload"]
    row = (await session.execute(select(cases).where(cases.c.claim_id == p["claim_id"]))).mappings().first()
    if not row:
        return
    case, to, reason = dict(row), p["to_state"], p["reason"]
    if to == "ON_HOLD_FROZEN":
        held = {"state": case["state"], "current_role": case["current_role"]}
        await _set(session, case, state="ON_HOLD", current_role=None, data={**(case["data"] or {}), "held_from": held})
    elif reason == "DEFROZEN_APPROVALS_VOID":
        rules = await rules_by_version(session, p["rule_version"])
        chain = after_defreeze_chain(rules, int(p["amount_paise"]))
        await _set(session, case, state="IN_REVIEW", chain=chain, step=0, round=case["round"] + 1, current_role=chain[0])
    elif reason == "DEFROZEN_RESUBMITTED":
        await _set(session, case, state="AUTO_PENDING", current_role=None)
    elif reason == "DEFROZEN_REVIEW":
        rules = await rules_by_version(session, p["rule_version"])
        chain = approval_chain(rules, p["claim_type"], int(p["amount_paise"]))
        await _set(session, case, state="IN_REVIEW", chain=chain, step=0, round=case["round"] + 1, current_role=chain[0])
    elif reason == "DEFROZEN_RESUMED":
        held = (case["data"] or {}).get("held_from") or {}
        await _set(session, case, state=held.get("state", "IN_REVIEW"), current_role=held.get("current_role"))
    elif to == "CORRECTION_PENDING":
        await _set(session, case, state="REDISBURSEMENT_REVIEW", current_role="fo.apfc")
    elif to == "REISSUE_APPROVED":
        await _set(session, case, state="PAYMENT_RETURNED", current_role="fo.cash")
    elif to == "PAYMENT_RETURNED" and p["from_state"] == "CORRECTION_PENDING":
        await _set(session, case, state="RETURNED_AWAITING_MEMBER", current_role=None)
    elif to == "CANCELLED":                                     # the member withdrew it before a checker decided
        await _set(session, case, state="CLOSED", current_role=None, data={**(case["data"] or {}), "closed": "cancelled by the member"})


async def _set(session: AsyncSession, case: dict[str, Any], **values: Any) -> None:
    await session.execute(update(cases).where(cases.c.case_id == case["case_id"]).values(version=case["version"] + 1, **values))


async def on_grievance_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await grievance_case(session, p["grievance_id"], p["office_id"], "RO")


async def on_grievance_escalated(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await grievance_case(session, p["grievance_id"], p["office_id"], p["to_tier"])


async def on_grievance_resolved(session: AsyncSession, event: dict[str, Any]) -> None:
    await session.execute(update(cases).where(cases.c.grievance_id == event["payload"]["grievance_id"])
                          .values(state="CLOSED", current_role=None, version=cases.c.version + 1))


async def on_member_exit(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(member_accounts).where(member_accounts.c.account_link_id == p["account_link_id"])
                          .values(date_of_exit=date.fromisoformat(p["date_of_exit"])))


async def on_transfer_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(member_accounts).where(member_accounts.c.account_link_id == p["from_account_link_id"])
                          .values(transferred_to=p["to_account_link_id"]))


async def on_member_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    """A new UAN becomes a process subject (in the office of its establishment); every member ID an account."""
    p = event["payload"]
    here = (await session.execute(select(subject_offices).where(subject_offices.c.establishment_id == p["establishment_id"]).limit(1))).mappings().first()
    here = here or (await session.execute(select(subject_offices).limit(1))).mappings().first()
    if not (await session.execute(select(subject_offices.c.subject_ref).where(subject_offices.c.subject_ref == p["uan"]))).first():
        await session.execute(insert(subject_offices).values(subject_ref=p["uan"], office_id=here["office_id"], zone_id=here["zone_id"],
                                                             member_subject=p.get("member_subject"), establishment_id=p["establishment_id"]))
    if not (await session.execute(select(member_accounts.c.account_link_id).where(member_accounts.c.account_link_id == p["account_link_id"]))).first():
        await session.execute(insert(member_accounts).values(account_link_id=p["account_link_id"], uan=p["uan"], member_subject=p.get("member_subject"),
                                                             establishment_id=p["establishment_id"], date_of_joining=date.fromisoformat(p["date_of_joining"])))


async def on_cad_generated(session: AsyncSession, event: dict[str, Any]) -> None:
    """A Claim Approval Docket was generated: it counts for that role until the next decision on the case."""
    p = event["payload"]
    case = (await session.execute(select(cases.c.case_id).where(cases.c.claim_id == p["claim_id"]))).scalar_one_or_none()
    if not case:
        raise LookupError(f"case for {p['claim_id']} not opened yet")
    if not (await session.execute(select(claim_dockets.c.cad_id).where(claim_dockets.c.cad_id == p["cad_id"]))).first():
        await session.execute(insert(claim_dockets).values(cad_id=p["cad_id"], claim_id=p["claim_id"], officer_role=p["officer_role"],
                                                           after_action=await last_decision(session, case)))


async def on_ledger_reversed(session: AsyncSession, event: dict[str, Any]) -> None:
    """A recredited transfer: the previous member ID is no longer transferred and may be transferred again."""
    p = event["payload"]
    if p.get("reversed_kind") == "TRANSFER":
        frm = next((x["account_link_id"] for x in p["postings"] if x.get("account_link_id") and x["side"] == "credit"), None)
        if frm:
            await session.execute(update(member_accounts).where(member_accounts.c.account_link_id == frm).values(transferred_to=None))


async def on_primary_changed(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.7d: which member ID of the member's Aadhaar-verified set is primary (Form 13 transfers go to it)."""
    p = event["payload"]
    await session.execute(update(member_accounts).where(member_accounts.c.uan.in_(p["set_uans"])).values(
        is_primary=member_accounts.c.account_link_id == p["primary_account_link_id"]))


HANDLERS = {
    "PrimaryMemberIdChanged.v1": on_primary_changed,
    "LedgerReversed.v1": on_ledger_reversed,
    "CADGenerated.v1": on_cad_generated,
    "MemberRegistered.v1": on_member_registered,
    "MemberExitMarked.v1": on_member_exit,
    "TransferPosted.v1": on_transfer_posted,
    "ClaimStateChanged.v1": on_claim_state,
    "PolicyPublished.v1": on_policy_published,
    "GrievanceRegistered.v1": on_grievance_registered,
    "GrievanceEscalated.v1": on_grievance_escalated,
    "GrievanceResolved.v1": on_grievance_resolved,
    "ClaimSubmitted.v1": on_claim_submitted,
    "ClaimDecisionRecorded.v1": on_claim_decision,
    "PaymentInstructed.v1": on_payment_instructed,
    "PaymentConfirmed.v1": on_payment_result,
    "PaymentReturned.v1": on_payment_result,
}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)
