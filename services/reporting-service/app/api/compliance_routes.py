"""Illustrative compliance reads from event-built contribution facts."""
from datetime import UTC, date, datetime
from typing import Any, Mapping

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _utc, db
from app.infra.tables import contribution_facts
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence.policy import baseline, due_date

router = APIRouter()
OFFICE = require_stakeholder("fo.da_compliance", "fo.apfc", "fo.oic")
EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")
STATUSES = ("FILED_AND_PAID_ON_TIME", "PAID_LATE", "FILED_NOT_PAID", "NOT_FILED")


def today() -> date:
    return datetime.now(UTC).date()


def _evaluate(rows: list[Mapping[str, Any]], as_of: date) -> tuple[list[dict[str, Any]], int]:
    """Evaluate overdue months; validated-only facts cannot start the history."""
    starts = [row["wage_month"] for row in rows if row["wage_month"] is not None
              and (row["submitted_at"] is not None or row["paid_at"] is not None)]
    if not starts:
        return [], 0
    by_month: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row["wage_month"] is not None:
            by_month.setdefault(row["wage_month"], []).append(row)

    year, month = map(int, min(starts).split("-"))
    rules = baseline()
    months = []
    unpaid_paise = 0
    while True:
        wage_month = f"{year:04d}-{month:02d}"
        due = due_date(wage_month, rules)
        if due >= as_of:
            break
        filings = by_month.get(wage_month, [])
        payments = [_utc(row["paid_at"]) for row in filings if row["paid_at"] is not None]
        paid_on = min(payments).date() if payments else None
        days_late = max(0, (paid_on - due).days) if paid_on is not None else 0
        status = ("NOT_FILED" if not filings else "FILED_NOT_PAID" if paid_on is None
                  else "PAID_LATE" if days_late else "FILED_AND_PAID_ON_TIME")
        months.append({"wage_month": wage_month, "due_date": due.isoformat(), "status": status,
                       "paid_on": paid_on.isoformat() if paid_on is not None else None,
                       "days_late": days_late,
                       "total_paise": sum(row["total_paise"] or 0 for row in filings)})
        unpaid_paise += sum(row["total_paise"] or 0 for row in filings if row["paid_at"] is None)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months, unpaid_paise


@router.get("/api/v1/office/compliance/defaulters")
async def defaulters(actor: Actor = Depends(OFFICE), session: AsyncSession = Depends(db)) -> dict:
    as_of = today()
    rows = (await session.execute(select(contribution_facts))).mappings().all()
    by_establishment: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_establishment.setdefault(row["establishment_id"], []).append(row)
    defaults = []
    for establishment_id, facts in by_establishment.items():
        months, unpaid_paise = _evaluate(facts, as_of)
        non_filing = [month["wage_month"] for month in months if month["status"] == "NOT_FILED"]
        non_payment = [month["wage_month"] for month in months if month["status"] == "FILED_NOT_PAID"]
        if non_filing or non_payment:
            defaults.append({
                "establishment_id": establishment_id,
                "non_filing_months": non_filing,
                "non_payment_months": non_payment,
                "unpaid_paise": unpaid_paise,
                "late_payment_months": [{"wage_month": month["wage_month"], "days_late": month["days_late"]}
                                        for month in months if month["status"] == "PAID_LATE"],
                "since": min(non_filing + non_payment),
            })
    defaults.sort(key=lambda item: (item["since"], item["establishment_id"]))
    return envelope({"as_of": as_of.isoformat(), "defaulters": defaults,
                     "note": "Illustrative detection from filings and payments; the office verifies before opening a case."})


@router.get("/api/v1/employers/me/compliance-summary")
async def compliance_summary(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment",
                      "The actor has no establishment assigned.")
    as_of = today()
    rows = (await session.execute(select(contribution_facts).where(
        contribution_facts.c.establishment_id == actor.establishment_id))).mappings().all()
    months, _ = _evaluate(rows, as_of)
    return envelope({"establishment_id": actor.establishment_id, "as_of": as_of.isoformat(),
                     "months": list(reversed(months)),
                     "counts": {status: sum(month["status"] == status for month in months) for status in STATUSES}})
