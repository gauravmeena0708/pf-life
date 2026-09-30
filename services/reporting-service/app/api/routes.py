"""reporting-service: tier-3 read models (ADR-0005) built only from events; no service database is ever read.

Grievance pendency (Journey C5), claims and contributions monitoring, data freshness per event source,
public statistics with small-number suppression, and the zone dashboard."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import claim_facts, contribution_facts, event_freshness, grievance_facts
from epfo_auth import Actor, require_stakeholder
from epfo_observability import envelope

router = APIRouter()
MONITORS = require_stakeholder("fo.rpfc1", "ho.cpfc", "ho.customer_service", "zo.acc")
CLAIM_MONITORS = require_stakeholder("fo.oic", "fo.rpfc1", "gov.mole", "gov.peic", "ho.acc_hq", "ho.cpfc", "ho.edli", "ho.pension")
CONTRIBUTION_MONITORS = require_stakeholder("fo.rpfc1", "gov.mole", "ho.cpfc")
FRESHNESS_MONITORS = require_stakeholder("ho.cpfc")
PUBLIC = require_stakeholder("public", "gov.mole")
ZONE = require_stakeholder("zo.acc")

CLAIM_SOURCE = ["ClaimSubmitted.v1", "ClaimDecisionRecorded.v1", "PaymentConfirmed.v1", "PaymentReturned.v1"]
CONTRIBUTION_SOURCE = ["ECRValidated.v1", "ECRSubmitted.v1", "PaymentConfirmed.v1", "ContributionPosted.v1"]
GRIEVANCE_SOURCE = ["GrievanceRegistered.v1", "GrievanceEscalated.v1", "GrievanceResolved.v1"]


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _at(event: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")) if event.get("occurred_at") else datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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


async def on_claim_submitted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if (await session.execute(select(claim_facts.c.claim_id).where(claim_facts.c.claim_id == p["claim_id"]))).first():
        return
    await session.execute(insert(claim_facts).values(
        claim_id=p["claim_id"], office_id=p["office_id"], form_type=p["form_type"],
        amount_paise=p["amount_paise"], route=p["route"], submitted_at=_at(event)))


async def on_claim_decision(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(claim_facts).where(
        claim_facts.c.claim_id == p["claim_id"], claim_facts.c.decided_at.is_(None)
    ).values(decided_at=_at(event), decision=p["decision"]))


async def on_payment_confirmed(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["purpose"] == "CLAIM_SETTLEMENT":
        await session.execute(update(claim_facts).where(
            claim_facts.c.claim_id == p["reference_id"], claim_facts.c.settled_at.is_(None)
        ).values(settled_at=_at(event)))
    elif p["purpose"] == "CHALLAN":
        await session.execute(update(contribution_facts).where(
            contribution_facts.c.trrn == p["reference_id"], contribution_facts.c.paid_at.is_(None)
        ).values(paid_at=_at(event)))


async def on_payment_returned(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["purpose"] == "CLAIM_SETTLEMENT":
        await session.execute(update(claim_facts).where(claim_facts.c.claim_id == p["reference"]).values(
            returned_count=claim_facts.c.returned_count + 1))


async def on_ecr_validated(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    row = (await session.execute(select(contribution_facts.c.wage_month).where(
        contribution_facts.c.filing_id == p["filing_id"]))).first()
    if row is None:
        await session.execute(insert(contribution_facts).values(
            filing_id=p["filing_id"], establishment_id=p["establishment_id"], wage_month=p["wage_month"]))
    elif row.wage_month is None:
        await session.execute(update(contribution_facts).where(
            contribution_facts.c.filing_id == p["filing_id"]).values(wage_month=p["wage_month"]))


async def on_ecr_submitted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    row = (await session.execute(select(contribution_facts.c.submitted_at).where(
        contribution_facts.c.filing_id == p["filing_id"]))).first()
    if row is None:
        await session.execute(insert(contribution_facts).values(
            filing_id=p["filing_id"], establishment_id=p["establishment_id"], trrn=p["trrn"],
            total_paise=p["total_paise"], submitted_at=_at(event)))
    elif row.submitted_at is None:
        await session.execute(update(contribution_facts).where(
            contribution_facts.c.filing_id == p["filing_id"]
        ).values(trrn=p["trrn"], total_paise=p["total_paise"], submitted_at=_at(event)))


async def on_contribution_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(contribution_facts).where(
        contribution_facts.c.filing_id == p["filing_id"], contribution_facts.c.posted_at.is_(None)
    ).values(posted_at=_at(event), wage_month=p["wage_month"]))


async def on_observed(session: AsyncSession, event: dict[str, Any]) -> None:
    """Some sources contribute to freshness without adding a fact column."""


async def update_freshness(session: AsyncSession, event: dict[str, Any]) -> None:
    source = event.get("producer") or EVENT_PRODUCERS[event["event_type"]]
    at = _at(event)
    row = (await session.execute(select(event_freshness).where(event_freshness.c.source == source))).mappings().first()
    if row is None:
        await session.execute(insert(event_freshness).values(
            source=source, last_event_type=event["event_type"], last_event_at=at, events_seen=1))
    else:
        values: dict[str, Any] = {"events_seen": row["events_seen"] + 1}
        if at >= _utc(row["last_event_at"]):
            values.update(last_event_type=event["event_type"], last_event_at=at)
        await session.execute(update(event_freshness).where(event_freshness.c.source == source).values(**values))


async def on_staff_posting(session: AsyncSession, event: dict[str, Any]) -> None:
    """HR re-posted an officer (P2.8e): the district dashboard follows the officer's office."""
    from app.infra.tables import office_staff
    from epfo_persistence.postings import apply_posting
    await apply_posting(session, event, office_staff)


