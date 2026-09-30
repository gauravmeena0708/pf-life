"""intelligence-service: advisory risk signals from security events, and their human review (Journey D2–D4).

AI endpoints (/ai/*) are Journey E and still answer from the generated stubs."""
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ai_routes import AI_HANDLERS
from app.domain.risk import (EXPLANATIONS, MEMBER_REPORT, RULE_VERSION, SHARED_DEVICE_MIN_SUBJECTS, TAKEOVER,
                             shared_device_context, takeover_evidence)
from app.infra.db import sessions
from app.infra.tables import risk_signals, security_events
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import on_policy_published

router = APIRouter()
PRODUCER = "intelligence-service"
CAIU = require_stakeholder("ho.caiu")
OUTCOMES = {"confirmed": "CONFIRMED", "benign": "BENIGN", "needs-more-evidence": "NEEDS_MORE_EVIDENCE"}
OPEN = ("OPEN", "NEEDS_MORE_EVIDENCE")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _subjects_on_device(session: AsyncSession, device: str) -> int:
    return (await session.execute(select(func.count(func.distinct(security_events.c.subject))).where(
        security_events.c.device == device))).scalar_one()


async def _raise(session: AsyncSession, subject: str, detection: str, evidence: list[str], context: dict[str, Any],
                 correlation_id: str) -> None:
    already = (await session.execute(select(risk_signals.c.signal_id).where(
        risk_signals.c.subject == subject, risk_signals.c.detection_type == detection,
        risk_signals.c.status.in_(OPEN)))).first()
    if already:
        return
    signal_id = f"RSK-{secrets.token_hex(4).upper()}"
    await session.execute(insert(risk_signals).values(
        signal_id=signal_id, subject=subject, detection_type=detection, rule_version=RULE_VERSION,
        evidence_refs=evidence, explanation=EXPLANATIONS[detection], context=context, status="OPEN"))
    await add_event(session, producer=PRODUCER, event_type="RiskSignalRaised.v1", aggregate_type="risk_signal",
                    aggregate_id=signal_id, correlation_id=correlation_id, payload={
                        "signal_id": signal_id, "detection_type": detection, "rule_version": RULE_VERSION,
                        "evidence_refs": evidence, "subject_ref": subject, "explanation": EXPLANATIONS[detection]})


async def on_security_event(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")) if event.get("occurred_at") else datetime.now(UTC)
    if not (await session.execute(select(security_events.c.id).where(security_events.c.event_id == event["event_id"]))).first():
        await session.execute(insert(security_events).values(event_id=event["event_id"], subject=p["subject"],
                                                             event_type=p["event_type"], device=p["device_fingerprint_hash"], at=at))
    rows = (await session.execute(select(security_events).where(security_events.c.subject == p["subject"]))).mappings().all()
    events = [{**dict(r), "at": _utc(r["at"])} for r in rows]
    context = shared_device_context(await _subjects_on_device(session, p["device_fingerprint_hash"])) or {}
    if p["event_type"] == "MEMBER_SECURITY_REPORT":
        await _raise(session, p["subject"], MEMBER_REPORT, [event["event_id"]], context, event["correlation_id"])
    cited = {ref for (refs,) in (await session.execute(select(risk_signals.c.evidence_refs).where(
        risk_signals.c.subject == p["subject"], risk_signals.c.detection_type == TAKEOVER))).all() for ref in refs}
    evidence = takeover_evidence(events, at, cited)
    if evidence:
        await _raise(session, p["subject"], TAKEOVER, evidence, context, event["correlation_id"])


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] == "StaffPostingChanged.v1":           # HR re-posted an officer (P2.8e)
        from app.infra.tables import office_staff
        from epfo_persistence.postings import apply_posting
        await apply_posting(session, event, office_staff)
        return
    if event["event_type"] == "SecurityEventRecorded.v1":
        await on_security_event(session, event)
    elif event["event_type"] == "PolicyPublished.v1":
        await on_policy_published(session, event)
    elif event["event_type"] in AI_HANDLERS:
        await AI_HANDLERS[event["event_type"]](session, event)


BINDINGS = ["audit-service.SecurityEventRecorded.v1", "claim-service.ClaimSubmitted.v1",
            "workflow-service.CaseDecisionSubmitted.v1", "grievance-service.GrievanceRegistered.v1",
            "platform-service.PolicyPublished.v1", "workflow-service.StaffPostingChanged.v1"]


def _signal(r: Any) -> dict[str, Any]:
    return {"signal_id": r["signal_id"], "subject_ref": r["subject"], "detection_type": r["detection_type"],
            "rule_version": r["rule_version"], "evidence_refs": r["evidence_refs"], "explanation": r["explanation"],
            "context": r["context"], "status": r["status"], "review_note": r["review_note"],
            "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None, "advisory_only": True}


@router.get("/api/v1/caiu/synthetic-risk-signals")
async def list_signals(actor: Actor = Depends(CAIU), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(risk_signals).order_by(risk_signals.c.created_at.desc()))).mappings().all()
    shared = (await session.execute(select(security_events.c.device, func.count(func.distinct(security_events.c.subject)))
                                    .group_by(security_events.c.device)
                                    .having(func.count(func.distinct(security_events.c.subject)) >= SHARED_DEVICE_MIN_SUBJECTS))).all()
    return envelope({"rule_version": RULE_VERSION, "signals": [_signal(r) for r in rows],
                     "shared_devices_not_signals": [{"device": device[:8], "subjects": n,
                                                     **shared_device_context(n)} for device, n in shared]})


class ReviewInput(BaseModel):
    outcome: str                                           # confirmed | benign | needs-more-evidence
    note: str = Field(min_length=10, max_length=2000)


@router.post("/api/v1/caiu/synthetic-risk-signals/{signal_id}/reviews")
async def review(signal_id: str, body: ReviewInput, actor: Actor = Depends(CAIU), session: AsyncSession = Depends(db)) -> dict:
    outcome = OUTCOMES.get(body.outcome.lower())
    if not outcome:
        raise Problem(422, "/problems/validation", "outcome must be confirmed, benign or needs-more-evidence")
    async with session.begin():
        r = (await session.execute(select(risk_signals).where(risk_signals.c.signal_id == signal_id))).mappings().first()
        if not r:
            raise Problem(404, "/problems/not-found", "Signal not found")
        if r["status"] not in OPEN:
            raise Problem(409, "/problems/already-reviewed", "This signal already has a final review",
                          f"Recorded outcome: {r['status']}.")
        await session.execute(update(risk_signals).where(risk_signals.c.signal_id == signal_id).values(
            status=outcome, review_note=body.note, reviewer_subject=actor.subject, reviewed_at=datetime.now(UTC)))
        await add_event(session, producer=PRODUCER, event_type="RiskSignalReviewed.v1", aggregate_type="risk_signal",
                        aggregate_id=signal_id, correlation_id=actor.correlation_id, payload={
                            "signal_id": signal_id, "subject_ref": r["subject"], "outcome": outcome})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="risk.review",
                    target_type="risk_signal", target_id=signal_id, detail=outcome)
        r = (await session.execute(select(risk_signals).where(risk_signals.c.signal_id == signal_id))).mappings().one()
    # A review records a human judgement only. Nothing here freezes an account, rejects a claim or accuses anyone;
    # any follow-up (vigilance referral, member contact) is a separate, deliberate action.
    return envelope({**_signal(r), "automatic_actions": []})
