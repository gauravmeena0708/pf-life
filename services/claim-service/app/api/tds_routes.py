"""Illustrative Form 16A and quarterly Form 26Q from settled claims' stored tax figures."""
import hashlib
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, staff_office
from app.infra.tables import accounts, claim_timeline, claims, tds_filings
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import financial_year, financial_year_bounds

router = APIRouter()
NOTE = "Illustrative/mock document; not valid for filing."


def _bounds(fy: str) -> tuple[date, date]:
    try:
        return financial_year_bounds(fy)
    except ValueError:
        raise Problem(422, "/problems/validation", "Invalid financial year", "Use YYYY-YY, for example 2025-26.") from None


def _quarter(day: date, fy_start: date) -> str:
    return f"Q{((day.year - fy_start.year) * 12 + day.month - fy_start.month) // 3 + 1}"


async def _paid_rows(session: AsyncSession, start: date, end: date, *, member: str | None = None,
                     office: str | None = None) -> list[dict]:
    # The SETTLED timeline entry is the payment date; tax.payment_date is the instruction date.
    q = (select(claims, accounts.c.uan, accounts.c.member_name, accounts.c.pan_verified,
                claim_timeline.c.at.label("settled_at"))
         .join(accounts, accounts.c.account_link_id == claims.c.account_link_id)
         .join(claim_timeline, (claim_timeline.c.claim_id == claims.c.claim_id) & (claim_timeline.c.state == "SETTLED"))
         .where(claims.c.state == "SETTLED")
         .order_by(claim_timeline.c.at, claims.c.claim_id))
    if member is not None:
        q = q.where(claims.c.member_subject == member)
    if office is not None:
        q = q.where(claims.c.office_id == office)
    rows = (await session.execute(q)).mappings().all()
    result = []
    for row in rows:
        settled = row["settled_at"]
        paid_on = settled.date() if isinstance(settled, datetime) else date.fromisoformat(str(settled)[:10])
        tax = row["tax"] or {}
        if start <= paid_on <= end and tax.get("tds_paise", 0) > 0:
            result.append({**dict(row), "paid_on": paid_on.isoformat()})
    return result


def _item(row: dict, *, office: bool = False) -> dict:
    tax = row["tax"]
    item = {"claim_id": row["claim_id"], "paid_on": row["paid_on"],
            "amount_paid_paise": tax["gross_paise"], "tds_paise": tax["tds_paise"],
            "rate_bp": tax["rate_bp"], "basis": tax["basis"]}
    if office:
        item.update(uan_masked=f"********{(row['uan'] or '')[-4:]}",
                    pan_status="VERIFIED" if "with a verified PAN" in tax["basis"] else "NOT_VERIFIED")
    return item


@router.get("/api/v1/members/me/tax/form-16a")
async def form_16a(financialYear: str | None = Query(default=None), actor: Actor = Depends(require_stakeholder("member")),
                   session: AsyncSession = Depends(db)) -> dict:
    fy = financialYear if financialYear is not None else financial_year(datetime.now(UTC).date())
    start, end = _bounds(fy)
    account = (await session.execute(select(accounts).where(accounts.c.member_subject == actor.subject)
                                     .order_by(accounts.c.account_link_id))).mappings().first()
    rows = await _paid_rows(session, start, end, member=actor.subject)
    quarters = []
    for n in range(1, 5):
        items = [_item(r) for r in rows if _quarter(date.fromisoformat(r["paid_on"]), start) == f"Q{n}"]
        quarters.append({"quarter": f"Q{n}", "items": items,
                         "amount_paid_paise": sum(i["amount_paid_paise"] for i in items),
                         "tds_paise": sum(i["tds_paise"] for i in items)})
    uan = (account or {}).get("uan") or "0000"
    return envelope({"certificate_no": f"16A/{fy}/{uan[-4:]}/1", "financial_year": fy,
                     "deductor": {"name": "Employees' Provident Fund Organisation (synthetic)", "tan": "DELE00000E",
                                  "office_id": (account or {}).get("office_id")},
                     "deductee": {"name": (account or {}).get("member_name"), "pan_masked": None,
                                  "pan_status": "VERIFIED" if account and account["pan_verified"] else "NOT_VERIFIED"},
                     "quarters": quarters,
                     "totals": {"amount_paid_paise": sum(q["amount_paid_paise"] for q in quarters),
                                "tds_paise": sum(q["tds_paise"] for q in quarters)},
                     "section": "192A", "note": NOTE if rows else "No tax was deducted in this financial year. " + NOTE})