HANDLERS = {
    "GrievanceRegistered.v1": on_grievance_registered,
    "GrievanceEscalated.v1": on_grievance_escalated,
    "GrievanceResolved.v1": on_grievance_resolved,
    "ClaimSubmitted.v1": on_claim_submitted,
    "ClaimDecisionRecorded.v1": on_claim_decision,
    "PaymentConfirmed.v1": on_payment_confirmed,
    "PaymentReturned.v1": on_payment_returned,
    "ECRValidated.v1": on_ecr_validated,
    "ECRSubmitted.v1": on_ecr_submitted,
    "ContributionPosted.v1": on_contribution_posted,
    "CaseDecisionSubmitted.v1": on_observed,
    "RiskSignalRaised.v1": on_observed,
    "StaffPostingChanged.v1": on_staff_posting,
}
EVENT_PRODUCERS = {
    **{name: "grievance-service" for name in GRIEVANCE_SOURCE},
    **{name: "claim-service" for name in ("ClaimSubmitted.v1", "ClaimDecisionRecorded.v1")},
    **{name: "payment-simulator" for name in ("PaymentConfirmed.v1", "PaymentReturned.v1")},
    **{name: "contribution-service" for name in ("ECRValidated.v1", "ECRSubmitted.v1", "ContributionPosted.v1")},
    "CaseDecisionSubmitted.v1": "workflow-service",
    "RiskSignalRaised.v1": "intelligence-service",
    "StaffPostingChanged.v1": "workflow-service",
}
BINDINGS = [f"{EVENT_PRODUCERS[name]}.{name}" for name in HANDLERS]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event["event_type"])
    if handler:
        await handler(session, event)
        await update_freshness(session, event)


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
                     "source": GRIEVANCE_SOURCE})


def _claim_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled_days = [(_utc(r["settled_at"]) - _utc(r["submitted_at"])).total_seconds() / 86400
                    for r in rows if r["settled_at"] is not None]
    pending_by_form: dict[str, int] = {}
    for row in rows:
        if row["decision"] is None:
            form = row["form_type"]
            pending_by_form[form] = pending_by_form.get(form, 0) + 1
    return {
        "submitted": len(rows),
        "auto_approved": sum(r["decision"] == "AUTO_APPROVED" for r in rows),
        "under_officer_review": sum(r["route"] == "REVIEW" and r["decision"] is None for r in rows),
        "approved": sum(r["decision"] == "APPROVED" for r in rows),
        "rejected": sum(r["decision"] == "REJECTED" for r in rows),
        "settled": sum(r["settled_at"] is not None for r in rows),
        "payment_returns": sum(r["returned_count"] for r in rows),
        "median_days_to_settle": median(settled_days) if settled_days else None,
        "pending_by_form": dict(sorted(pending_by_form.items())),
    }


