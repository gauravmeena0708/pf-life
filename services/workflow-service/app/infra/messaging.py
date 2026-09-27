"""Events workflow-service consumes: claims open cases; payment results move the cash-section task."""
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import grievance_case, open_case
from app.infra.tables import cases
from epfo_persistence.policy import on_policy_published

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
    else:
        await _move(session, p["reference"], ("PAYMENT_ISSUED",), state="PAYMENT_RETURNED", current_role="fo.cash")


async def on_grievance_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await grievance_case(session, p["grievance_id"], p["office_id"], "RO")


async def on_grievance_escalated(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await grievance_case(session, p["grievance_id"], p["office_id"], p["to_tier"])


async def on_grievance_resolved(session: AsyncSession, event: dict[str, Any]) -> None:
    await session.execute(update(cases).where(cases.c.grievance_id == event["payload"]["grievance_id"])
                          .values(state="CLOSED", current_role=None, version=cases.c.version + 1))


HANDLERS = {
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
