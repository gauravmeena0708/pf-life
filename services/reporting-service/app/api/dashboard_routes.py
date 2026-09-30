"""Illustrative office and employer dashboards; aggregate synthetic facts only."""
from datetime import date, timedelta
from typing import Any, Mapping

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import compliance_routes
from app.api.routes import _utc, db
from app.infra.tables import claim_facts, contribution_facts, grievance_facts, office_staff
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence.policy import baseline

router = APIRouter()
DISTRICT = require_stakeholder("do.incharge")


def today() -> date:
    return compliance_routes.today()


def _recent(row: Mapping[str, Any], field: str, as_of: date) -> bool:
    value = row[field]
    return value is not None and as_of - timedelta(days=30) <= _utc(value).date() <= as_of


@router.get("/api/v1/do/dashboards")
async def district_dashboard(actor: Actor = Depends(DISTRICT), session: AsyncSession = Depends(db)) -> dict:
    office_id = (await session.execute(select(office_staff.c.office_id).where(
        office_staff.c.subject == actor.subject,
        office_staff.c.stakeholder == actor.stakeholder))).scalar_one_or_none()
    if office_id is None:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    as_of = today()
    claims = (await session.execute(select(claim_facts).where(
        claim_facts.c.office_id == office_id))).mappings().all()
    grievances = (await session.execute(select(grievance_facts).where(
        grievance_facts.c.office_id == office_id))).mappings().all()
    facts = (await session.execute(select(contribution_facts))).mappings().all()
    by_establishment: dict[str, list[Mapping[str, Any]]] = {}
    for row in facts:
        by_establishment.setdefault(row["establishment_id"], []).append(row)
    defaulting = paid_late = 0
    for rows in by_establishment.values():
        months, _ = compliance_routes._evaluate(rows, as_of)
        defaulting += any(m["status"] in ("NOT_FILED", "FILED_NOT_PAID") for m in months)
        paid_late += sum(m["status"] == "PAID_LATE" for m in months[-12:])
    # Match the existing claim monitoring read: pending means no decision recorded.
    pending = [row for row in claims if row["decision"] is None]
    sla_cutoff = as_of - timedelta(days=baseline()["claims"]["settlement_sla_days"])
    resolved = [row for row in grievances if row["resolved_at"] is not None]
    return envelope({
        "office_id": office_id, "as_of": as_of.isoformat(),
        "claims": {"pending": len(pending),
                   "settled_last_30_days": sum(_recent(r, "settled_at", as_of) for r in claims),
                   "pending_over_sla": sum(_utc(r["submitted_at"]).date() < sla_cutoff for r in pending),
                   "returned_payments": sum(r["returned_count"] for r in claims)},
        "grievances": {"open": len(grievances) - len(resolved),
                       "resolved_last_30_days": sum(_recent(r, "resolved_at", as_of) for r in grievances),
                       "resolved_within_sla_pct": round(100 * sum(r["within_sla"] is True for r in resolved) / len(resolved))
                       if len(resolved) >= 5 else None,
                       "escalated_open": sum(r["resolved_at"] is None and r["escalations"] > 0 for r in grievances)},
        "establishments": {"with_filings": len(by_establishment), "defaulting": defaulting,
                           "paid_late_last_12_months": paid_late},
        "note": "Illustrative synthetic data. Claims and grievances are scoped to the posted parent regional office. "
                "Contribution facts have no office; all are included for the single demo office. "
                "For the grievance SLA percentage, small numbers are not shown (fewer than 5 resolved); "
                "office-internal counts remain exact.",
    })


@router.get("/api/v1/employers/me/dashboard")
async def employer_dashboard(actor: Actor = Depends(compliance_routes.EMPLOYER),
                             session: AsyncSession = Depends(db)) -> dict:
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment",
                      "The actor has no establishment assigned.")
    as_of = today()
    rows = (await session.execute(select(contribution_facts).where(
        contribution_facts.c.establishment_id == actor.establishment_id))).mappings().all()
    months, _ = compliance_routes._evaluate(rows, as_of)
    alerts = []
    if months and months[-1]["status"] == "NOT_FILED":
        alerts.append({"kind": "NOT_FILED", "message": f"Return for {months[-1]['wage_month']} not filed",
                       "link": "/employer/ecr#ecr-returns"})
    for month in reversed(months[-12:]):                      # the last 12 wage months due
        if month["status"] == "FILED_NOT_PAID":
            alerts.append({"kind": "FILED_NOT_PAID", "message": f"Challan for {month['wage_month']} not paid",
                           "link": "/employer/ecr#ecr-challans"})
    paid_late = sum(m["status"] == "PAID_LATE" for m in months[-12:])
    if paid_late:
        alerts.append({"kind": "PAID_LATE",
                       "message": f"{paid_late} month(s) paid late in the last 12 — 14B/7Q demands may follow",
                       "link": "/employer/returns#demands-heading"})
    return envelope({
        "establishment_id": actor.establishment_id, "as_of": as_of.isoformat(),
        "returns": [{k: m[k] for k in ("wage_month", "status", "due_date", "paid_on")}
                    for m in reversed(months[-3:])],
        "alerts": alerts,
        "counts": {status: sum(m["status"] == status for m in months) for status in compliance_routes.STATUSES},
        "see_also": [
            {"label": "Member approvals", "link": "/employer/members#approvals-heading"},
            {"label": "KYC approvals", "link": "/employer/registration#kyc-approvals-heading"},
            {"label": "Missing details", "link": "/employer/registration#missing-heading"},
        ],
        "note": "Illustrative synthetic data. Member approvals, KYC approvals and missing-details counts "
                "are kept by member-service and shown on those pages.",
    })
