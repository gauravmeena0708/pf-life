"""P2.17: Insolvency proceedings under the Insolvency and Bankruptcy Code, 2016 (IBC).
- Watchlist from EPFO signals: stopped ECR filing (3+ months), open demands in default, synthetic MCA status.
- Insolvency case per establishment: IBBI announcement (CIRP or liquidation), claim deadline (+14 days configurable),
  and warning within 3 days if claim is not yet filed.
- Dues frozen: moratorium (IBC s.14) stops coercive recovery; claim filed with PF/pension principal kept apart from
  s.14B damages and s.7Q interest.
- Resolution plan checked: NON-COMPLIANT unless PF principal is paid in full (IBC s.36(4)(a)(iii));
  in liquidation, PF claim is outside the liquidation estate (not in s.53 waterfall).
- Recovery measured: dues claimed, recovered, recovery %, and office summary.
"""
from collections import Counter
from datetime import UTC, date, datetime, timedelta
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _names, _office, db
from app.infra.tables import demands, ecr_filings, establishments, insolvency_cases
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
INSOLVENCY_OFFICERS = require_stakeholder("fo.da_compliance", "fo.ss", "fo.apfc", "fo.oic", "fo.recovery_officer", "do.staff")


def current_date() -> date:
    """Returns the current date. Monkeypatchable in unit tests for time-dependent rule validation."""
    return date.today()


def now() -> datetime:
    return datetime.now(UTC)


def iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def case_view(row: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """Formats an insolvency case with deadline warnings, recovery percentages, and statutory status."""
    c = dict(row)
    eid = c["establishment_id"]
    legal_name = names.get(eid, eid)
    c["legal_name"] = legal_name

    # Deadline & 3-day warning calculation
    deadline = date.fromisoformat(c["claim_deadline"]) if isinstance(c["claim_deadline"], str) else c["claim_deadline"]
    today = current_date()
    days_remaining = (deadline - today).days
    c["days_to_deadline"] = days_remaining

    warning: str | None = None
    warning_code: str | None = None
    if not c.get("claim_filed"):
        if days_remaining < 0:
            warning = f"Claim submission deadline expired {abs(days_remaining)} days ago ({c['claim_deadline']})! File claim immediately."
            warning_code = "CLAIM_DEADLINE_EXPIRED"
        elif days_remaining <= 3:
            warning = f"Urgent: Claim submission deadline is in {days_remaining} day(s) on {c['claim_deadline']}. Claim not yet filed!"
            warning_code = "CLAIM_DEADLINE_APPROACHING"

    c["warning"] = warning
    c["warning_code"] = warning_code

    total_claimed = int(c.get("total_claimed_paise") or 0)
    realised = int(c.get("realised_paise") or 0)
    c["recovery_pct"] = round(realised * 100.0 / total_claimed, 2) if total_claimed > 0 else 0.0
    c["outstanding_paise"] = max(0, total_claimed - realised)

    # IBC s.36(4)(a)(iii): in liquidation, PF dues are outside the liquidation estate (not in s.53 waterfall)
    if c.get("outside_liquidation_estate"):
        c["waterfall_status"] = "OUTSIDE_S53_WATERFALL"
        c["statutory_basis"] = "IBC s.36(4)(a)(iii)"
        c["liquidation_note"] = "Provident fund and pension dues are excluded from the liquidation estate and not subject to s.53 waterfall priority."

    c["created_at"] = iso(c.get("created_at"))
    c["claim_filed_at"] = iso(c.get("claim_filed_at"))
    return c


# ── Item a: Watchlist from EPFO signals ─────────────────────────────────────────────────────────────

class McaStatusInput(BaseModel):
    mca_status: Literal["ACTIVE", "UNDER_CIRP", "LIQUIDATION", "STRIKE_OFF"]


@router.post("/api/v1/office/compliance/establishments/{establishment_id}/mca-statuses")
async def update_mca_status(
    establishment_id: str,
    body: McaStatusInput,
    actor: Actor = Depends(require_stakeholder("fo.da_compliance", "fo.ss", "fo.apfc", "fo.oic")),
    session: AsyncSession = Depends(db)
) -> dict:
    """Updates synthetic MCA registration status for an establishment (e.g. UNDER_CIRP, LIQUIDATION)."""
    async with session.begin():
        await session.execute(
            update(establishments)
            .where(establishments.c.establishment_id == establishment_id)
            .values(mca_status=body.mca_status)
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="compliance.mca_status_updated", target_type="establishment",
                    target_id=establishment_id, detail=f"MCA status updated to {body.mca_status}")
    return envelope({"establishment_id": establishment_id, "mca_status": body.mca_status})


@router.get("/api/v1/office/compliance/insolvency/watchlist")
async def insolvency_watchlist(
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Watchlist from EPFO's own signals: establishments whose ECR filing has stopped (no return for 3+ months
    after regular filing), with open demands in default, or a synthetic MCA status of 'under CIRP'/'liquidation' —
    scored and listed for the office with the reasons."""
    office = await _office(session, actor)
    est_rows = (await session.execute(
        select(establishments).where(establishments.c.office_id == office)
    )).mappings().all()

    today = current_date()
    cur_year = today.year
    cur_month = today.month

    watchlist = []

    for est in est_rows:
        eid = est["establishment_id"]
        score = 0
        reasons = []
        signals = {
            "ecr_stopped": False,
            "last_ecr_month": None,
            "months_unfiled": 0,
            "open_demands_count": 0,
            "open_demands_paise": 0,
            "mca_status": est.get("mca_status")
        }

        # 1. ECR filing signal: stopped after regular filing (>= 3 months)
        filings = (await session.execute(
            select(ecr_filings.c.wage_month)
            .where(ecr_filings.c.establishment_id == eid)
            .order_by(ecr_filings.c.wage_month.desc())
        )).scalars().all()

        if filings:
            last_filing = filings[0]
            signals["last_ecr_month"] = last_filing
            try:
                ly, lm = int(last_filing[:4]), int(last_filing[5:7])
                months_diff = (cur_year - ly) * 12 + (cur_month - lm)
                if months_diff >= 3:
                    signals["ecr_stopped"] = True
                    signals["months_unfiled"] = months_diff
                    score += 30
                    reasons.append(f"ECR filing stopped for {months_diff} months after regular filing (last return filed: {last_filing})")
            except (ValueError, IndexError):
                pass

        # 2. Open demands in default
        open_demands = (await session.execute(
            select(demands.c.amount_paise)
            .where(demands.c.establishment_id == eid, demands.c.state == "OPEN")
        )).scalars().all()

        if open_demands:
            d_count = len(open_demands)
            d_amount = sum(open_demands)
            signals["open_demands_count"] = d_count
            signals["open_demands_paise"] = d_amount
            score += 35
            reasons.append(f"Open demands in default ({d_count} demand(s), ₹{d_amount // 100:,})")

        # 3. MCA status: UNDER_CIRP or LIQUIDATION
        mca = est.get("mca_status")
        if mca and any(kw in mca.lower() for kw in ("cirp", "liquidation")):
            score += 50
            reasons.append(f"MCA status: {mca}")

        if score > 0:
            risk_level = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
            watchlist.append({
                "establishment_id": eid,
                "legal_name": est["legal_name"],
                "score": score,
                "risk_level": risk_level,
                "reasons": reasons,
                "signals": signals
            })

    watchlist.sort(key=lambda x: (-x["score"], x["establishment_id"]))
    return envelope({
        "as_of": today.isoformat(),
        "office_id": office,
        "total_flagged": len(watchlist),
        "watchlist": watchlist
    })


# ── Item b: Insolvency Case per establishment ────────────────────────────────────────────────────────

class InsolvencyCaseInput(BaseModel):
    establishment_id: str = Field(min_length=3, max_length=40)
    stage: Literal["CIRP", "LIQUIDATION"] = "CIRP"
    practitioner_type: Literal["IRP", "RP", "LIQUIDATOR"] = "IRP"
    practitioner_name: str = Field(min_length=2, max_length=120)
    practitioner_email: str | None = None
    announcement_date: date
    claim_period_days: int = Field(default=14, ge=1, le=90)  # Configurable, default 14 days under IBBI CIRP Reg 6(2)(c)
    nclt_bench: str | None = None
    order_ref: str | None = None
    note: str | None = None


@router.post("/api/v1/office/compliance/insolvency-cases", status_code=201)
async def create_insolvency_case(
    body: InsolvencyCaseInput,
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Records an IBBI public announcement and creates an insolvency case per establishment with claim deadline
    (announcement date + 14 days under CIRP regulations, configurable)."""
    async with session.begin():
        office = await _office(session, actor)
        case_id = f"INS-{secrets.token_hex(4).upper()}"
        announcement_str = body.announcement_date.isoformat()
        claim_deadline_dt = body.announcement_date + timedelta(days=body.claim_period_days)
        claim_deadline_str = claim_deadline_dt.isoformat()

        # Admission to CIRP triggers statutory moratorium under IBC s.14
        # Liquidation excludes PF dues under IBC s.36(4)(a)(iii)
        is_cirp = body.stage == "CIRP"
        moratorium_active = is_cirp
        outside_estate = not is_cirp

        history_entry = {
            "at": now().isoformat(),
            "action": "ANNOUNCEMENT_RECORDED",
            "stage": body.stage,
            "practitioner_type": body.practitioner_type,
            "practitioner_name": body.practitioner_name,
            "claim_deadline": claim_deadline_str,
            "by": actor.subject,
            "note": body.note or "IBBI public announcement recorded"
        }

        row = {
            "case_id": case_id,
            "establishment_id": body.establishment_id,
            "office_id": office,
            "stage": body.stage,
            "practitioner_type": body.practitioner_type,
            "practitioner_name": body.practitioner_name,
            "practitioner_email": body.practitioner_email,
            "announcement_date": announcement_str,
            "claim_deadline": claim_deadline_str,
            "claim_period_days": body.claim_period_days,
            "nclt_bench": body.nclt_bench,
            "order_ref": body.order_ref,
            "claim_filed": False,
            "claim_filed_at": None,
            "claim_reference": None,
            "form_type": None,
            "claimed_principal_paise": 0,
            "claimed_damages_paise": 0,
            "claimed_interest_paise": 0,
            "total_claimed_paise": 0,
            "moratorium_active": moratorium_active,
            "outside_liquidation_estate": outside_estate,
            "resolution_plan": None,
            "plan_status": None,
            "realised_paise": 0,
            "state": "OPEN",
            "history": [history_entry],
            "created_by": actor.subject,
            "created_at": now()
        }
        await session.execute(insert(insolvency_cases).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="compliance.insolvency_case_opened", target_type="insolvency_case",
                    target_id=case_id, detail=f"IBBI {body.stage} announcement for {body.establishment_id}")

        names = await _names(session)
        result = case_view(row, names)
    return envelope(result)


@router.get("/api/v1/office/compliance/insolvency-cases")
async def list_insolvency_cases(
    establishment_id: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    status: str | None = Query(default=None),
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Lists insolvency cases for the office."""
    office = await _office(session, actor)
    q = select(insolvency_cases).where(insolvency_cases.c.office_id == office).order_by(insolvency_cases.c.created_at.desc())
    if establishment_id:
        q = q.where(insolvency_cases.c.establishment_id == establishment_id)
    if stage:
        q = q.where(insolvency_cases.c.stage == stage)
    if status:
        q = q.where(insolvency_cases.c.state == status)

    rows = (await session.execute(q)).mappings().all()
    names = await _names(session)
    return envelope([case_view(r, names) for r in rows])


@router.get("/api/v1/office/compliance/insolvency-cases/{case_id}")
async def get_insolvency_case(
    case_id: str,
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Retrieves details of an insolvency case with deadline warnings and statutory attributes."""
    office = await _office(session, actor)
    row = (await session.execute(
        select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
    )).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Insolvency case not found")
    names = await _names(session)
    return envelope(case_view(row, names))


# ── Item c: Dues frozen & Claim filing ──────────────────────────────────────────────────────────────

@router.get("/api/v1/office/compliance/insolvency-cases/{case_id}/dues-summary")
async def get_frozen_dues_summary(
    case_id: str,
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Calculates frozen dues for the establishment: PF/pension dues (principal) kept apart from
    damages (s.14B) and interest (s.7Q)."""
    office = await _office(session, actor)
    row = (await session.execute(
        select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
    )).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Insolvency case not found")

    eid = row["establishment_id"]
    open_demands = (await session.execute(
        select(demands).where(demands.c.establishment_id == eid, demands.c.state == "OPEN")
    )).mappings().all()

    principal_paise = 0
    damages_paise = 0
    interest_paise = 0
    demand_items = []

    for d in open_demands:
        amt = int(d["amount_paise"])
        k = d["kind"]
        if k in ("DUES_7A", "PRINCIPAL"):
            principal_paise += amt
        elif k == "DAMAGES_14B":
            damages_paise += amt
        elif k == "INTEREST_7Q":
            interest_paise += amt
        else:
            principal_paise += amt
        demand_items.append({
            "demand_id": d["demand_id"],
            "kind": k,
            "wage_month": d.get("wage_month"),
            "amount_paise": amt
        })

    return envelope({
        "case_id": case_id,
        "establishment_id": eid,
        "principal_paise": principal_paise,
        "damages_paise": damages_paise,
        "interest_paise": interest_paise,
        "total_dues_paise": principal_paise + damages_paise + interest_paise,
        "demands": demand_items
    })


class ClaimSubmissionInput(BaseModel):
    claim_reference: str = Field(min_length=2, max_length=100)
    form_type: Literal["FORM_B", "FORM_C", "FORM_F"] = "FORM_B"
    principal_paise: int = Field(ge=0)
    damages_paise: int = Field(default=0, ge=0)
    interest_paise: int = Field(default=0, ge=0)
    note: str | None = None


@router.post("/api/v1/office/compliance/insolvency-cases/{case_id}/claims")
async def file_insolvency_claim(
    case_id: str,
    body: ClaimSubmissionInput,
    actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "fo.recovery_officer", "fo.da_compliance")),
    session: AsyncSession = Depends(db)
) -> dict:
    """Files proof of claim with the IRP/RP/Liquidator with PF principal kept apart from s.14B damages and s.7Q interest."""
    async with session.begin():
        office = await _office(session, actor)
        row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().first()
        if not row or row["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Insolvency case not found")

        total_claimed = body.principal_paise + body.damages_paise + body.interest_paise
        history = list(row["history"])
        history.append({
            "at": now().isoformat(),
            "action": "CLAIM_FILED",
            "claim_reference": body.claim_reference,
            "form_type": body.form_type,
            "principal_paise": body.principal_paise,
            "damages_paise": body.damages_paise,
            "interest_paise": body.interest_paise,
            "total_claimed_paise": total_claimed,
            "by": actor.subject,
            "note": body.note
        })

        await session.execute(
            update(insolvency_cases)
            .where(insolvency_cases.c.case_id == case_id)
            .values(
                claim_filed=True,
                claim_filed_at=now(),
                claim_reference=body.claim_reference,
                form_type=body.form_type,
                claimed_principal_paise=body.principal_paise,
                claimed_damages_paise=body.damages_paise,
                claimed_interest_paise=body.interest_paise,
                total_claimed_paise=total_claimed,
                state="CLAIM_FILED",
                history=history
            )
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="compliance.insolvency_claim_filed", target_type="insolvency_case",
                    target_id=case_id, detail=f"Claim {body.claim_reference} filed: ₹{total_claimed // 100:,}")

        updated_row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().one()
        names = await _names(session)
        result = case_view(updated_row, names)
    return envelope(result)


# ── Item d: Resolution Plan check ──────────────────────────────────────────────────────────────────

class ResolutionPlanInput(BaseModel):
    plan_reference: str = Field(min_length=2, max_length=100)
    resolution_applicant: str | None = None
    approved_by_coc_on: date | None = None
    plan_principal_paise: int = Field(ge=0)
    plan_damages_paise: int = Field(default=0, ge=0)
    plan_interest_paise: int = Field(default=0, ge=0)
    note: str | None = None


@router.post("/api/v1/office/compliance/insolvency-cases/{case_id}/resolution-plans")
async def check_resolution_plan(
    case_id: str,
    body: ResolutionPlanInput,
    actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "fo.recovery_officer")),
    session: AsyncSession = Depends(db)
) -> dict:
    """The resolution plan checked: record the plan's amount for PF dues; the plan is flagged NON-COMPLIANT
    unless PF dues (principal) are paid in full — they are outside the liquidation estate (IBC s.36(4)(a)(iii));
    damages/interest may be compromised."""
    async with session.begin():
        office = await _office(session, actor)
        row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().first()
        if not row or row["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Insolvency case not found")

        claimed_principal = int(row["claimed_principal_paise"])

        # IBC s.36(4)(a)(iii): PF dues are outside the liquidation estate and cannot be compromised
        is_compliant = body.plan_principal_paise >= claimed_principal
        plan_status = "COMPLIANT" if is_compliant else "NON_COMPLIANT"

        if not is_compliant:
            compliance_reason = (
                f"NON-COMPLIANT: PF dues (principal) must be paid in full under IBC s.36(4)(a)(iii). "
                f"Plan offers ₹{body.plan_principal_paise // 100:,} against claimed ₹{claimed_principal // 100:,}."
            )
        else:
            compliance_reason = (
                "COMPLIANT: PF dues (principal) are paid in full in accordance with IBC s.36(4)(a)(iii). "
                "Damages (s.14B) and interest (s.7Q) may be compromised as proposed."
            )

        plan_detail = {
            "plan_reference": body.plan_reference,
            "resolution_applicant": body.resolution_applicant,
            "approved_by_coc_on": iso(body.approved_by_coc_on),
            "plan_principal_paise": body.plan_principal_paise,
            "plan_damages_paise": body.plan_damages_paise,
            "plan_interest_paise": body.plan_interest_paise,
            "total_plan_paise": body.plan_principal_paise + body.plan_damages_paise + body.plan_interest_paise,
            "claimed_principal_paise": claimed_principal,
            "is_compliant": is_compliant,
            "status": plan_status,
            "compliance_reason": compliance_reason,
            "checked_by": actor.subject,
            "checked_at": now().isoformat(),
            "note": body.note
        }

        history = list(row["history"])
        history.append({
            "at": now().isoformat(),
            "action": "RESOLUTION_PLAN_CHECKED",
            "plan_status": plan_status,
            "is_compliant": is_compliant,
            "by": actor.subject,
            "reason": compliance_reason
        })

        await session.execute(
            update(insolvency_cases)
            .where(insolvency_cases.c.case_id == case_id)
            .values(
                resolution_plan=plan_detail,
                plan_status=plan_status,
                state="PLAN_CHECKED",
                history=history
            )
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"compliance.plan_{plan_status.lower()}", target_type="insolvency_case",
                    target_id=case_id, detail=compliance_reason)

        updated_row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().one()
        names = await _names(session)
        result = case_view(updated_row, names)
    return envelope(result)


# ── Item e: Realisations & Office Summary ───────────────────────────────────────────────────────────

class RealisationInput(BaseModel):
    amount_paise: int = Field(gt=0)
    mode: Literal["RESOLUTION_PLAN", "LIQUIDATION_PAYOUT", "IRP_DISBURSEMENT", "DIRECT", "OTHER"] = "RESOLUTION_PLAN"
    reference: str = Field(min_length=2, max_length=100)
    realised_on: date
    note: str | None = None


@router.post("/api/v1/office/compliance/insolvency-cases/{case_id}/realisations")
async def record_insolvency_realisation(
    case_id: str,
    body: RealisationInput,
    actor: Actor = Depends(require_stakeholder("fo.recovery_officer", "fo.apfc", "fo.oic")),
    session: AsyncSession = Depends(db)
) -> dict:
    """Records realization received from resolution applicant, liquidator payout, or IRP disbursement,
    updating recovery amounts and percentages."""
    async with session.begin():
        office = await _office(session, actor)
        row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().first()
        if not row or row["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Insolvency case not found")

        current_realised = int(row["realised_paise"])
        total_claimed = int(row["total_claimed_paise"])
        new_realised = current_realised + body.amount_paise
        new_state = "CLOSED" if new_realised >= total_claimed and total_claimed > 0 else row["state"]

        history = list(row["history"])
        history.append({
            "at": now().isoformat(),
            "action": "REALISATION_RECORDED",
            "amount_paise": body.amount_paise,
            "mode": body.mode,
            "reference": body.reference,
            "realised_on": body.realised_on.isoformat(),
            "by": actor.subject,
            "note": body.note
        })

        await session.execute(
            update(insolvency_cases)
            .where(insolvency_cases.c.case_id == case_id)
            .values(
                realised_paise=new_realised,
                state=new_state,
                history=history
            )
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="compliance.insolvency_realisation", target_type="insolvency_case",
                    target_id=case_id, detail=f"Recovered ₹{body.amount_paise // 100:,} via {body.mode}")

        updated_row = (await session.execute(
            select(insolvency_cases).where(insolvency_cases.c.case_id == case_id)
        )).mappings().one()
        names = await _names(session)
        result = case_view(updated_row, names)
    return envelope(result)


@router.get("/api/v1/office/compliance/insolvency/summary")
async def office_insolvency_summary(
    actor: Actor = Depends(INSOLVENCY_OFFICERS),
    session: AsyncSession = Depends(db)
) -> dict:
    """Summary of insolvency cases for the office: dues claimed, amount recovered, recovery %,
    breakdown by stage, claims pending/due soon, and resolution plan compliance."""
    office = await _office(session, actor)
    rows = (await session.execute(
        select(insolvency_cases).where(insolvency_cases.c.office_id == office)
    )).mappings().all()

    today = current_date()
    total_cases = len(rows)
    by_stage = Counter(r["stage"] for r in rows)
    by_state = Counter(r["state"] for r in rows)

    claims_pending = sum(1 for r in rows if not r["claim_filed"])
    claims_filed = sum(1 for r in rows if r["claim_filed"])

    claims_due_soon = 0
    for r in rows:
        if not r["claim_filed"]:
            dl = date.fromisoformat(r["claim_deadline"]) if isinstance(r["claim_deadline"], str) else r["claim_deadline"]
            if 0 <= (dl - today).days <= 3:
                claims_due_soon += 1

    total_claimed = sum(int(r["total_claimed_paise"]) for r in rows)
    total_recovered = sum(int(r["realised_paise"]) for r in rows)
    overall_recovery_pct = round(total_recovered * 100.0 / total_claimed, 2) if total_claimed > 0 else 0.0

    compliant_plans = sum(1 for r in rows if r["plan_status"] == "COMPLIANT")
    non_compliant_plans = sum(1 for r in rows if r["plan_status"] == "NON_COMPLIANT")
    moratorium_active = sum(1 for r in rows if r["moratorium_active"] and r["state"] != "CLOSED")

    return envelope({
        "as_of": today.isoformat(),
        "office_id": office,
        "total_cases": total_cases,
        "by_stage": dict(by_stage),
        "by_state": dict(by_state),
        "claims_pending": claims_pending,
        "claims_filed": claims_filed,
        "claims_due_soon": claims_due_soon,
        "total_claimed_paise": total_claimed,
        "total_recovered_paise": total_recovered,
        "overall_recovery_pct": overall_recovery_pct,
        "resolution_plans": {
            "compliant": compliant_plans,
            "non_compliant": non_compliant_plans,
            "total": compliant_plans + non_compliant_plans
        },
        "moratorium_active_cases": moratorium_active
    })


# ── Employer view ───────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/employers/me/insolvency-cases")
async def employer_insolvency_cases(
    actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")),
    session: AsyncSession = Depends(db)
) -> dict:
    """The employer reads its establishment's insolvency case, stage, claim status, deadline, and moratorium status."""
    eid = actor.establishment_id
    if not eid:
        raise Problem(403, "/problems/forbidden", "Establishment ID required in session")
    rows = (await session.execute(
        select(insolvency_cases).where(insolvency_cases.c.establishment_id == eid)
        .order_by(insolvency_cases.c.created_at.desc())
    )).mappings().all()
    names = await _names(session)
    return envelope([case_view(r, names) for r in rows])