class FilingInput(BaseModel):
    financial_year: str
    quarter: Literal["Q1", "Q2", "Q3", "Q4"]


@router.post("/api/v1/office/tds/computations")
async def file_26q(body: FilingInput, actor: Actor = Depends(require_stakeholder("fo.da_accounts")),
                   session: AsyncSession = Depends(db)) -> dict:
    start, _ = _bounds(body.financial_year)
    n = int(body.quarter[1])
    quarter_start = date(start.year + (start.month - 1 + 3 * (n - 1)) // 12, (start.month - 1 + 3 * (n - 1)) % 12 + 1, 1)
    next_month = start.month - 1 + 3 * n
    quarter_end = date.fromordinal(date(start.year + next_month // 12, next_month % 12 + 1, 1).toordinal() - 1)
    if datetime.now(UTC).date() <= quarter_end:
        raise Problem(422, "/problems/quarter-open", "Quarter has not ended", "File after the quarter ends.")
    async with session.begin():
        office = await staff_office(session, actor)
        existing = (await session.execute(select(tds_filings.c.acknowledgement).where(
            tds_filings.c.office_id == office, tds_filings.c.financial_year == body.financial_year,
            tds_filings.c.quarter == body.quarter))).scalar_one_or_none()
        if existing:
            raise Problem(409, "/problems/already-filed", "TDS statement already filed", f"Acknowledgement: {existing}")
        rows = await _paid_rows(session, quarter_start, quarter_end, office=office)
        deductees = [_item(r, office=True) for r in rows]
        total_paid = sum(r["amount_paid_paise"] for r in deductees)
        total_tds = sum(r["tds_paise"] for r in deductees)
        key = f"{office}|{body.financial_year}|{body.quarter}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:16].upper()
        filing_id, acknowledgement = f"TDS-{digest}", f"26Q-ACK-{digest}"
        values = dict(filing_id=filing_id, office_id=office, financial_year=body.financial_year, quarter=body.quarter,
                      deductees=deductees, amount_paid_paise=total_paid, tds_paise=total_tds,
                      acknowledgement=acknowledgement, filed_by=actor.subject)
        insert_for = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        inserted = await session.execute(insert_for(tds_filings).values(**values).on_conflict_do_nothing(
            index_elements=["office_id", "financial_year", "quarter"]))
        if not inserted.rowcount:
            existing = (await session.execute(select(tds_filings.c.acknowledgement).where(
                tds_filings.c.office_id == office, tds_filings.c.financial_year == body.financial_year,
                tds_filings.c.quarter == body.quarter))).scalar_one()
            raise Problem(409, "/problems/already-filed", "TDS statement already filed", f"Acknowledgement: {existing}")
        await add_event(session, producer="claim-service", event_type="TdsStatementFiled.v1", aggregate_type="tds_filing",
                        aggregate_id=filing_id, correlation_id=actor.correlation_id,
                        payload={"filing_id": filing_id, "office_id": office, "financial_year": body.financial_year,
                                 "quarter": body.quarter, "deductees": len(deductees), "tds_paise": total_tds,   # a count: the event carries no list of members
                                 "acknowledgement": acknowledgement})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="tds.statement_filed",
                    target_type="tds_filing", target_id=filing_id, detail=acknowledgement)
    return envelope({"filing_id": filing_id, "office_id": office, "financial_year": body.financial_year,
                     "quarter": body.quarter, "deductees": deductees,
                     "totals": {"amount_paid_paise": total_paid, "tds_paise": total_tds},
                     "acknowledgement": acknowledgement, "form": "26Q", "note": NOTE})
