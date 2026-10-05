"""Public citizen's charter and privacy-protected office performance."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.domain.standards import performance
from app.infra.tables import claim_facts, grievance_facts, service_standards
from epfo_auth import Actor, require_stakeholder
from epfo_observability import envelope

router = APIRouter()
PUBLIC = require_stakeholder("public", "gov.mole")


def now() -> datetime:
    return datetime.now(UTC)


@router.get("/api/v1/public/service-standards")
async def public_service_standards(days: int = Query(30, ge=1, le=365),
                                   office_id: str | None = None,
                                   actor: Actor = Depends(PUBLIC),
                                   session: AsyncSession = Depends(db)) -> dict:
    as_of = now()
    standards = (await session.execute(select(service_standards).order_by(service_standards.c.code))).mappings().all()
    claims = (await session.execute(select(claim_facts))).mappings().all()
    grievances = (await session.execute(select(grievance_facts))).mappings().all()
    office_ids = {row["office_id"] for row in claims + grievances if row["office_id"]}
    if office_id:
        office_ids &= {office_id}

    def rows_for(standard: dict, office: str) -> list:
        if standard["code"] == "GRIEVANCE":
            return [row for row in grievances if row["office_id"] == office]
        return [row for row in claims if row["office_id"] == office and row["decision"] != "REJECTED" and
                (standard["code"] != "AUTO_CLAIM" or row["route"] == "AUTO")]

    offices = []
    for office in sorted(office_ids):
        results = []
        for row in standards:
            standard = dict(row)
            if row["code"] == "TRANSFER":
                results.append({**standard, "availability": "NO_READ_MODEL", "performance": None})
                continue
            is_grievance = row["code"] == "GRIEVANCE"
            measure = performance(rows_for(standard, office),
                                  start_field="registered_at" if is_grievance else "submitted_at",
                                  end_field="resolved_at" if is_grievance else "settled_at",
                                  days=row["days"], as_of=as_of, period_days=days)
            results.append({**standard, "availability": "AVAILABLE" if measure else "SUPPRESSED",
                            "performance": measure})
        offices.append({"office_id": office, "standards": results})
    charter = [{**dict(row), "availability": "NO_READ_MODEL" if row["code"] == "TRANSFER" else "NO_DATA",
                "performance": None} for row in standards]
    return envelope({"as_of": as_of.isoformat(), "period_days": days, "standards": charter,
                     "offices": offices, "suppression_threshold": 10,
                     "note": "Synthetic demonstration. Completed cases are grouped by completion date; "
                             "overdue open cases started within the period. Met means all completed cases "
                             "finished within the standard. Groups and positive open counts below 10 are hidden. "
                             "Transfer timing has no reporting read model."})
