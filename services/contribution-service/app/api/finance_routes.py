import json
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text

from app.infra.db import sessions
from app.infra.interest import interest_due
from app.infra.models import YieldAssumption
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import interest_rate_bp, rules_on

router = APIRouter()
FINANCE = require_stakeholder("gov.statutory_auditor", "ho.fa_cao")
HO_FINANCE = require_stakeholder("ho.fa_cao")
SUSTAINABILITY = require_stakeholder("ho.fa_cao", "ho.cpfc")

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


class YieldAssumptionUpdate(BaseModel):
    yield_bp: int = Field(ge=0, le=10000)
    label: str | None = None


class SustainabilityInput(BaseModel):
    financial_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    proposed_rate_bp: int = Field(ge=0, le=2000)

    @field_validator("financial_year")
    @classmethod
    def consecutive_years(cls, value: str) -> str:
        if int(value[-2:]) != (int(value[:4]) + 1) % 100:
            raise ValueError("financial_year must name consecutive years")
        return value


@router.put("/api/v1/ho/finance/yield-assumptions/{assetClass}")
async def update_yield_assumption(assetClass: str, body: YieldAssumptionUpdate,
                                  actor: Actor = Depends(HO_FINANCE)) -> dict:
    clean_key = assetClass.strip()
    async with sessions()() as session, session.begin():
        existing = (await session.execute(
            select(YieldAssumption).where(func.lower(YieldAssumption.asset_class) == clean_key.lower())
        )).scalar_one_or_none()
        target_class = existing.asset_class if existing else clean_key
        if existing:
            existing.yield_bp = body.yield_bp
            if body.label is not None:
                existing.label = body.label
            existing.updated_at = datetime.now(UTC)
            existing.updated_by = actor.subject
            label = existing.label
        else:
            label = body.label or f"{target_class} (illustrative)"
            session.add(YieldAssumption(
                asset_class=target_class,
                yield_bp=body.yield_bp,
                label=label,
                illustrative=True,
                updated_at=datetime.now(UTC),
                updated_by=actor.subject,
            ))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="finance.yield_assumption.updated", target_type="yield_assumption",
                    target_id=target_class, detail=json.dumps({"yield_bp": body.yield_bp}, sort_keys=True))
    return envelope({"asset_class": target_class, "yield_bp": body.yield_bp,
                     "label": label, "illustrative": True})


@router.get("/api/v1/ho/finance/yield-assumptions")
async def get_yield_assumptions(actor: Actor = Depends(SUSTAINABILITY)) -> dict:
    async with sessions()() as session, session.begin():
        rows = (await session.execute(select(YieldAssumption).order_by(YieldAssumption.asset_class))).scalars().all()
        return envelope([{"asset_class": r.asset_class, "yield_bp": r.yield_bp,
                          "label": r.label, "illustrative": r.illustrative} for r in rows])


@router.post("/api/v1/ho/finance/interest-sustainability")
async def interest_sustainability(body: SustainabilityInput, actor: Actor = Depends(SUSTAINABILITY)) -> dict:
    async with sessions()() as session, session.begin():
        pos_rows = (await session.execute(
            text("SELECT asset_class, SUM(book_value_paise) AS total_book FROM fund_asset_classes "
                 "WHERE fund = 'EPF' GROUP BY asset_class ORDER BY asset_class")
        )).all()
        if not pos_rows:
            raise Problem(422, "/problems/no-fund-positions", "No fund positions are known for the EPF fund.")

        assumptions = (await session.execute(select(YieldAssumption))).scalars().all()
        exact_map = {a.asset_class: a.yield_bp for a in assumptions}
        lower_map = {a.asset_class.lower(): a.yield_bp for a in assumptions}

        def get_yield(ac: str) -> int:
            if ac in exact_map:
                return exact_map[ac]
            if ac.lower() in lower_map:
                return lower_map[ac.lower()]
            return 700

        total_book = 0
        income = 0
        income_minus_50 = 0
        income_plus_50 = 0
        by_class = []
        for ac, raw_book in pos_rows:
            bv = int(raw_book)
            total_book += bv
            y = get_yield(ac)
            inc = round(bv * y / 10000)
            inc_minus = round(bv * max(0, y - 50) / 10000)
            inc_plus = round(bv * (y + 50) / 10000)
            income += inc
            income_minus_50 += inc_minus
            income_plus_50 += inc_plus
            by_class.append({"asset_class": ac, "book_value_paise": bv, "yield_bp": y, "income_paise": inc})

        proposed_due = await interest_due(session, body.financial_year, body.proposed_rate_bp)
        proposed_liability = sum(a["employee"]["due_paise"] + a["employer"]["due_paise"] for a in proposed_due)
        proposed_surplus = income - proposed_liability
        proposed_verdict = "SUSTAINABLE" if proposed_surplus >= 0 else "DEFICIT"

        # A zero proposed rate has zero liability; use a nonzero reference rate
        # to find the same liability slope. If there are no member balances,
        # no finite break-even rate can be inferred.
        reference_rate = body.proposed_rate_bp or 1000
        reference_liability = proposed_liability
        if not body.proposed_rate_bp:
            reference_due = await interest_due(session, body.financial_year, reference_rate)
            reference_liability = sum(a["employee"]["due_paise"] + a["employer"]["due_paise"] for a in reference_due)
        break_even_rate_bp = round(income * reference_rate / reference_liability) if reference_liability > 0 else None

        rules = await rules_on(session, date(int(body.financial_year[:4]), 4, 1))
        current_rate = interest_rate_bp(rules, body.financial_year) or 0
        if current_rate > 0:
            current_due = await interest_due(session, body.financial_year, current_rate)
            current_liability = sum(a["employee"]["due_paise"] + a["employer"]["due_paise"] for a in current_due)
            current_surplus = income - current_liability
            current_verdict = "SUSTAINABLE" if current_surplus >= 0 else "DEFICIT"
        else:
            current_liability = 0
            current_surplus = income
            current_verdict = "SUSTAINABLE"

        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="finance.interest_sustainability.modeled", target_type="interest_sustainability",
                    target_id=body.financial_year,
                    detail=json.dumps({"financial_year": body.financial_year, "proposed_rate_bp": body.proposed_rate_bp}, sort_keys=True))

        return envelope({
            "financial_year": body.financial_year,
            "total_book_value_paise": total_book,
            "income_paise": income,
            "sensitivity": {
                "minus_50_bp_income_paise": income_minus_50,
                "plus_50_bp_income_paise": income_plus_50,
            },
            "proposed_rate_bp": body.proposed_rate_bp,
            "liability_paise": proposed_liability,
            "surplus_paise": proposed_surplus,
            "verdict": proposed_verdict,
            "break_even_rate_bp": break_even_rate_bp,
            "current_declared_rate_bp": current_rate,
            "current_income_paise": income,
            "current_liability_paise": current_liability,
            "current_surplus_paise": current_surplus,
            "current_verdict": current_verdict,
            "by_asset_class": by_class,
            "yield_assumptions": [
                {"asset_class": r.asset_class, "yield_bp": r.yield_bp, "label": r.label, "illustrative": r.illustrative}
                for r in assumptions
            ],
        })
