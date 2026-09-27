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
    row = (await session.execute(select(policy_rules.c.document).where(policy_rules.c.effective_from <= day)
                                 .order_by(policy_rules.c.effective_from.desc()).limit(1))).scalar_one_or_none()
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
    if not isinstance(claims.get("settlement_sla_days"), int) or claims["settlement_sla_days"] < 1:
        problems.append("claims.settlement_sla_days must be at least 1")
    g = document.get("grievances") or {}
    if not g.get("categories") or "OTHER" not in g["categories"]:
        problems.append("grievances.categories must include OTHER")
    if set((g.get("sla_days") or {})) != {"RO", "ZO", "HO"} or any(not isinstance(v, int) or v < 1 for v in g["sla_days"].values()):
        problems.append("grievances.sla_days needs RO, ZO and HO, each at least 1 day")
    if not isinstance(g.get("reopen_window_days"), int) or g["reopen_window_days"] < 0:
        problems.append("grievances.reopen_window_days must be a non-negative whole number")
    return problems
