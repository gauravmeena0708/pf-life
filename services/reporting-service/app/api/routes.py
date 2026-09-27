"""reporting-service: read models built only from events; no service database is ever read directly.

GET /monitoring/grievances (Journey C5): pendency, escalation and resolution-within-SLA per office."""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import grievance_facts
from epfo_auth import Actor, require_stakeholder
from epfo_observability import envelope

router = APIRouter()
MONITORS = require_stakeholder("fo.rpfc1", "ho.cpfc", "ho.customer_service", "zo.acc")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _at(event: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")) if event.get("occurred_at") else datetime.now(UTC)


async def on_grievance_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if (await session.execute(select(grievance_facts.c.grievance_id).where(
            grievance_facts.c.grievance_id == p["grievance_id"]))).first():
        return
    await session.execute(insert(grievance_facts).values(grievance_id=p["grievance_id"], office_id=p["office_id"],
                                                         category=p["category"], registered_at=_at(event), tier="RO"))


async def on_grievance_escalated(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(grievance_facts).where(grievance_facts.c.grievance_id == p["grievance_id"]).values(
        tier=p["to_tier"], escalations=grievance_facts.c.escalations + 1))


async def on_grievance_resolved(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(grievance_facts).where(grievance_facts.c.grievance_id == p["grievance_id"]).values(
        resolved_at=_at(event), within_sla=p["within_sla"], tier=p["tier"]))


HANDLERS = {"GrievanceRegistered.v1": on_grievance_registered, "GrievanceEscalated.v1": on_grievance_escalated,
            "GrievanceResolved.v1": on_grievance_resolved}
BINDINGS = [f"grievance-service.{name}" for name in HANDLERS]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)


@router.get("/api/v1/monitoring/grievances")
async def grievance_monitoring(actor: Actor = Depends(MONITORS), session: AsyncSession = Depends(db)) -> dict:
    g = grievance_facts.c
    rows = (await session.execute(select(
        g.office_id, func.count().label("registered"),
        func.count(g.resolved_at).label("resolved"),
        func.sum(g.escalations).label("escalations"),
        func.count().filter(g.within_sla.is_(True)).label("within_sla"),
    ).group_by(g.office_id).order_by(g.office_id))).mappings().all()
    by_tier = (await session.execute(select(g.tier, func.count()).where(g.resolved_at.is_(None))
                                     .group_by(g.tier))).all()
    by_category = (await session.execute(select(g.category, func.count()).group_by(g.category))).all()
    offices = [{"office_id": r["office_id"], "registered": r["registered"], "resolved": r["resolved"],
                "pending": r["registered"] - r["resolved"], "escalations": int(r["escalations"] or 0),
                "resolved_within_sla_pct": round(100 * r["within_sla"] / r["resolved"]) if r["resolved"] else None}
               for r in rows]
    return envelope({"as_of": datetime.now(UTC).isoformat(), "offices": offices,
                     "pending_by_tier": {tier: n for tier, n in by_tier},
                     "by_category": {category: n for category, n in by_category},
                     "source": "events: GrievanceRegistered.v1, GrievanceEscalated.v1, GrievanceResolved.v1"})
