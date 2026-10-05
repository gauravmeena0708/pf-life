"""Illustrative head-office balance sheet from the posted double-entry ledger."""
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
FINANCE = require_stakeholder("gov.statutory_auditor", "ho.fa_cao")

LIABILITIES = {
    "AC01_EPF": "Members' provident fund accounts",
    "AC10_EPS": "Pension fund (EPS)",
    "AC21_EDLI": "Insurance fund (EDLI)",
    "AC02_ADMIN": "Administration account",
    "AC22_EDLI_ADMIN": "Administration account",
    "CLAIMS_PAYABLE": "Claims payable",
    "TDS_PAYABLE": "Income tax deducted, payable",
    "PAYABLE_TO_TRUSTS": "Payable to exempted PF trusts (transfers in)",
    "SCWF_PAYABLE": "Senior Citizens' Welfare Fund transfers",
    "ADJUSTMENT_SUSPENSE": "Suspense accounts",
    "INTEREST_SUSPENSE": "Suspense accounts",
}
ASSETS = {
    "OPENING_BALANCE_BF": "Balances brought forward (assets held)",
    "BANK_COLLECTION": "Bank — collections",
    "BANK_SETTLEMENT": "Bank — settlements",
}
NOTE = "Illustrative: amounts from the POC ledger; investments are reported separately from the fund managers' positions"


def _day(value: str | None) -> date:
    if value is None:
        return date.today()
    try:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise Problem(422, "/problems/validation", "Give as_of as YYYY-MM-DD")


@router.get("/api/v1/ho/finance/balance-sheet")
async def balance_sheet(as_of: str | None = Query(default=None), actor: Actor = Depends(FINANCE)) -> dict:
    day = _day(as_of)
    end = datetime.combine(day, time.max, tzinfo=UTC)
    async with sessions()() as session, session.begin():
        rows = (await session.execute(text(
            "SELECT jl.account_code, SUM(CASE WHEN jl.side='credit' THEN jl.amount_paise ELSE -jl.amount_paise END) AS balance "
            "FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id "
            "WHERE j.occurred_at <= :end GROUP BY jl.account_code ORDER BY jl.account_code"), {"end": end})).all()
        journals = (await session.execute(text("SELECT COUNT(*) FROM journals WHERE occurred_at <= :end"), {"end": end})).scalar_one()
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="finance.balance_sheet", target_type="balance_sheet", target_id=day.isoformat())

    liabilities, assets = [], []
    other_liability = other_asset = 0
    for code, raw_balance in rows:
        balance = int(raw_balance)
        if code in LIABILITIES:
            liabilities.append({"code": code, "name": LIABILITIES[code], "amount_paise": balance})
        elif code in ASSETS:
            assets.append({"code": code, "name": ASSETS[code], "amount_paise": -balance})
        elif balance > 0:
            other_liability += balance
        elif balance < 0:
            other_asset -= balance
    if other_liability:
        liabilities.append({"code": "OTHER", "name": "Other", "amount_paise": other_liability})
    if other_asset:
        assets.append({"code": "OTHER", "name": "Other", "amount_paise": other_asset})
    total_liabilities = sum(line["amount_paise"] for line in liabilities)
    total_assets = sum(line["amount_paise"] for line in assets)
    return envelope({"as_of": day.isoformat(), "liabilities": liabilities, "assets": assets,
                     "total_liabilities_paise": total_liabilities, "total_assets_paise": total_assets,
                     "balanced": total_assets == total_liabilities, "journals_counted": int(journals), "note": NOTE})
