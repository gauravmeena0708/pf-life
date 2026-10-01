"""Special Form 10D, legacy disbursement lists, and de-identified EPS valuation data."""
import hashlib
import os
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.domain.pension import amount_for, approved
from app.infra.tables import (higher_pension_options, member_service, office_staff, pension_payments, pensioners,
                              special_10d_cases)
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import rules_on

router = APIRouter()
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CHECKLIST = {
    "SERVICE_PERIOD": "Reconstruct the service period from the employer certificate and service record.",
    "WAGES": "Reconstruct wages from payroll records and the employer certificate.",
    "DATE_OF_BIRTH": "Reconstruct the date of birth from a service record or affidavit.",
    "EXIT_DATE": "Reconstruct the exit date from the employer certificate and service record.",
}
NEXT_STEP = "The APFC (Pension) accepts the reconstructed record; the worksheet is then generated from it."


async def db():
    async with sessions()() as session:
        yield session


async def office_for(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


class Evidence(BaseModel):
    kind: str = Field(pattern="^(EMPLOYER_CERTIFICATE|SERVICE_RECORD|AFFIDAVIT|OTHER)$")
    ref: str = Field(min_length=1)


class Special10D(BaseModel):
    uan: str = Field(min_length=1, max_length=12)
    account_link_id: str | None = None
    missing: list[str] = Field(min_length=1)
    details: str = Field(min_length=20)
    evidence: list[Evidence] = Field(default_factory=list)


@router.post("/api/v1/office/pensions/special-10d-cases", status_code=201)
async def create_special_case(body: Special10D, actor: Actor = Depends(require_stakeholder("fo.da_pension")),
                              session: AsyncSession = Depends(db)) -> dict:
    if any(item not in CHECKLIST for item in body.missing) or len(set(body.missing)) != len(body.missing):
        raise Problem(422, "/problems/validation", "Missing items must be distinct supported fields")
    async with session.begin():
        office = await office_for(session, actor)
        member = (await session.execute(select(member_service).where(member_service.c.uan == body.uan,
                                                                      member_service.c.office_id == office))).mappings().first()
        if not member or (body.account_link_id and body.account_link_id != member["account_link_id"]):
            raise Problem(404, "/problems/not-found", "Member not found in your office")
        if (await session.execute(select(special_10d_cases.c.case_id).where(
                special_10d_cases.c.uan == body.uan, special_10d_cases.c.state == "OPEN"))).first():
            raise Problem(409, "/problems/already-open", "An open Special 10D case already exists for this UAN")
        case_id = f"S10D-{secrets.token_hex(4).upper()}"
        await session.execute(insert(special_10d_cases).values(case_id=case_id, uan=body.uan,
            account_link_id=body.account_link_id or member["account_link_id"], office_id=office, state="OPEN",
            missing=body.missing, details=body.details, evidence=[e.model_dump() for e in body.evidence], created_by=actor.subject))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="pension.special_10d_opened", target_type="special_10d_case", target_id=case_id)
    return envelope({"case_id": case_id, "state": "OPEN", "checklist": [CHECKLIST[item] for item in body.missing],
                     "next_step": NEXT_STEP})


def masked_name(name: str) -> str:
    return " ".join(part[0] + "*" * max(1, len(part) - 1) for part in name.split())


@router.get("/api/v1/office/pensions/disbursement-lists")
async def disbursement_lists(month: str | None = Query(default=None),
                             actor: Actor = Depends(require_stakeholder("fo.pension_disbursement")),
                             session: AsyncSession = Depends(db)) -> dict:
    month = month or (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    if not MONTH.fullmatch(month):
        raise Problem(422, "/problems/validation", "Month must be YYYY-MM")
    office = await office_for(session, actor)
    rows = (await session.execute(select(pension_payments.c.ppo_id, pension_payments.c.amount_paise,
                                          pensioners.c.name, pensioners.c.bank_ifsc, pensioners.c.bank_account_last4)
                                  .join(pensioners, pensioners.c.ppo_id == pension_payments.c.ppo_id)
                                  .where(pension_payments.c.month == month, pension_payments.c.kind == "MONTHLY",
                                         pensioners.c.office_id == office)
                                  .order_by(pensioners.c.bank_ifsc, pension_payments.c.ppo_id))).all()
    banks: dict[str, dict[str, Any]] = {}
    for ppo, amount, name, ifsc, last4 in rows:
        bank = ifsc[:4].upper()
        group = banks.setdefault(bank, {"bank": bank, "pensioners": 0, "amount_paise": 0, "items": []})
        group["pensioners"] += 1
        group["amount_paise"] += int(amount)
        group["items"].append({"ppo_id": ppo, "name_masked": masked_name(name), "account_last4": last4,
                               "amount_paise": int(amount)})
    groups = list(banks.values())
    return envelope({"month": month, "banks": groups,
                     "totals": {"pensioners": sum(g["pensioners"] for g in groups),
                                "amount_paise": sum(g["amount_paise"] for g in groups)},
                     "note": "Legacy lists until CPPS pays centrally."})


def as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def age_at(born: Any, day: date) -> int:
    born = as_date(born)
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


@router.get("/api/v1/ho/actuarial/extracts")
async def actuarial_extract(as_of: date | None = None, actor: Actor = Depends(require_stakeholder("ho.actuarial")),
                            session: AsyncSession = Depends(db)) -> dict:
    day = as_of or datetime.now(UTC).date()
    salt = os.getenv("ACTUARIAL_EXTRACT_SALT", "demo-actuarial-salt")
    def record_id(identifier: str) -> str:
        return hashlib.sha256(f"{salt}:{identifier}".encode()).hexdigest()[:16]

    rows: list[dict[str, Any]] = []
    pensions = (await session.execute(select(pensioners))).mappings().all()
    for p in pensions:
        if as_date(p["pension_start"]) > day:
            continue
        monthly = amount_for(dict(p), await approved(session, p["ppo_id"]), day.strftime("%Y-%m"))["monthly_paise"]
        rows.append({"record_id": record_id(p["ppo_id"]), "category": "PENSIONER",
                     "age_years": age_at(p["date_of_birth"], day), "gender": None,
                     "pension_start_year": as_date(p["pension_start"]).year,
                     "monthly_pension_paise": int(monthly),
                     "service_months": p["service_months"], "status": p["status"]})
    options = (await session.execute(select(higher_pension_options, member_service.c.date_of_birth)
                                     .join(member_service, member_service.c.subject == higher_pension_options.c.subject))).mappings().all()
    for o in options:
        rows.append({"record_id": record_id(o["uan"]), "category": "HIGHER_PENSION_OPTION",
                     "age_years": age_at(o["date_of_birth"], day), "gender": None,
                     "pension_start_year": None, "monthly_pension_paise": None,
                     "service_months": None, "status": o["state"]})
    aggregate: dict[tuple[str, str], int] = {}
    for row in rows:
        age_band = f"{row['age_years'] // 5 * 5}-{row['age_years'] // 5 * 5 + 4}"
        key = row["category"], age_band
        aggregate[key] = aggregate.get(key, 0) + 1
    rule_version = (await rules_on(session, day))["rule_version"]
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                action="pension.actuarial_extract", target_type="actuarial_extract", target_id=day.isoformat())
    await session.commit()
    return envelope({"as_of": day.isoformat(), "rows": rows,
                     "aggregates": [{"category": category, "age_band": band, "count": count}
                                    for (category, band), count in sorted(aggregate.items())],
                     "rule_version": rule_version,
                     "note": "Direct identifiers are removed; record IDs are salted hashes. Gender is unavailable in this POC."})
