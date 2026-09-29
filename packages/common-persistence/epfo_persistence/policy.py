"""Versioned policy (rule sets) as consumed by the services.

platform-service owns rule sets: drafts, checks, maker-checker approval and publication. Each publication
emits PolicyPublished.v1 carrying the whole document. Every consuming service keeps the published versions
in its own `policy_rules` table (no cross-service reads) and asks for:

* `rules_on(session, day)`       the version in force on a date (a claim date, the first day of a wage month);
* `rules_by_version(session, v)` the exact version a past decision used, so it can be reproduced.

Before any version has been published (a fresh stack) both fall back to the baseline file config/demo-rules.yaml.
`validate` is the one set of checks used by platform-service before publishing."""
import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import JSON, Column, Date, DateTime, MetaData, String, Table, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

policy_metadata = MetaData()
policy_rules = Table(
    "policy_rules", policy_metadata,
    Column("rule_version", String(60), primary_key=True),
    Column("effective_from", Date, nullable=False, index=True),
    Column("document", JSON, nullable=False),
    Column("published_at", DateTime(timezone=True), server_default=func.now()),
)

CHAIN_FIRST = {"fo.da_accounts"}
CHAIN_SECOND = {"fo.ss", "fo.ao"}
CHAIN_LATER = {"fo.apfc", "fo.oic"}
CLAIM_CONDITIONS = {"requires_active_employment", "requires_exit_months", "min_service_months", "once_every_months",
                    "max_from", "max_pct_bp", "cap_paise"}
CLAIM_FIELDS = CLAIM_CONDITIONS | {"form_type", "label", "plain_rule", "auto_settle_up_to_paise", "approval_bands", "retired"}


def _baseline_path() -> Path:
    configured = Path(os.getenv("RULES_FILE", "/srv/demo-rules.yaml"))
    if configured.exists():
        return configured
    here = Path(__file__).resolve()
    for parent in here.parents:                                   # a checkout: <repo>/config/demo-rules.yaml
        candidate = parent / "config" / "demo-rules.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/demo-rules.yaml not found; set RULES_FILE")


