"""Phase 2, slice 7c: the member's annual statement for a financial year and the taxable / non-taxable split of the
interest (illustrative: interest on the employee's own contributions above a yearly threshold is taxable).
Interest belongs to the year it is earned for (it is credited after the year ends); everything else to the year it
was posted in; the opening balance brought forward belongs before any year."""
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence.policy import rules_on, section

router = APIRouter()
MEMBER = require_stakeholder("member")
FY = re.compile(r"^(\d{4})-(\d{2})$")
GROUPS = {"CONTRIBUTION": "contributions", "OPENING_BALANCE": "opening", "CLAIM_DEBIT": "withdrawals", "CLAIM_REVERSAL": "withdrawals",
          "TRANSFER": "transfers", "TRANSFER_RECREDIT": "transfers", "INTEREST": "interest", "INTEREST_REVISION": "interest",
          "APPENDIX_E": "adjustments", "REVERSAL": "adjustments"}
TAX_DEFAULTS = {"taxable_interest_threshold_paise": 25000000}


def _fy(value: str) -> tuple[date, date]:
    m = FY.match(value)
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise Problem(422, "/problems/validation", "Give a financial year like 2025-26")
    start = int(m.group(1))
    return date(start, 4, 1), date(start + 1, 3, 31)


def _year_of(on: date) -> str:
    start = on.year if on.month >= 4 else on.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


async def _lines(session, subject: str) -> list[dict[str, Any]]:
    return [dict(r) for r in (await session.execute(text(
        "SELECT m.account_link_id, e.legal_name, j.kind, j.occurred_at, jl.side, jl.amount_paise, jl.share, ip.financial_year AS interest_year "
        "FROM establishment_members m JOIN journal_lines jl ON jl.account_link_id = m.account_link_id AND jl.account_code = 'AC01_EPF' "
        "JOIN journals j ON j.id = jl.journal_id LEFT JOIN interest_postings ip ON ip.journal_id = j.id "
        "LEFT JOIN establishments e ON e.id = m.establishment_id WHERE m.member_subject = :s"), {"s": subject})).mappings().all()]


def _assign(line: dict[str, Any]) -> str:
    if line["kind"] == "OPENING_BALANCE":
        return "0000-00"
    if line["interest_year"]:
        return line["interest_year"]
    at = line["occurred_at"]
    return _year_of(at.date() if hasattr(at, "date") else date.fromisoformat(str(at)[:10]))


def statement(lines: list[dict[str, Any]], fy: str) -> list[dict[str, Any]]:
    accounts: dict[str, dict[str, Any]] = {}
    for ln in lines:
        a = accounts.setdefault(ln["account_link_id"], {"account_link_id": ln["account_link_id"], "establishment": ln["legal_name"],
                                                        "opening": {"employee": 0, "employer": 0},
                                                        "movements": {g: {"employee": 0, "employer": 0} for g in sorted(set(GROUPS.values()) - {"opening"})}})
        signed = ln["amount_paise"] if ln["side"] == "credit" else -ln["amount_paise"]
        share = ln["share"] if ln["share"] in ("employee", "employer") else "employer"
        year = _assign(ln)
        if year < fy:
            a["opening"][share] += signed
        elif year == fy:
            a["movements"][GROUPS.get(ln["kind"], "adjustments")][share] += signed
    for a in accounts.values():
        a["closing"] = {s: a["opening"][s] + sum(m[s] for m in a["movements"].values()) for s in ("employee", "employer")}
        a["closing_total_paise"] = a["closing"]["employee"] + a["closing"]["employer"]
    return sorted(accounts.values(), key=lambda x: x["account_link_id"])


@router.get("/api/v1/members/me/annual-statements/{financialYear}")
async def annual_statement(financialYear: str, actor: Actor = Depends(MEMBER)) -> dict:
    _fy(financialYear)
    async with sessions()() as session:
        lines = await _lines(session, actor.subject)
    if not lines:
        raise Problem(404, "/problems/not-found", "No member account found")
    return envelope({"financial_year": financialYear, "accounts": statement(lines, financialYear),
                     "note": "Interest is shown in the year it is earned for; it is credited after the year ends. EPS is not held per member ID."})


def taxable_split(employee_contributions_paise: int, employee_interest_paise: int, rate_bp: int, threshold_paise: int) -> dict[str, Any]:
    """Interest on the employee's own contributions above the yearly threshold is taxable (illustrative: the
    excess earns a full year's interest at the year's rate), never more than the interest itself."""
    excess = max(0, employee_contributions_paise - threshold_paise)
    taxable = min(max(0, employee_interest_paise), excess * rate_bp // 10000)
    return {"employee_contributions_paise": employee_contributions_paise, "threshold_paise": threshold_paise, "excess_paise": excess,
            "employee_interest_paise": employee_interest_paise, "taxable_interest_paise": taxable,
            "non_taxable_interest_paise": max(0, employee_interest_paise) - taxable,
            "working": (f"Contributions of ₹{employee_contributions_paise // 100:,} are within the ₹{threshold_paise // 100:,} limit: no interest is taxable."
                        if not excess else f"₹{excess // 100:,} above the ₹{threshold_paise // 100:,} limit x {rate_bp / 100:g}% = ₹{taxable // 100:,} taxable")}


@router.get("/api/v1/members/me/tax/taxable-interest")
async def taxable_interest(financialYear: str = Query(), actor: Actor = Depends(MEMBER)) -> dict:
    start, end = _fy(financialYear)
    async with sessions()() as session:
        lines = await _lines(session, actor.subject)
        rate = (await session.execute(text("SELECT MAX(ip.rate_bp) FROM interest_postings ip WHERE ip.financial_year=:y"), {"y": financialYear})).scalar_one()
        rules = await rules_on(session, end)
    if not lines:
        raise Problem(404, "/problems/not-found", "No member account found")
    threshold = {**TAX_DEFAULTS, **section(rules, "tds")}["taxable_interest_threshold_paise"]
    rate = rate or section(rules, "interest")["rates_bp"].get(financialYear, 0)
    ee_contrib = sum(ln["amount_paise"] if ln["side"] == "credit" else -ln["amount_paise"] for ln in lines
                     if ln["kind"] in ("CONTRIBUTION", "REVERSAL") and ln["share"] == "employee" and _assign(ln) == financialYear)
    ee_interest = sum(ln["amount_paise"] if ln["side"] == "credit" else -ln["amount_paise"] for ln in lines
                      if ln["interest_year"] == financialYear and ln["share"] == "employee")
    return envelope({"financial_year": financialYear, **taxable_split(ee_contrib, ee_interest, int(rate or 0), threshold), "rate_bp": int(rate or 0),
                     "interest_credited": ee_interest != 0, "illustrative": True,
                     "note": "Illustrative only — not tax advice. The employer share and its interest are not counted here."})
