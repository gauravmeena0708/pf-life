"""audit-service: the append-only, hash-chained record of every domain event (Journey C5, architecture §2.8),
and the intake for security events reported by the gateway (Journey D1)."""
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import audit_log
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event

router = APIRouter()
PRODUCER = "audit-service"
GENESIS = "0" * 64
AUDITORS = require_stakeholder("ho.audit", "gov.cag", "gov.statutory_auditor", "zo.rpfc1_audit", "zo.internal_audit",
                               "ho.security")
SECURITY_EVENT_TYPES = {"LOGIN", "LOGIN_NEW_DEVICE", "CONTACT_DETAILS_CHANGED", "CLAIM_CREATED", "SESSION_REVOKED",
                        "MEMBER_SECURITY_REPORT", "ACCOUNT_RECOVERY_REQUESTED", "STEP_UP_FAILED"}


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def chain_hash(prev_hash: str, event: dict[str, Any]) -> str:
    canonical = json.dumps({k: event.get(k) for k in ("event_id", "event_type", "producer", "aggregate_type",
                                                      "aggregate_id", "correlation_id", "occurred_at", "payload")},
                           sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


async def record(session: AsyncSession, event: dict[str, Any]) -> None:
    """Consumer handler for every event on the bus (binding '#'). Runs inside the inbox transaction."""
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(7710001)"))    # one writer extends the chain at a time
    if (await session.execute(select(audit_log.c.seq).where(audit_log.c.event_id == event["event_id"]))).first():
        return
    prev = (await session.execute(select(audit_log.c.hash).order_by(audit_log.c.seq.desc()).limit(1))).scalar_one_or_none()
    prev = prev or GENESIS
    values = {"event_id": event["event_id"], "event_type": event["event_type"], "producer": event.get("producer") or "unknown",
              "aggregate_type": event.get("aggregate_type") or "unknown", "aggregate_id": str(event.get("aggregate_id") or ""),
              "correlation_id": event.get("correlation_id") or "-", "occurred_at": event.get("occurred_at") or "",
              "payload": event.get("payload") or {}}
    await session.execute(insert(audit_log).values(**values, prev_hash=prev, hash=chain_hash(prev, values)))


def _row(r: Any) -> dict[str, Any]:
    return {"seq": r["seq"], "event_id": r["event_id"], "event_type": r["event_type"], "producer": r["producer"],
            "aggregate_type": r["aggregate_type"], "aggregate_id": r["aggregate_id"],
            "correlation_id": r["correlation_id"], "occurred_at": r["occurred_at"], "payload": r["payload"],
            "prev_hash": r["prev_hash"], "hash": r["hash"]}


async def verify_chain(session: AsyncSession) -> dict[str, Any]:
    prev, count = GENESIS, 0
    for r in (await session.execute(select(audit_log).order_by(audit_log.c.seq))).mappings():
        expected = chain_hash(prev, _row(r))
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"valid": False, "broken_at_seq": r["seq"], "checked": count}
        prev, count = r["hash"], count + 1
    return {"valid": True, "checked": count, "head": prev}


@router.get("/api/v1/audit/events")
async def events(actor: Actor = Depends(AUDITORS), session: AsyncSession = Depends(db),
                 event_type: str | None = Query(default=None, max_length=120),
                 aggregate_id: str | None = Query(default=None, max_length=80),
                 after_seq: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)) -> dict:
    q = select(audit_log).where(audit_log.c.seq > after_seq)
    if event_type:
        q = q.where(audit_log.c.event_type == event_type)
    if aggregate_id:
        q = q.where(audit_log.c.aggregate_id == aggregate_id)
    rows = (await session.execute(q.order_by(audit_log.c.seq).limit(limit))).mappings().all()
    return envelope({"items": [_row(r) for r in rows], "chain": await verify_chain(session)})


@router.get("/api/v1/audit/correlations/{correlation_id}")
async def correlation(correlation_id: str, actor: Actor = Depends(AUDITORS), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(audit_log).where(audit_log.c.correlation_id == correlation_id)
                                  .order_by(audit_log.c.seq))).mappings().all()
    if not rows:
        raise Problem(404, "/problems/not-found", "No events for this correlation ID")
    return envelope({"correlation_id": correlation_id, "items": [_row(r) for r in rows]})


class SecurityEventInput(BaseModel):
    subject: str = Field(min_length=1, max_length=80)
    event_type: str
    device_fingerprint_hash: str = Field(min_length=8, max_length=64)   # a salted hash; never the raw device data
    detail: str | None = Field(default=None, max_length=300)


@router.post("/api/v1/internal/security-events", status_code=202)
async def security_event(body: SecurityEventInput, actor: Actor = Depends(require_stakeholder("system.gateway", "ho.security")),
                         session: AsyncSession = Depends(db)) -> dict:
    if body.event_type not in SECURITY_EVENT_TYPES:
        raise Problem(422, "/problems/validation", "Unknown security event type")
    async with session.begin():
        event = await add_event(session, producer=PRODUCER, event_type="SecurityEventRecorded.v1",
                                aggregate_type="security_event", aggregate_id=body.subject,
                                correlation_id=actor.correlation_id, payload={
                                    "subject": body.subject, "event_type": body.event_type,
                                    "device_fingerprint_hash": body.device_fingerprint_hash})
    return envelope({"event_id": event["event_id"], "accepted": True})