@lru_cache(maxsize=1)
def baseline() -> dict[str, Any]:
    with _baseline_path().open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _document(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else json.loads(value)


async def rules_on(session: AsyncSession, day: date) -> dict[str, Any]:
    # On a date with two versions, the one published later (a same-day correction) applies.
    row = (await session.execute(select(policy_rules.c.document).where(policy_rules.c.effective_from <= day)
                                 .order_by(policy_rules.c.effective_from.desc(), policy_rules.c.published_at.desc())
                                 .limit(1))).scalar_one_or_none()
    return _document(row) if row is not None else baseline()


async def rules_by_version(session: AsyncSession, rule_version: str) -> dict[str, Any]:
    row = (await session.execute(select(policy_rules.c.document).where(
        policy_rules.c.rule_version == rule_version))).scalar_one_or_none()
    if row is not None:
        return _document(row)
    if baseline()["rule_version"] == rule_version:
        return baseline()
    raise LookupError(f"rule version {rule_version} has not reached this service yet")


async def on_policy_published(session: AsyncSession, event: dict[str, Any]) -> None:
    """Consumer handler for platform-service.PolicyPublished.v1 (idempotent)."""
    p = event["payload"]
    if (await session.execute(select(policy_rules.c.rule_version).where(policy_rules.c.rule_version == p["rule_version"]))).first():
        return
    await session.execute(insert(policy_rules).values(rule_version=p["rule_version"], effective_from=date.fromisoformat(
        p["effective_from"]), document=p["document"]))


def approval_chain(rules: dict[str, Any], claim_type: str, amount_paise: int) -> list[str]:
    spec = rules["claims"]["types"].get(claim_type, {})
    for band in spec.get("approval_bands") or rules["claims"]["approval_bands"]:
        if band["upto_paise"] is None or amount_paise <= band["upto_paise"]:
            return list(band["chain"])
    raise ValueError("no approval band")


def auto_settle_limit(rules: dict[str, Any], claim_type: str) -> int | None:
    spec = rules["claims"]["types"].get(claim_type, {})
    if "auto_settle_up_to_paise" in spec:
        return spec["auto_settle_up_to_paise"]
    return rules["claims"].get("auto_settlement_limit_paise")


# ── contribution arithmetic (used by contribution-service and by the policy preview) ──────────────

def round_rupee_half_up(amount_paise_numerator: int, denominator: int = 10_000) -> int:
    """Round (paise*numerator/denominator) to a whole rupee, returning paise."""
    rupees_numerator = amount_paise_numerator
    divisor = denominator * 100
    return ((rupees_numerator * 2 + divisor) // (2 * divisor)) * 100


def split(epf_wages_paise: int, eps_wages_paise: int, age_years: int, rules: dict[str, Any], edli_wages_paise: int | None = None) -> dict[str, int]:
    c = rules["contribution"]
    eps_wages_paise = min(eps_wages_paise, c["eps_wage_ceiling_paise"])
    ee = round_rupee_half_up(epf_wages_paise * c["epf_employee_rate_bp"])
    eps = 0 if age_years >= c["eps_age_limit_years"] else round_rupee_half_up(eps_wages_paise * c["eps_rate_bp"])
    er = ee - eps
    edli_wages_paise = epf_wages_paise if edli_wages_paise is None else edli_wages_paise
    edli = round_rupee_half_up(min(edli_wages_paise, c["edli_wage_ceiling_paise"]) * c["edli_rate_bp"])
    admin = max(c["admin_charges_min_paise"], round_rupee_half_up(epf_wages_paise * c["admin_charges_rate_bp"]))
    edli_admin = round_rupee_half_up(epf_wages_paise * c["edli_admin_rate_bp"])
    return {"AC01_EPF_EE": ee, "AC01_EPF_ER": er, "AC10_EPS": eps, "AC21_EDLI": edli,
            "AC02_ADMIN": admin, "AC22_EDLI_ADMIN": edli_admin,
            "TOTAL": ee + er + eps + edli + admin + edli_admin}


# ── interest, TDS and pension (used by contribution-, claim- and pension-service and by the preview) ──

def section(rules: dict[str, Any], name: str) -> dict[str, Any]:
    """A section of the rules; a version published before the section existed takes the baseline's."""
    return rules.get(name) or baseline()[name]


FY = re.compile(r"^(\d{4})-(\d{2})$")


def financial_year(day: date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def financial_year_bounds(fy: str) -> tuple[date, date]:
    m = FY.match(fy)
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise ValueError(f"{fy} is not a financial year like 2025-26")
    start = int(m.group(1))
    return date(start, 4, 1), date(start + 1, 3, 31)


def month_ends(fy: str) -> list[date]:
    start, _ = financial_year_bounds(fy)
    ends = []
    for i in range(12):
        y, mth = start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1
        nxt = date(y + (mth == 12), mth % 12 + 1, 1)
        ends.append(date.fromordinal(nxt.toordinal() - 1))
    return ends


def interest_rate_bp(rules: dict[str, Any], fy: str) -> int | None:
    return section(rules, "interest").get("rates_bp", {}).get(fy)


def interest_on(monthly_closing_paise: list[int], rate_bp: int) -> int:
    """Monthly running balance: the sum of the twelve month-end balances x rate / 12, to the nearest rupee."""
    return round_rupee_half_up(sum(monthly_closing_paise) * rate_bp, 10_000 * 12)


def tds_on(amount_paise: int, claim_type: str, service_months: int, pan_verified: bool, has_15g_15h: bool,
           rules: dict[str, Any]) -> dict[str, Any]:
    """TDS on a withdrawal under the rules in force on the payment date: {tds_paise, rate_bp, basis}."""
    t = section(rules, "tds")
    none = {"tds_paise": 0, "rate_bp": 0}
    if claim_type not in t["applies_to_claim_types"]:
        return {**none, "basis": "This type of withdrawal is not taxed at source."}
    if service_months >= t["exempt_after_service_months"]:
        return {**none, "basis": f"No TDS after {t['exempt_after_service_months'] // 12} years of service."}
    if amount_paise < t["threshold_paise"]:
        return {**none, "basis": "Below the TDS threshold."}
    if has_15g_15h and t["form_15g_15h_waiver"]:
        return {**none, "basis": "Form 15G / 15H on file for this financial year."}
    rate = t["rate_with_pan_bp"] if pan_verified else t["rate_without_pan_bp"]
    return {"tds_paise": round_rupee_half_up(amount_paise * rate), "rate_bp": rate,
            "basis": f"{rate / 100:g}% {'with a verified PAN' if pan_verified else 'without a verified PAN'}."}


def pension_on(salary_paise: int, service_months: int, age_years: int, rules: dict[str, Any]) -> dict[str, Any]:
    """Monthly EPS pension under the formula in the rules, with the working shown."""
    p = section(rules, "pension")
    years = service_months // 12 + (1 if service_months % 12 >= 6 else 0)        # six months or more count as a year
    if years < p["min_service_years"]:
        return {"eligible": False, "monthly_paise": 0, "service_years": years,
                "reason": f"At least {p['min_service_years']} years of service are needed for a monthly pension."}
    if age_years < p["earliest_age_years"]:
        return {"eligible": False, "monthly_paise": 0, "service_years": years,
                "reason": f"A monthly pension starts at {p['earliest_age_years']} at the earliest."}
    salary = min(salary_paise, p["pensionable_salary_cap_paise"])
    weightage = p["weightage_years"] if years >= p["weightage_after_service_years"] else 0
    formula = salary * (years + weightage) // p["divisor"]
    early_years = max(0, p["normal_age_years"] - age_years)
    reduction_bp = min(10_000, early_years * p["early_reduction_bp_per_year"])
    reduced = formula * (10_000 - reduction_bp) // 10_000
    by_formula = round_rupee_half_up(reduced * 10_000)
    monthly = max(by_formula, p["minimum_pension_paise"])
    working = f"₹{salary // 100:,} x ({years}{f' + {weightage} weightage' if weightage else ''} years) / {p['divisor']}"
    if reduction_bp:
        working += f", less {reduction_bp / 100:g}% for {early_years} years before age {p['normal_age_years']}"
    if monthly > by_formula:
        working += f"; raised to the minimum pension of ₹{monthly // 100:,}"
    return {"eligible": True, "monthly_paise": monthly, "service_years": years, "weightage_years": weightage,
            "pensionable_salary_paise": salary, "divisor": p["divisor"], "early_reduction_bp": reduction_bp,
            "minimum_applied": monthly > by_formula, "working": working}


def edli_benefit(average_wages_paise: int, average_balance_paise: int, service_months: int, rules: dict[str, Any]) -> dict[str, Any]:
    """EDLI assurance benefit on a member's death (illustrative formula from the rules)."""
    e = section(rules, "death_claims")["edli"]
    wages = min(average_wages_paise, section(rules, "contribution").get("edli_wage_ceiling_paise", average_wages_paise)) \
        if isinstance(rules.get("contribution"), dict) else average_wages_paise
    bonus = min(average_balance_paise * e["average_balance_share_bp"] // 10_000, e["balance_bonus_cap_paise"])
    raw = wages * e["wage_multiplier"] + bonus
    floor = e["minimum_paise"] if service_months >= e["minimum_needs_service_months"] else 0
    amount = max(min(raw, e["maximum_paise"]), floor)
    return {"amount_paise": amount, "working": (f"₹{wages // 100:,} x {e['wage_multiplier']} + ₹{bonus // 100:,} (balance share) = ₹{raw // 100:,}"
                                                f"{'; capped at the maximum' if raw > e['maximum_paise'] else ''}"
                                                f"{'; raised to the minimum' if raw < floor else ''}")}


# ── checks before publishing ─────────────────────────────────────────────────────────────────────

def _bands_problems(bands: Any, where: str) -> list[str]:
    problems = []
    if not isinstance(bands, list) or not bands:
        return [f"{where}: at least one band is needed"]
    previous = -1
    for i, band in enumerate(bands):
        upto, chain = band.get("upto_paise"), band.get("chain") or []
        last = i == len(bands) - 1
        if upto is None and not last:
            problems.append(f"{where} band {i + 1}: only the last band may be open-ended")
        if upto is not None and (not isinstance(upto, int) or upto <= previous):
            problems.append(f"{where} band {i + 1}: amounts must increase")
        if last and upto is not None:
            problems.append(f"{where}: the last band must have no upper limit, so every amount has an approver")
        previous = upto if isinstance(upto, int) else previous
        if len(chain) < 2:
            problems.append(f"{where} band {i + 1}: a claim needs a dealing assistant and at least one approver")
            continue
        if chain[0] not in CHAIN_FIRST:
            problems.append(f"{where} band {i + 1}: the chain must start with fo.da_accounts")
        if chain[1] not in CHAIN_SECOND:
            problems.append(f"{where} band {i + 1}: the first approver must be fo.ss or fo.ao")
        if any(r not in CHAIN_LATER for r in chain[2:]):
            problems.append(f"{where} band {i + 1}: further approvers must be fo.apfc or fo.oic")
        if len(set(chain)) != len(chain):
            problems.append(f"{where} band {i + 1}: a role appears twice")
    return problems


def _whole(v: Any, low: int, high: int | None = None) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= low and (high is None or v <= high)


def _money_sections_problems(document: dict[str, Any]) -> list[str]:
    """Interest, TDS and pension sections (each optional: a missing section takes the baseline's)."""
    problems: list[str] = []
    if "interest" in document:
        rates = (document["interest"] or {}).get("rates_bp")
        if not isinstance(rates, dict) or not rates:
            problems.append("interest.rates_bp needs at least one financial year")
        for fy, rate in (rates or {}).items() if isinstance(rates, dict) else []:
            try:
                financial_year_bounds(fy)
            except ValueError:
                problems.append(f"interest: {fy} is not a financial year like 2025-26")
            if not _whole(rate, 0, 2000):
                problems.append(f"interest rate for {fy} must be between 0 and 2000 basis points (20%)")
    if "tds" in document:
        t = document["tds"] or {}
        if not isinstance(t.get("applies_to_claim_types"), list):
            problems.append("tds.applies_to_claim_types must be a list of claim types (it may be empty)")
        else:
            unknown = set(t["applies_to_claim_types"]) - set(((document.get("claims") or {}).get("types") or {}))
            if unknown:
                problems.append(f"tds.applies_to_claim_types names unknown claim types: {', '.join(sorted(unknown))}")
        for key in ("rate_with_pan_bp", "rate_without_pan_bp"):
            if not _whole(t.get(key), 0, 5000):
                problems.append(f"tds.{key} must be between 0 and 5000 basis points")
        if _whole(t.get("rate_with_pan_bp"), 0) and _whole(t.get("rate_without_pan_bp"), 0) and t["rate_without_pan_bp"] < t["rate_with_pan_bp"]:
            problems.append("tds.rate_without_pan_bp cannot be lower than the rate with a PAN")
        for key in ("threshold_paise", "exempt_after_service_months"):
            if not _whole(t.get(key), 0):
                problems.append(f"tds.{key} must be a non-negative whole number")
        if not isinstance(t.get("form_15g_15h_waiver"), bool):
            problems.append("tds.form_15g_15h_waiver must be true or false")
    if "death_claims" in document:
        e = ((document["death_claims"] or {}).get("edli")) or {}
        for key, (low, high) in {"wage_multiplier": (1, 100), "average_balance_share_bp": (0, 10000), "balance_bonus_cap_paise": (0, None),
                                 "minimum_paise": (0, None), "maximum_paise": (1, None), "minimum_needs_service_months": (0, 120)}.items():
            if not _whole(e.get(key), low, high):
                problems.append(f"death_claims.edli.{key} must be a whole number" + (f" between {low} and {high}" if high else f" of at least {low}"))
        if _whole(e.get("minimum_paise"), 0) and _whole(e.get("maximum_paise"), 0) and e["minimum_paise"] > e["maximum_paise"]:
            problems.append("death_claims.edli.minimum_paise cannot exceed the maximum")
    if "pension" in document:
        p = document["pension"] or {}
        checks = {"divisor": (1, 1000), "salary_months": (1, 120), "pensionable_salary_cap_paise": (100, None),
                  "min_service_years": (1, 40), "weightage_years": (0, 10), "weightage_after_service_years": (1, 45),
                  "normal_age_years": (50, 70), "earliest_age_years": (40, 70), "early_reduction_bp_per_year": (0, 2000),
                  "minimum_pension_paise": (0, None)}
        for key, (low, high) in checks.items():
            if not _whole(p.get(key), low, high):
                problems.append(f"pension.{key} must be a whole number" + (f" between {low} and {high}" if high else f" of at least {low}"))
        if _whole(p.get("earliest_age_years"), 0) and _whole(p.get("normal_age_years"), 0) and p["earliest_age_years"] > p["normal_age_years"]:
            problems.append("pension.earliest_age_years cannot be after the normal pension age")
        if not isinstance(p.get("applies_to_pensions_in_payment"), bool):
            problems.append("pension.applies_to_pensions_in_payment must be true or false")
        back = p.get("revise_in_payment_from")
        if back is not None:
            try:
                if date.fromisoformat(str(back)) > date.fromisoformat(str(document.get("effective_from"))):
                    problems.append("pension.revise_in_payment_from cannot be after the rule set's effective date")
            except ValueError:
                problems.append("pension.revise_in_payment_from must be a date (YYYY-MM-DD) or empty")
    return problems


def validate(document: dict[str, Any]) -> list[str]:
    """Everything wrong with a rule-set document, in plain words. Empty means it can be published."""
    problems: list[str] = []
    c = document.get("contribution") or {}
    for key in ("epf_employee_rate_bp", "eps_rate_bp", "edli_rate_bp", "admin_charges_rate_bp", "edli_admin_rate_bp"):
        if not isinstance(c.get(key), int) or not 0 <= c[key] <= 10000:
            problems.append(f"contribution.{key} must be a whole number of basis points between 0 and 10000")
    if isinstance(c.get("eps_rate_bp"), int) and isinstance(c.get("epf_employee_rate_bp"), int) and c["eps_rate_bp"] > c["epf_employee_rate_bp"]:
        problems.append("contribution.eps_rate_bp cannot exceed the employer's 12% share (epf_employee_rate_bp)")
    for key in ("eps_wage_ceiling_paise", "edli_wage_ceiling_paise", "admin_charges_min_paise"):
        if not isinstance(c.get(key), int) or c[key] < 0:
            problems.append(f"contribution.{key} must be a non-negative amount in paise")
    for key in ("eps_wage_ceiling_paise", "edli_wage_ceiling_paise"):
        if isinstance(c.get(key), int) and c[key] % 100:
            problems.append(f"contribution.{key} must be whole rupees")
    if not isinstance(c.get("eps_age_limit_years"), int) or not 50 <= c["eps_age_limit_years"] <= 70:
        problems.append("contribution.eps_age_limit_years must be between 50 and 70")
    claims = document.get("claims") or {}
    types = claims.get("types") or {}
    if not types:
        problems.append("claims.types: at least one claim type is needed")
    if not any(not t.get("retired") for t in types.values()):
        problems.append("claims.types: at least one claim type must stay open to members")
    for code, t in types.items():
        where = f"claim type {code}"
        if not code.isupper() or not code.replace("_", "").isalnum():
            problems.append(f"{where}: codes use capital letters, digits and underscores")
        unknown = set(t) - CLAIM_FIELDS
        if unknown:
            problems.append(f"{where}: unknown fields {', '.join(sorted(unknown))}")
        for field in ("form_type", "label", "plain_rule"):
            if not str(t.get(field) or "").strip():
                problems.append(f"{where}: {field} is required")
        if t.get("max_from") not in ("employee_share", "total_balance"):
            problems.append(f"{where}: max_from must be employee_share or total_balance")
        if "max_pct_bp" in t and not (isinstance(t["max_pct_bp"], int) and 1 <= t["max_pct_bp"] <= 10000):
            problems.append(f"{where}: max_pct_bp must be between 1 and 10000")
        for field in ("cap_paise", "requires_exit_months", "min_service_months", "once_every_months"):
            if field in t and t[field] is not None and (not isinstance(t[field], int) or t[field] < 0):
                problems.append(f"{where}: {field} must be a non-negative whole number")
        if t.get("requires_active_employment") and t.get("requires_exit_months") is not None:
            problems.append(f"{where}: cannot require both current employment and having left")
        limit = t.get("auto_settle_up_to_paise", claims.get("auto_settlement_limit_paise"))
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            problems.append(f"{where}: auto_settle_up_to_paise must be empty (never automatic) or an amount")
        if t.get("approval_bands") is not None:
            problems.extend(_bands_problems(t["approval_bands"], where))
    problems.extend(_bands_problems(claims.get("approval_bands"), "default approval bands"))
    if claims.get("after_defreeze_bands") is not None:
        problems.extend(_bands_problems(claims["after_defreeze_bands"], "after-de-freeze bands"))
    if not isinstance(claims.get("settlement_sla_days"), int) or claims["settlement_sla_days"] < 1:
        problems.append("claims.settlement_sla_days must be at least 1")
    problems.extend(_money_sections_problems(document))
    g = document.get("grievances") or {}
    if not g.get("categories") or "OTHER" not in g["categories"]:
        problems.append("grievances.categories must include OTHER")
    if set((g.get("sla_days") or {})) != {"RO", "ZO", "HO"} or any(not isinstance(v, int) or v < 1 for v in g["sla_days"].values()):
        problems.append("grievances.sla_days needs RO, ZO and HO, each at least 1 day")
    if not isinstance(g.get("reopen_window_days"), int) or g["reopen_window_days"] < 0:
        problems.append("grievances.reopen_window_days must be a non-negative whole number")
    return problems


def after_defreeze_chain(rules: dict[str, Any], amount_paise: int) -> list[str]:
    # A version published before this matrix existed takes the baseline's; the normal chain is the last resort.
    bands = rules["claims"].get("after_defreeze_bands") or baseline()["claims"].get("after_defreeze_bands")
    for band in bands or rules["claims"]["approval_bands"]:
        if band["upto_paise"] is None or amount_paise <= band["upto_paise"]:
            return list(band["chain"])
    raise ValueError("no approval band")
