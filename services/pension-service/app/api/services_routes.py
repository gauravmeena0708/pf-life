"""Phase 2, slice 3: pensioner self-service (PPO, slips, life certificate, bank change, declarations), the office's
pension enquiry, overdue life certificates, suspension / resumption and updation activities, and the public
pension enquiries (CAPTCHA checked by the gateway; minimal disclosure)."""
import hashlib
import hmac
import os
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import amount_for, approved, catch_up_payments, month_of, today
from app.domain.services import DA_ACTIVITIES, PRO_ACTIVITIES, apply_activity, lc_state, load, renew_life_certificate, set_status
from app.infra.db import sessions
from app.infra.tables import office_staff, pension_payments, pension_revisions, pensioners, updation_activities
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
PENSIONER = require_stakeholder("pensioner", "family_pensioner")
PENSION_OFFICE = require_stakeholder("fo.apfc_pension", "fo.da_pension")
APFC_PENSION = require_stakeholder("fo.apfc_pension")
DA_PENSION = require_stakeholder("fo.da_pension")
JP_SECRET = os.getenv("MOCK_JEEVAN_PRAMAAN_SECRET", "dev-mock-jeevan-pramaan")


async def db():
    async with sessions()() as session:
        yield session


def iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _own(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(pensioners).where(pensioners.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "No pension found for this login")
    return dict(row)


async def _in_office(session: AsyncSession, actor: Actor, ppo_id: str) -> dict[str, Any]:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    p = await load(session, ppo_id)
    if not office or not p or p["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Pension not found in your office")
    return p


def _lc(p: dict[str, Any]) -> dict[str, Any]:
    return {"state": lc_state(p), "valid_till": iso(p["life_certificate_valid_till"]), "source": p["life_certificate_source"],
            "reference": p["life_certificate_ref"]}


# ── pensioner self-service ──────────────────────────────────────────────────────────────────────

@router.get("/api/v1/pensioners/me/ppo")
async def my_ppo(actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _own(session, actor)
        now = amount_for(p, await approved(session, p["ppo_id"]), month_of(today()))
    return envelope({"title": "Pension Payment Order (synthetic)", "ppo_id": p["ppo_id"], "name": p["name"], "uan": p["uan"],
                     "date_of_birth": iso(p["date_of_birth"]), "pension_type": "Superannuation" if p["age_at_start"] >= 58 else "Early",
                     "pension_start": iso(p["pension_start"]), "original_monthly_paise": p["original_monthly_paise"],
                     "current_monthly_paise": now["monthly_paise"], "working": now["working"], "rule_version": now["rule_version"],
                     "issuing_office": p["office_id"], "disbursing_bank": {"ifsc": p["bank_ifsc"], "account_last4": p["bank_account_last4"]},
                     "status": p["status"]})


@router.get("/api/v1/pensioners/me/pension-slips")
async def my_slip(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _own(session, actor)
        await catch_up_payments(session, p)
        rows = (await session.execute(select(pension_payments).where(pension_payments.c.ppo_id == p["ppo_id"],
                                                                      pension_payments.c.month == month))).mappings().all()
    if not rows:
        raise Problem(404, "/problems/not-found", "No pension was credited for that month",
                      "A month is credited on its last day; a suspended pension is credited when it is resumed.")
    lines = [{"kind": r["kind"], "amount_paise": r["amount_paise"], "paid_on": iso(r["paid_on"])} for r in rows]
    gross = sum(x["amount_paise"] for x in lines)
    return envelope({"ppo_id": p["ppo_id"], "name": p["name"], "month": month, "lines": lines, "gross_paise": gross,
                     "deductions": {"commutation_paise": 0, "recovery_paise": 0, "tds_paise": 0}, "net_paise": gross,
                     "bank_account_last4": p["bank_account_last4"]})


@router.get("/api/v1/pensioners/me/life-certificate")
async def my_life_certificate(actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    p = await _own(session, actor)
    return envelope({"ppo_id": p["ppo_id"], **_lc(p), "pension_status": p["status"]})


class DlcSubmission(BaseModel):
    face_authentication_consent: bool


@router.post("/api/v1/pensioners/me/life-certificate/submissions", status_code=201)
async def submit_dlc(body: DlcSubmission, actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    """Mock Jeevan Pramaan: face authentication is simulated; the certificate counts at once, as a real DLC
    counts once the field office's system receives it."""
    if not body.face_authentication_consent:
        raise Problem(422, "/problems/validation", "Consent to face authentication is required")
    async with session.begin():
        p = await _own(session, actor)
        pramaan_id = f"JP{secrets.randbelow(10**8):08d}"
        valid = await renew_life_certificate(session, p, "JEEVAN_PRAMAAN", pramaan_id)
        resumed = p["status"] == "SUSPENDED" and (p["status_reason"] or "").startswith("Life certificate")
        if resumed:
            await set_status(session, p, "IN_PAYMENT", "Life certificate received (Jeevan Pramaan)")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.dlc_submitted",
                    target_type="pension", target_id=p["ppo_id"], detail=pramaan_id)
    return envelope({"pramaan_id": pramaan_id, "valid_till": valid.isoformat(), "resumed": resumed, "mock": True,
                     "note": "MOCK Jeevan Pramaan: no real face authentication took place."})


class DlcEvent(BaseModel):
    pramaan_id: str = Field(pattern=r"^JP[0-9]{8}$")
    ppo_id: str = Field(min_length=3, max_length=40)
    status: str = Field(pattern="^(ACCEPTED|REJECTED)$")
    signature: str = Field(min_length=64, max_length=64)


@router.post("/api/v1/integrations/mock-jeevan-pramaan/dlc-events")
async def dlc_event(body: DlcEvent, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    """Signed callback from the mock Jeevan Pramaan (HMAC-SHA256 of pramaan_id|ppo_id|status)."""
    expected = hmac.new(JP_SECRET.encode(), f"{body.pramaan_id}|{body.ppo_id}|{body.status}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.signature):
        raise Problem(401, "/problems/bad-signature", "The callback signature does not match")
    async with session.begin():
        p = await load(session, body.ppo_id)
        if not p:
            raise Problem(404, "/problems/not-found", "Unknown PPO")
        if body.status == "ACCEPTED":
            await renew_life_certificate(session, p, "JEEVAN_PRAMAAN", body.pramaan_id)
        else:
            await session.execute(update(pensioners).where(pensioners.c.ppo_id == body.ppo_id).values(life_certificate_ref=body.pramaan_id + " (rejected)"))
    return envelope({"ppo_id": body.ppo_id, "recorded": body.status})


class BankChange(BaseModel):
    ifsc: str = Field(pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    account_number: str = Field(pattern=r"^[0-9]{9,18}$")


@router.post("/api/v1/pensioners/me/bank-change-requests", status_code=201)
async def bank_change(body: BankChange, actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    """The new account is checked by a mock penny-drop; the change is an updation activity the APFC (Pension) settles."""
    if body.account_number.endswith("0000"):
        raise Problem(422, "/problems/penny-drop-failed", "The bank account could not be validated (mock penny-drop)")
    async with session.begin():
        p = await _own(session, actor)
        require_step_up(actor, "change-pension-bank", p["ppo_id"])
        activity = await _new_activity(session, p["ppo_id"], "BASIC_DETAILS", "ONLINE",
                                       {"bank_ifsc": body.ifsc, "bank_account_last4": body.account_number[-4:], "requested_by": "pensioner"},
                                       actor, status="PENDING")
    return envelope({**activity, "note": "Validated by a mock penny-drop; your office approves the change before the next credit."})


class Declaration(BaseModel):
    kind: str = Field(pattern="^(NON_REMARRIAGE|NON_EMPLOYMENT)$")
    declared: bool


@router.post("/api/v1/pensioners/me/declarations", status_code=201)
async def declare(body: Declaration, actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    if not body.declared:
        raise Problem(422, "/problems/validation", "The declaration must be confirmed")
    async with session.begin():
        p = await _own(session, actor)
        declarations = dict(p["declarations"] or {})
        declarations[body.kind] = today().isoformat()
        await session.execute(update(pensioners).where(pensioners.c.ppo_id == p["ppo_id"]).values(declarations=declarations))
    return envelope({"ppo_id": p["ppo_id"], "declarations": declarations})


# ── the office: enquiry, overdue certificates, suspension, updation activities ──────────────────────────

@router.get("/api/v1/office/pensions/enquiries")
async def enquiry(ppo: str | None = None, memberId: str | None = None, uan: str | None = None, actor: Actor = Depends(PENSION_OFFICE),
                  session: AsyncSession = Depends(db)) -> dict:
    if not (ppo or uan or memberId):
        raise Problem(422, "/problems/validation", "Enter a PPO number, member ID or UAN")
    async with session.begin():
        row = (await session.execute(select(pensioners.c.ppo_id).where(or_(pensioners.c.ppo_id == (ppo or ""), pensioners.c.uan == (uan or ""))))).first()
        if not row:
            raise Problem(404, "/problems/not-found", "The entered PPO / member ID / UAN does not belong to your office")
        p = await _in_office(session, actor, row[0])
        await catch_up_payments(session, p)
        payments = (await session.execute(select(pension_payments).where(pension_payments.c.ppo_id == p["ppo_id"])
                                          .order_by(pension_payments.c.paid_on.desc()))).mappings().all()
        revisions = (await session.execute(select(pension_revisions).where(pension_revisions.c.ppo_id == p["ppo_id"])
                                           .order_by(pension_revisions.c.proposed_at))).mappings().all()
        now = amount_for(p, await approved(session, p["ppo_id"]), month_of(today()))
    return envelope({
        "ppo_details": {"ppo_id": p["ppo_id"], "name": p["name"], "uan": p["uan"], "pension_type": "Superannuation" if p["age_at_start"] >= 58 else "Early",
                        "pension_start": iso(p["pension_start"]), "monthly_paise": now["monthly_paise"], "status": p["status"],
                        "status_reason": p["status_reason"], "life_certificate": _lc(p), "declarations": p["declarations"] or {}},
        "beneficiary_details": [],
        "pension_payment_details": [{"month": r["month"], "kind": r["kind"], "amount_paise": r["amount_paise"], "paid_on": iso(r["paid_on"])} for r in payments],
        "scheme_certificate_issue_details": None,
        "service_details": {"service_months": p["service_months"], "pensionable_salary_paise": p["pensionable_salary_paise"],
                            "age_at_start": p["age_at_start"], "working": now["working"]},
        "arrears_adjustment_details": [{"revision_id": r["revision_id"], "state": r["state"], "effective_from": iso(r["effective_from"]),
                                        "old_monthly_paise": r["old_monthly_paise"], "new_monthly_paise": r["new_monthly_paise"],
                                        "arrears_paise": r["arrears_paise"]} for r in revisions],
        "recovery_details": [], "tds_details": [],
        "note": "Synthetic record. Beneficiaries, recoveries and TDS on pension are not modelled in this demonstration."})


@router.get("/api/v1/office/pensions/life-certificates/overdue")
async def overdue(actor: Actor = Depends(PENSION_OFFICE), session: AsyncSession = Depends(db)) -> dict:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    rows = (await session.execute(select(pensioners).where(pensioners.c.office_id == (office or ""), pensioners.c.status != "STOPPED")
                                  .order_by(pensioners.c.life_certificate_valid_till))).mappings().all()
    return envelope([{"ppo_id": r["ppo_id"], "name": r["name"], "status": r["status"], **_lc(dict(r))} for r in rows if lc_state(dict(r)) == "EXPIRED"])


class StatusChange(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/pensions/{ppoId}/suspensions")
async def suspend(ppoId: str, body: StatusChange, actor: Actor = Depends(APFC_PENSION), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _in_office(session, actor, ppoId)
        if p["status"] != "IN_PAYMENT":
            raise Problem(409, "/problems/invalid-state", "Only a pension in payment can be suspended", f"Status: {p['status']}.")
        if lc_state(p) == "VALID":
            raise Problem(409, "/problems/life-certificate-valid", "The life certificate is valid",
                          f"Valid till {iso(p['life_certificate_valid_till'])}; a pension is suspended only when it has lapsed.")
        require_step_up(actor, "suspend-pension", ppoId)
        p = await set_status(session, p, "SUSPENDED", f"Life certificate lapsed: {body.reason}")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.suspended",
                    target_type="pension", target_id=ppoId, detail=body.reason)
    return envelope({"ppo_id": ppoId, "status": p["status"], "status_reason": p["status_reason"]})


@router.post("/api/v1/office/pensions/{ppoId}/resumptions")
async def resume(ppoId: str, body: StatusChange, actor: Actor = Depends(APFC_PENSION), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _in_office(session, actor, ppoId)
        if p["status"] != "SUSPENDED":
            raise Problem(409, "/problems/invalid-state", "Only a suspended pension can be resumed", f"Status: {p['status']}.")
        if lc_state(p) != "VALID":
            raise Problem(409, "/problems/life-certificate-lapsed", "A valid life certificate is needed first",
                          "Record a Jeevan Pramaan or a physical life certificate (updation activity) first.")
        require_step_up(actor, "resume-pension", ppoId)
        p = await set_status(session, p, "IN_PAYMENT", body.reason)
        released = (await session.execute(select(pension_payments).where(pension_payments.c.ppo_id == ppoId,
                                                                         pension_payments.c.paid_on == today()))).mappings().all()
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.resumed",
                    target_type="pension", target_id=ppoId, detail=body.reason)
    return envelope({"ppo_id": ppoId, "status": "IN_PAYMENT", "released_months": [r["month"] for r in released if r["kind"] == "MONTHLY"],
                     "released_paise": sum(r["amount_paise"] for r in released if r["kind"] == "MONTHLY")})


def _activity_view(a: Any) -> dict[str, Any]:
    return {"activity_id": a["activity_id"], "ppo_id": a["ppo_id"], "activity": a["activity"], "mode": a["mode"], "status": a["status"],
            "details": a["details"], "initiated_role": a["initiated_role"], "decision_note": a["decision_note"],
            "created_at": iso(a["created_at"]), "updated_at": iso(a["updated_at"])}


async def _new_activity(session: AsyncSession, ppo_id: str, activity: str, mode: str, details: dict[str, Any], actor: Actor,
                        status: str = "PENDING") -> dict[str, Any]:
    open_same = (await session.execute(select(updation_activities.c.activity_id).where(
        updation_activities.c.ppo_id == ppo_id, updation_activities.c.activity == activity,
        updation_activities.c.status.in_(("NEW", "PENDING", "SENT_BACK_TO_DA"))))).first()
    if open_same:
        raise Problem(409, "/problems/activity-open", "The same activity is already in progress for this PPO", f"Activity {open_same[0]}.")
    now = datetime.now(UTC)
    row = {"activity_id": f"UPD-{secrets.token_hex(4).upper()}", "ppo_id": ppo_id, "activity": activity, "mode": mode, "status": status,
           "details": details, "initiated_by": actor.subject, "initiated_role": actor.stakeholder, "created_at": now, "updated_at": now}
    await session.execute(insert(updation_activities).values(**row))
    return _activity_view({**row, "decision_note": None})


class ActivityInput(BaseModel):
    activity: str = Field(pattern="^(BASIC_DETAILS|PENSION_START|PENSION_STOP|DLC_REVALIDATION|UNHOLD_TRANSACTIONS|PHYSICAL_LC|DEATH|SPOUSE_REMARRIAGE)$")
    mode: str = Field(default="PHYSICAL", pattern="^(PHYSICAL|ONLINE)$")
    details: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/pensions/{ppoId}/updation-activities", status_code=201)
async def initiate(ppoId: str, body: ActivityInput, actor: Actor = Depends(DA_PENSION), session: AsyncSession = Depends(db)) -> dict:
    if body.activity not in DA_ACTIVITIES | PRO_ACTIVITIES:
        raise Problem(422, "/problems/validation", "Unknown activity")
    async with session.begin():
        await _in_office(session, actor, ppoId)
        require_step_up(actor, "initiate-pension-updation", ppoId)
        activity = await _new_activity(session, ppoId, body.activity, body.mode, {**body.details, "reason": body.reason}, actor)
    return envelope(activity)


@router.get("/api/v1/office/pensions/updation-activities")
async def tracker(activity: str | None = None, mode: str | None = None, status: str | None = None, actor: Actor = Depends(PENSION_OFFICE),
                  session: AsyncSession = Depends(db)) -> dict:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    q = select(updation_activities).join(pensioners, pensioners.c.ppo_id == updation_activities.c.ppo_id).where(
        pensioners.c.office_id == (office or "")).order_by(updation_activities.c.created_at.desc())
    for column, value in ((updation_activities.c.activity, activity), (updation_activities.c.mode, mode), (updation_activities.c.status, status)):
        if value:
            q = q.where(column == value)
    rows = (await session.execute(q)).mappings().all()
    return envelope([_activity_view(r) for r in rows])


class ActivityDecision(BaseModel):
    decision: str = Field(pattern="^(SETTLE|REJECT|SEND_BACK)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/pensions/updation-activities/{activityId}/decisions")
async def decide_activity(activityId: str, body: ActivityDecision, actor: Actor = Depends(APFC_PENSION),
                          session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        a = (await session.execute(select(updation_activities).where(updation_activities.c.activity_id == activityId)
                                   .with_for_update())).mappings().first()
        if not a:
            raise Problem(404, "/problems/not-found", "Activity not found")
        await _in_office(session, actor, a["ppo_id"])
        if a["status"] not in ("NEW", "PENDING"):
            raise Problem(409, "/problems/invalid-state", "This activity is already decided", f"Status: {a['status']}.")
        if a["initiated_by"] == actor.subject:
            raise Problem(403, "/problems/separation-of-duties", "You initiated this activity", "A different officer must settle it.")
        require_step_up(actor, "decide-pension-updation", activityId)
        outcome = None
        status = {"SETTLE": "SETTLED", "REJECT": "REJECTED", "SEND_BACK": "SENT_BACK_TO_DA"}[body.decision]
        if status == "SETTLED":
            outcome = await apply_activity(session, dict(a))
        await session.execute(update(updation_activities).where(updation_activities.c.activity_id == activityId).values(
            status=status, decided_by=actor.subject, decision_note=f"{body.note}{' — ' + outcome if outcome else ''}", updated_at=datetime.now(UTC)))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"pension.updation.{status.lower()}",
                    target_type="pension", target_id=a["ppo_id"], detail=f"{activityId} {a['activity']}")
        a = (await session.execute(select(updation_activities).where(updation_activities.c.activity_id == activityId))).mappings().one()
    return envelope(_activity_view(a))


# ── public enquiries (the gateway checks the CAPTCHA; answers disclose as little as possible) ──────────

def _masked(name: str) -> str:
    return " ".join(part[0] + "*" * (len(part) - 1) for part in name.split())


class PpoLookup(BaseModel):
    bank_account_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    uan: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    date_of_birth: date


class PpoEnquiry(BaseModel):
    ppo_id: str = Field(min_length=3, max_length=40)
    date_of_birth: date | None = None


class LcLookup(BaseModel):
    ppo_id: str | None = Field(default=None, max_length=40)
    pramaan_id: str | None = Field(default=None, pattern=r"^JP[0-9]{8}$")


@router.post("/api/v1/public/pension/ppo-lookups")
async def know_your_ppo(body: PpoLookup, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    if not (body.bank_account_last4 or body.uan):
        raise Problem(422, "/problems/validation", "Enter the bank account's last four digits or the UAN / member ID")
    rows = (await session.execute(select(pensioners).where(pensioners.c.date_of_birth == body.date_of_birth))).mappings().all()
    hit = next((r for r in rows if (body.uan and r["uan"] == body.uan) or (body.bank_account_last4 and r["bank_account_last4"] == body.bank_account_last4)), None)
    if not hit:
        return envelope({"found": False, "next_step": "Check the details, or contact your pension disbursing office."})
    return envelope({"found": True, "ppo_id": hit["ppo_id"], "office_id": hit["office_id"], "name": _masked(hit["name"]), "label": "SYNTHETIC_DEMO"})


@router.post("/api/v1/public/pension/payment-enquiries")
async def payment_enquiry(body: PpoEnquiry, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await load(session, body.ppo_id)
        if not p or p["date_of_birth"] != body.date_of_birth:
            return envelope({"found": False, "next_step": "The PPO number and date of birth do not match a pension."})
        await catch_up_payments(session, p)
        paid = (await session.execute(select(pension_payments.c.month, pension_payments.c.paid_on).where(
            pension_payments.c.ppo_id == p["ppo_id"], pension_payments.c.kind == "MONTHLY").order_by(pension_payments.c.month.desc()).limit(12))).all()
    return envelope({"found": True, "ppo_id": p["ppo_id"], "months": [{"month": m, "credited_on": iso(d)} for m, d in paid],
                     "note": "Amounts are shown only after login (minimal disclosure).", "label": "SYNTHETIC_DEMO"})


@router.post("/api/v1/public/pension/status-enquiries")
async def status_enquiry(body: PpoEnquiry, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    p = await load(session, body.ppo_id)
    if not p:
        return envelope({"found": False})
    return envelope({"found": True, "ppo_id": p["ppo_id"], "pension_status": {"IN_PAYMENT": "Active", "SUSPENDED": "Suspended", "STOPPED": "Stopped", "PENDING": "In process"}[p["status"]],
                     "life_certificate_due": iso(p["life_certificate_valid_till"]), "label": "SYNTHETIC_DEMO"})


@router.post("/api/v1/public/pension/life-certificate-lookups")
async def lc_lookup(body: LcLookup, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    if not (body.ppo_id or body.pramaan_id):
        raise Problem(422, "/problems/validation", "Enter the PPO number or the Jeevan Pramaan ID")
    q = select(pensioners).where(pensioners.c.ppo_id == body.ppo_id) if body.ppo_id else select(pensioners).where(pensioners.c.life_certificate_ref == body.pramaan_id)
    p = (await session.execute(q)).mappings().first()
    if not p:
        return envelope({"found": False})
    return envelope({"found": True, "state": lc_state(dict(p)), "valid_till_month": month_of(p["life_certificate_valid_till"]) if p["life_certificate_valid_till"] else None,
                     "label": "SYNTHETIC_DEMO"})