async def _claim_offices(session: AsyncSession, office_ids: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [dict(row) for row in (await session.execute(select(claim_facts))).mappings()]
    if office_ids is not None:
        rows = [row for row in rows if row["office_id"] in office_ids]
    offices = sorted(office_ids if office_ids is not None else {row["office_id"] for row in rows})
    return ([{"office_id": office_id, **_claim_summary([r for r in rows if r["office_id"] == office_id])}
             for office_id in offices], _claim_summary(rows))


@router.get("/api/v1/monitoring/claims")
async def claim_monitoring(actor: Actor = Depends(CLAIM_MONITORS), session: AsyncSession = Depends(db)) -> dict:
    offices, totals = await _claim_offices(session)
    return envelope({"as_of": datetime.now(UTC).isoformat(), "offices": offices, "totals": totals,
                     "source": CLAIM_SOURCE})


def _contribution_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    filed = [row for row in rows if row["submitted_at"] is not None]
    return {
        "returns_filed": len(filed),
        "amount_due_paise": sum(row["total_paise"] or 0 for row in filed),
        "amount_paid_paise": sum(row["total_paise"] or 0 for row in filed if row["paid_at"] is not None),
        "posted": sum(row["posted_at"] is not None for row in filed),
        "pending_payment": sum(row["paid_at"] is None for row in filed),
    }


@router.get("/api/v1/monitoring/contributions")
async def contribution_monitoring(actor: Actor = Depends(CONTRIBUTION_MONITORS),
                                  session: AsyncSession = Depends(db)) -> dict:
    rows = [dict(row) for row in (await session.execute(select(contribution_facts))).mappings()]
    months = sorted({row["wage_month"] for row in rows if row["submitted_at"] is not None},
                    key=lambda value: value or "")
    by_month = [{"wage_month": month, **_contribution_summary([r for r in rows if r["wage_month"] == month])}
                for month in months]
    return envelope({"as_of": datetime.now(UTC).isoformat(), "wage_months": by_month,
                     "totals": _contribution_summary(rows), "source": CONTRIBUTION_SOURCE})


@router.get("/api/v1/monitoring/data-freshness")
async def data_freshness(actor: Actor = Depends(FRESHNESS_MONITORS), session: AsyncSession = Depends(db)) -> dict:
    now = datetime.now(UTC)
    rows = (await session.execute(select(event_freshness).order_by(event_freshness.c.source))).mappings()
    sources = []
    for row in rows:
        lag = max(0, (now - _utc(row["last_event_at"])).total_seconds())
        sources.append({"source": row["source"], "last_event_type": row["last_event_type"],
                        "last_event_at": _utc(row["last_event_at"]).isoformat(),
                        "events_seen": row["events_seen"], "lag_seconds": lag,
                        "status": "fresh" if lag < 900 else "stale"})
    return envelope({"as_of": now.isoformat(), "sources": sources, "source": list(HANDLERS)})


@router.get("/api/v1/public/statistics")
async def public_statistics(actor: Actor = Depends(PUBLIC), session: AsyncSession = Depends(db)) -> dict:
    claims_settled = (await session.execute(select(func.count()).select_from(claim_facts).where(
        claim_facts.c.settled_at.is_not(None)))).scalar_one()
    posted = (await session.execute(select(func.count(), func.sum(contribution_facts.c.total_paise)).where(
        contribution_facts.c.posted_at.is_not(None)))).one()
    grievances_resolved = (await session.execute(select(func.count()).select_from(grievance_facts).where(
        grievance_facts.c.resolved_at.is_not(None)))).scalar_one()
    suppressed = {"claims_settled": claims_settled < 5,
                  "contributions_posted_paise": posted[0] < 5,
                  "grievances_resolved": grievances_resolved < 5}
    return envelope({
        "claims_settled": None if suppressed["claims_settled"] else claims_settled,
        "contributions_posted_paise": None if suppressed["contributions_posted_paise"] else int(posted[1] or 0),
        "grievances_resolved": None if suppressed["grievances_resolved"] else grievances_resolved,
        "suppressed": suppressed,
        "note": "Counts below 5 are suppressed; the contribution amount is suppressed when fewer than 5 returns are posted.",
        "as_of": datetime.now(UTC).isoformat(),
        "source": list(dict.fromkeys(CLAIM_SOURCE + CONTRIBUTION_SOURCE + GRIEVANCE_SOURCE)),
    })


def _office_zone() -> dict[str, str]:
    configured = Path(os.getenv("SEED_FILE", "/srv/seed/synthetic.json"))
    # The repository path exists only when running from a checkout (tests); the image has /srv/seed.
    path = configured if configured.is_file() else Path(__file__).resolve().parents[4] / "scripts" / "seed" / "synthetic.json"
    with path.open(encoding="utf-8") as seed_file:
        office = json.load(seed_file)["office"]
    return {office["office_id"]: office["zone_id"]}


@router.get("/api/v1/zo/dashboards")
async def zone_dashboard(actor: Actor = Depends(ZONE), session: AsyncSession = Depends(db)) -> dict:
    mapping = _office_zone()
    zone_id = actor.claims.get("office_id") or next(iter(mapping.values()))
    office_ids = {office for office, zone in mapping.items() if zone == zone_id}
    claims, claim_totals = await _claim_offices(session, office_ids)
    g = grievance_facts.c
    grievance_rows = (await session.execute(select(g.office_id, g.grievance_id, g.resolved_at, g.escalations,
                                                  g.within_sla).where(g.office_id.in_(office_ids)))).mappings().all()
    grievance_offices = []
    for office_id in sorted(office_ids):
        rows = [r for r in grievance_rows if r["office_id"] == office_id]
        resolved = sum(r["resolved_at"] is not None for r in rows)
        grievance_offices.append({"office_id": office_id, "registered": len(rows), "resolved": resolved,
                                  "pending": len(rows) - resolved,
                                  "escalations": sum(r["escalations"] for r in rows),
                                  "resolved_within_sla_pct": round(100 * sum(r["within_sla"] is True for r in rows) / resolved)
                                  if resolved else None})
    return envelope({"zone_id": zone_id, "claims": {"offices": claims, "totals": claim_totals},
                     "grievances": {"offices": grievance_offices}, "as_of": datetime.now(UTC).isoformat(),
                     "source": list(dict.fromkeys(CLAIM_SOURCE + GRIEVANCE_SOURCE))})
