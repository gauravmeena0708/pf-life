"""Phase 2, slice 4: pension settlement (Form 10D → Input Data Sheet → worksheet → PPO → initial arrear → e-sign →
dispatch), scheme certificates and their surrender, service aggregation, transfers-in, the CPPS monthly
disbursement run with the (mock) sponsor bank's paid statement and reconciliation, and the office's BRS.

Every step is a separate officer (maker ≠ checker along PEN 11.7–11.9, illustrative); every amount comes from the
pension formula in the rule set in force on the date the pension starts."""
import hashlib
import hmac
import os
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import age_on, catch_up_payments, month_of, months, today
from app.infra.db import sessions
from app.infra.tables import (brs_statements, disbursement_runs, member_service, office_staff, pension_claims, pension_payments,
                              pensioners, scheme_certificates)
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import family_pension_on, pension_on, rules_on, section

router = APIRouter()
MEMBER = require_stakeholder("member")
BANK_SECRET = os.getenv("MOCK_PENSION_BANK_SECRET", "dev-mock-pension-bank")
ROLE = {"fo.da_accounts": "DA (Accounts)", "fo.ao": "AO", "fo.da_pension": "DA (Pension)", "fo.ss_pension": "SS (Pension)",
        "fo.apfc_pension": "APFC (Pension)", "member": "Member"}


async def db():
    async with sessions()() as session:
        yield session


def iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day))


async def _office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


async def _claim(session: AsyncSession, claim_id: str, actor: Actor, *states: str) -> dict[str, Any]:
    c = (await session.execute(select(pension_claims).where(pension_claims.c.claim_id == claim_id).with_for_update())).mappings().first()
    if not c or c["office_id"] != await _office(session, actor):
        raise Problem(404, "/problems/not-found", "Pension claim not found in your office")
    if states and c["state"] not in states:
        raise Problem(409, "/problems/invalid-state", "This step is not possible now", f"State: {c['state']}.")
    return dict(c)


def _separate(c: dict[str, Any], actor: Actor) -> None:
    """Maker ≠ checker: the officer who took the step being checked cannot check it. (The APFC (Pension) both
    approves the worksheet and e-signs the PPO, as in the Pension Manual; other officers stand between.)"""
    if c["history"] and c["history"][-1].get("by") == actor.subject:
        raise Problem(403, "/problems/separation-of-duties", "You took the step being checked", "A different officer must check it.")


async def _move(session: AsyncSession, c: dict[str, Any], state: str, actor: Actor, note: str, **values: Any) -> dict[str, Any]:
    history = [*c["history"], {"state": state, "role": actor.stakeholder, "by": actor.subject, "note": note, "at": datetime.now(UTC).isoformat()}]
    await session.execute(update(pension_claims).where(pension_claims.c.claim_id == c["claim_id"]).values(
        state=state, history=history, updated_at=datetime.now(UTC), **values))
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"pension_claim.{state.lower()}",
                target_type="pension_claim", target_id=c["claim_id"], detail=note[:200])
    return {**c, **values, "state": state, "history": history}


def _view(c: dict[str, Any]) -> dict[str, Any]:
    return {"claim_id": c["claim_id"], "uan": c["uan"], "name": c["name"], "state": c["state"], "pension_from": iso(c["pension_from"]),
            "service_months": c["service_months"], "aggregated": c["aggregated"], "pensionable_salary_paise": c["pensionable_salary_paise"],
            "ids": c.get("ids"), "worksheet": c.get("worksheet"), "ppo_id": c.get("ppo_id"), "arrears": c.get("arrears"),
            "history": [{**{k: v for k, v in h.items() if k != "by"}, "role": ROLE.get(h["role"], h["role"])} for h in c["history"]],
            "next_step": NEXT.get(c["state"]), "kind": c.get("kind", "MEMBER"), "family": c.get("family")}


NEXT = {"SUBMITTED": "DA (Accounts) prepares the Input Data Sheet", "IDS_PREPARED": "AO approves the Input Data Sheet",
        "IDS_APPROVED": "DA (Pension) generates the worksheet (after adding any past service)", "WORKSHEET_PREPARED": "APFC (Pension) approves the worksheet",
        "WORKSHEET_APPROVED": "DA (Pension) issues the PPO", "PPO_ISSUED": "DA (Pension) proposes the initial arrear",
        "ARREAR_PROPOSED": "SS (Pension) checks the initial arrear", "ARREAR_CHECKED": "APFC (Pension) e-signs the PPO",
        "PPO_SIGNED": "DA (Pension) dispatches the PPO; the pension is then paid", "DISPATCHED": None, "RETURNED": "Corrected and resubmitted"}


# ── member: Form 10D, status, scheme certificate ───────────────────────────────────────────────

class PensionApplication(BaseModel):
    pension_from: date | None = None              # default: the later of the day after exit and the 58th birthday


async def _me(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    m = (await session.execute(select(member_service).where(member_service.c.subject == actor.subject))).mappings().first()
    if not m:
        raise Problem(404, "/problems/not-found", "No service record found")
    return dict(m)


@router.post("/api/v1/members/me/pension-applications", status_code=201)
async def apply(body: PensionApplication, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        m = await _me(session, actor)
        if not m["date_of_exit"]:
            raise Problem(422, "/problems/not-eligible", "Mark your date of exit first", "A monthly pension starts after leaving service.")
        rules = await rules_on(session, today())
        p = section(rules, "pension")
        at58 = date(m["date_of_birth"].year + p["normal_age_years"], m["date_of_birth"].month, min(m["date_of_birth"].day, 28))
        start = body.pension_from or max(m["date_of_exit"] + timedelta(days=1), at58)
        service = months_between(m["date_of_joining"], m["date_of_exit"])
        check = pension_on(m["eps_wages_paise"], service, age_on(m["date_of_birth"], start), rules)
        if not check["eligible"]:
            raise Problem(422, "/problems/not-eligible", "Not eligible for a monthly pension", check["reason"] +
                          (" You can ask for a scheme certificate instead." if "years of service" in check["reason"] else ""))
        if start <= m["date_of_exit"] or start > today() + timedelta(days=366):
            raise Problem(422, "/problems/validation", "The pension must start after the date of exit and within a year")
        if (await session.execute(select(pension_claims.c.claim_id).where(pension_claims.c.member_subject == actor.subject,
                                                                          pension_claims.c.state != "REJECTED"))).first():
            raise Problem(409, "/problems/already-applied", "A pension application is already on file")
        claim = {"claim_id": f"PC-{secrets.token_hex(4).upper()}", "member_subject": actor.subject, "uan": m["uan"] or "", "name": m["name"],
                 "date_of_birth": m["date_of_birth"], "account_link_id": m["account_link_id"], "office_id": m["office_id"] or "RO-DEMO-01",
                 "pension_from": start, "state": "SUBMITTED", "service_months": service, "aggregated": [],
                 "pensionable_salary_paise": m["eps_wages_paise"],
                 "history": [{"state": "SUBMITTED", "role": "member", "by": actor.subject, "note": "Form 10D filed online", "at": datetime.now(UTC).isoformat()}]}
        await session.execute(insert(pension_claims).values(**claim))
    return envelope({**_view(claim), "estimate": {k: check[k] for k in ("monthly_paise", "working")}})


@router.get("/api/v1/members/me/pension-applications")
async def my_applications(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(pension_claims).where(pension_claims.c.member_subject == actor.subject)
                                  .order_by(pension_claims.c.created_at.desc()))).mappings().all()
    return envelope([_view(dict(r)) for r in rows])


class Confirm(BaseModel):
    confirm: bool


@router.post("/api/v1/members/me/pension-scheme-certificates", status_code=201)
async def request_certificate(body: Confirm, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """Form 10C option: keep pension service for later instead of withdrawing it (illustrative: issued at once)."""
    if not body.confirm:
        raise Problem(422, "/problems/validation", "Please confirm the request")
    async with session.begin():
        m = await _me(session, actor)
        require_step_up(actor, "request-scheme-certificate", m["uan"] or actor.subject)
        if not m["date_of_exit"]:
            raise Problem(422, "/problems/not-eligible", "Mark your date of exit first")
        service = months_between(m["date_of_joining"], m["date_of_exit"])
        min_years = section(await rules_on(session, today()), "pension")["min_service_years"]
        if service < 6:
            raise Problem(422, "/problems/not-eligible", "At least six months of service are needed for a scheme certificate")
        if service >= min_years * 12:
            raise Problem(422, "/problems/not-eligible", "You have enough service for a monthly pension", "Apply with Form 10D instead.")
        if (await session.execute(select(scheme_certificates.c.cert_id).where(scheme_certificates.c.member_subject == actor.subject,
                                                                              scheme_certificates.c.state != "CANCELLED"))).first():
            raise Problem(409, "/problems/already-issued", "A scheme certificate is already on file")
        cert = {"cert_id": f"SC-{secrets.token_hex(4).upper()}", "member_subject": actor.subject, "uan": m["uan"] or "",
                "service_months": service, "pensionable_salary_paise": m["eps_wages_paise"], "state": "ISSUED"}
        await session.execute(insert(scheme_certificates).values(**cert))
    return envelope({**cert, "note": "Your pension service is kept; it counts when you later take a monthly pension."})


def _cert(c: Any) -> dict[str, Any]:
    return {"cert_id": c["cert_id"], "uan": c["uan"], "service_months": c["service_months"], "pensionable_salary_paise": c["pensionable_salary_paise"],
            "state": c["state"], "surrender_purpose": c["surrender_purpose"], "issued_at": iso(c["issued_at"])}


@router.get("/api/v1/members/me/pension-scheme-certificate")
async def my_certificate(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    c = (await session.execute(select(scheme_certificates).where(scheme_certificates.c.member_subject == actor.subject)
                               .order_by(scheme_certificates.c.issued_at.desc()))).mappings().first()
    if not c:
        raise Problem(404, "/problems/not-found", "No scheme certificate")
    return envelope(_cert(c))


class Surrender(BaseModel):
    purpose: str = Field(pattern="^(MONTHLY_PENSION|WITHDRAWAL_BENEFIT)$")


@router.post("/api/v1/members/me/pension-scheme-certificates/{certId}/surrenders")
async def surrender(certId: str, body: Surrender, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = (await session.execute(select(scheme_certificates).where(scheme_certificates.c.cert_id == certId,
                                                                     scheme_certificates.c.member_subject == actor.subject))).mappings().first()
        if not c:
            raise Problem(404, "/problems/not-found", "Scheme certificate not found")
        if c["state"] != "ISSUED":
            raise Problem(409, "/problems/invalid-state", "Only an issued certificate can be surrendered", f"State: {c['state']}.")
        require_step_up(actor, "surrender-scheme-certificate", certId)
        await session.execute(update(scheme_certificates).where(scheme_certificates.c.cert_id == certId).values(
            state="SURRENDERED", surrender_purpose=body.purpose, updated_at=datetime.now(UTC)))
    return envelope({"cert_id": certId, "state": "SURRENDERED", "surrender_purpose": body.purpose,
                     "next_step": "The DA (Pension) validates and cancels the certificate; its service then counts."})


class Adjudication(BaseModel):
    decision: str = Field(pattern="^(CANCEL|RETURN)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/pensions/scheme-certificates/{certId}/surrender-adjudications")
async def adjudicate(certId: str, body: Adjudication, actor: Actor = Depends(require_stakeholder("fo.da_pension")),
                     session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        await _office(session, actor)
        c = (await session.execute(select(scheme_certificates).where(scheme_certificates.c.cert_id == certId))).mappings().first()
        if not c or c["state"] != "SURRENDERED":
            raise Problem(409, "/problems/invalid-state", "No surrendered certificate with that number")
        require_step_up(actor, "adjudicate-surrender", certId)
        state = "CANCELLED" if body.decision == "CANCEL" else "ISSUED"
        await session.execute(update(scheme_certificates).where(scheme_certificates.c.cert_id == certId).values(
            state=state, adjudicated_by=actor.subject, updated_at=datetime.now(UTC)))
    return envelope({"cert_id": certId, "state": state})


# ── office: the Form 10D chain ────────────────────────────────────────────────────────────────

@router.get("/api/v1/office/pension-claims")
async def claims_queue(state: str | None = Query(default=None), actor: Actor = Depends(require_stakeholder(
        "fo.da_accounts", "fo.ao", "fo.da_pension", "fo.ss_pension", "fo.apfc_pension")), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    q = select(pension_claims).where(pension_claims.c.office_id == office).order_by(pension_claims.c.created_at)
    if state:
        q = q.where(pension_claims.c.state == state)
    return envelope([_view(dict(r)) for r in (await session.execute(q)).mappings().all()])


class IdsInput(BaseModel):
    claim_id: str | None = None
    service_months: int = Field(ge=0, le=600)
    pensionable_salary_paise: int = Field(ge=0, le=100_000_000)
    note: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/office/pension-claims/{claimId}/input-data-sheets", status_code=201)
async def prepare_ids(claimId: str, body: IdsInput, actor: Actor = Depends(require_stakeholder("fo.da_accounts")),
                      session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _claim(session, claimId, actor, "SUBMITTED", "RETURNED")
        ids = {"ids_id": f"IDS-{secrets.token_hex(3).upper()}", "service_months": body.service_months,
               "pensionable_salary_paise": body.pensionable_salary_paise, "note": body.note}
        c = await _move(session, c, "IDS_PREPARED", actor, body.note, ids=ids, service_months=body.service_months,
                        pensionable_salary_paise=body.pensionable_salary_paise)
    return envelope(_view(c))


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|RETURN)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/office/pension-claims/{claimId}/input-data-sheets/{idsId}/approvals")
async def approve_ids(claimId: str, idsId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.ao")),
                      session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _claim(session, claimId, actor, "IDS_PREPARED")
        if (c["ids"] or {}).get("ids_id") != idsId:
            raise Problem(404, "/problems/not-found", "Input Data Sheet not found")
        _separate(c, actor)
        require_step_up(actor, "approve-ids", idsId)
        c = await _move(session, c, "IDS_APPROVED" if body.decision == "APPROVE" else "RETURNED", actor, body.note)
    return envelope(_view(c))


class Aggregation(BaseModel):
    claim_id: str
    source: str = Field(pattern="^(SCHEME_CERTIFICATE|UNTRANSFERRED_SERVICE)$")
    cert_id: str | None = None
    service_months: int = Field(ge=1, le=480)
    note: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/pensions/service-aggregations")
async def aggregate(body: Aggregation, actor: Actor = Depends(require_stakeholder("fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _claim(session, body.claim_id, actor, "IDS_APPROVED")
        require_step_up(actor, "aggregate-service", body.claim_id)
        if body.source == "SCHEME_CERTIFICATE":
            cert = (await session.execute(select(scheme_certificates).where(scheme_certificates.c.cert_id == (body.cert_id or "")))).mappings().first()
            if not cert or cert["state"] != "CANCELLED" or cert["uan"] != c["uan"]:
                raise Problem(422, "/problems/validation", "The scheme certificate must be this member's and surrendered and cancelled first")
            if any(a.get("cert_id") == body.cert_id for a in c["aggregated"]):
                raise Problem(409, "/problems/already-aggregated", "That certificate's service is already counted")
        item = {"source": body.source, "cert_id": body.cert_id, "service_months": body.service_months, "note": body.note}
        c = await _move(session, c, "IDS_APPROVED", actor, f"Past service added: {body.service_months} months ({body.source.lower()})",
                        aggregated=[*c["aggregated"], item])
    return envelope(_view(c))


class WorksheetInput(BaseModel):
    claim_id: str


@router.post("/api/v1/office/pensions/worksheets", status_code=201)
async def worksheet(body: WorksheetInput, actor: Actor = Depends(require_stakeholder("fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _claim(session, body.claim_id, actor, "IDS_APPROVED")
        _separate(c, actor)
        rules = await rules_on(session, c["pension_from"])            # the formula in force when the pension starts
        total = c["service_months"] + sum(a["service_months"] for a in c["aggregated"])
        r = (pension_on(c["pensionable_salary_paise"], total, age_on(c["date_of_birth"], c["pension_from"]), rules)
             if c.get("kind", "MEMBER") == "MEMBER" else family_pension_on(c["pensionable_salary_paise"], total, c["kind"], rules))
        if not r["eligible"]:
            raise Problem(422, "/problems/not-eligible", "Not eligible on these data", r["reason"])
        ws = {"worksheet_id": f"WS-{secrets.token_hex(3).upper()}", "service_months": total, "monthly_paise": r["monthly_paise"],
              "working": r["working"], "rule_version": rules["rule_version"], "age_at_start": age_on(c["date_of_birth"], c["pension_from"])}
        c = await _move(session, c, "WORKSHEET_PREPARED", actor, f"Worksheet {ws['worksheet_id']}: {r['working']}", worksheet=ws)
    return envelope(_view(c))


@router.post("/api/v1/office/pensions/worksheets/{worksheetId}/approvals")
async def approve_worksheet(worksheetId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc_pension")),
                            session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        cid = (await session.execute(select(pension_claims.c.claim_id).where(
            pension_claims.c.worksheet["worksheet_id"].as_string() == worksheetId))).scalar_one_or_none()
        if not cid:
            raise Problem(404, "/problems/not-found", "Worksheet not found")
        c = await _claim(session, cid, actor, "WORKSHEET_PREPARED")
        _separate(c, actor)
        require_step_up(actor, "approve-worksheet", worksheetId)
        c = await _move(session, c, "WORKSHEET_APPROVED" if body.decision == "APPROVE" else "IDS_APPROVED", actor, body.note)
    return envelope(_view(c))


class ClaimRef(BaseModel):
    claim_id: str


@router.post("/api/v1/office/pensions/ppo-issuances", status_code=201)
async def issue_ppo(body: ClaimRef, actor: Actor = Depends(require_stakeholder("fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _claim(session, body.claim_id, actor, "WORKSHEET_APPROVED")
        require_step_up(actor, "issue-ppo", body.claim_id)
        count = (await session.execute(select(func.count()).select_from(pensioners))).scalar_one()
        ppo_id = f"PPO-DEMO-{count + 1:04d}"
        ws = c["worksheet"]
        m = (await session.execute(select(member_service).where(member_service.c.subject == c["member_subject"]))).mappings().first()
        await session.execute(insert(pensioners).values(
            ppo_id=ppo_id, subject=c["member_subject"] if c.get("kind", "MEMBER") != "MEMBER" else None, name=c["name"], uan=c["uan"], date_of_birth=c["date_of_birth"], pension_start=c["pension_from"],
            service_months=ws["service_months"], pensionable_salary_paise=c["pensionable_salary_paise"], age_at_start=ws["age_at_start"],
            office_id=c["office_id"], bank_ifsc="DEMO0000000", bank_account_last4=(m["account_link_id"] or "0000")[-4:] if m else "0000",
            original_monthly_paise=ws["monthly_paise"], original_rule_version=ws["rule_version"], original_working=ws["working"],
            status="PENDING", status_reason="PPO issued; awaiting e-signature and dispatch"))
        c = await _move(session, c, "PPO_ISSUED", actor, f"PPO {ppo_id} generated", ppo_id=ppo_id)
    return envelope(_view(c))


class ArrearInput(BaseModel):
    action: str = Field(pattern="^(PROPOSE|CHECK)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/pensions/ppos/{ppoId}/initial-arrears")
async def initial_arrear(ppoId: str, body: ArrearInput, actor: Actor = Depends(require_stakeholder("fo.da_pension", "fo.ss_pension")),
                         session: AsyncSession = Depends(db)) -> dict:
    """The months from the start of the pension to the last completed month, at the worksheet amount:
    proposed by the DA (Pension), checked by the SS (Pension), approved by the APFC (Pension) with the e-signature."""
    async with session.begin():
        cid = (await session.execute(select(pension_claims.c.claim_id).where(pension_claims.c.ppo_id == ppoId))).scalar_one_or_none()
        if not cid:
            raise Problem(404, "/problems/not-found", "PPO not found")
        if body.action == "PROPOSE":
            if actor.stakeholder != "fo.da_pension":
                raise Problem(403, "/problems/not-your-turn", "The DA (Pension) proposes the initial arrear")
            c = await _claim(session, cid, actor, "PPO_ISSUED")
            due = months(month_of(c["pension_from"]), month_of(today()))
            arrears = {"months": due, "monthly_paise": c["worksheet"]["monthly_paise"], "amount_paise": len(due) * c["worksheet"]["monthly_paise"]}
            c = await _move(session, c, "ARREAR_PROPOSED", actor, f"Initial arrear {len(due)} months", arrears=arrears)
        else:
            if actor.stakeholder != "fo.ss_pension":
                raise Problem(403, "/problems/not-your-turn", "The SS (Pension) checks the initial arrear")
            c = await _claim(session, cid, actor, "ARREAR_PROPOSED")
            _separate(c, actor)
            c = await _move(session, c, "ARREAR_CHECKED", actor, body.note)
    return envelope(_view(c))


@router.post("/api/v1/office/pensions/ppos/{ppoId}/e-signatures")
async def esign(ppoId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc_pension")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        cid = (await session.execute(select(pension_claims.c.claim_id).where(pension_claims.c.ppo_id == ppoId))).scalar_one_or_none()
        if not cid:
            raise Problem(404, "/problems/not-found", "PPO not found")
        c = await _claim(session, cid, actor, "ARREAR_CHECKED")
        _separate(c, actor)
        require_step_up(actor, "esign-ppo", ppoId, None, c["arrears"]["amount_paise"])
        c = await _move(session, c, "PPO_SIGNED" if body.decision == "APPROVE" else "PPO_ISSUED", actor, body.note)
    return envelope(_view(c))


@router.post("/api/v1/office/pensions/ppos/{ppoId}/dispatches")
async def dispatch(ppoId: str, actor: Actor = Depends(require_stakeholder("fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        cid = (await session.execute(select(pension_claims.c.claim_id).where(pension_claims.c.ppo_id == ppoId))).scalar_one_or_none()
        if not cid:
            raise Problem(404, "/problems/not-found", "PPO not found")
        c = await _claim(session, cid, actor, "PPO_SIGNED")
        await session.execute(update(pensioners).where(pensioners.c.ppo_id == ppoId).values(status="IN_PAYMENT", status_reason=None))
        p = (await session.execute(select(pensioners).where(pensioners.c.ppo_id == ppoId))).mappings().one()
        await catch_up_payments(session, dict(p), released_on=today())       # the initial arrear is credited now
        c = await _move(session, c, "DISPATCHED", actor, f"PPO {ppoId} and scroll sent to the disbursing bank")
    return envelope(_view(c))


class TransferIn(BaseModel):
    ppo_id: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    uan: str = Field(pattern=r"^[0-9]{12}$")
    date_of_birth: date
    pension_start: date
    monthly_paise: int = Field(ge=1, le=100_000_000)
    from_office: str = Field(min_length=3, max_length=40)
    with_ppo: bool


@router.post("/api/v1/office/pensions/transfers-in", status_code=201)
async def transfer_in(body: TransferIn, actor: Actor = Depends(require_stakeholder("fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    """A pension moved here from another office: with its PPO it is paid from here at once; without, it waits
    for the PPO (status PENDING)."""
    async with session.begin():
        office = await _office(session, actor)
        if (await session.execute(select(pensioners.c.ppo_id).where(pensioners.c.ppo_id == body.ppo_id))).first():
            raise Problem(409, "/problems/duplicate", "That PPO is already with an office")
        await session.execute(insert(pensioners).values(
            ppo_id=body.ppo_id, subject=None, name=body.name.upper(), uan=body.uan, date_of_birth=body.date_of_birth,
            pension_start=body.pension_start, service_months=0, pensionable_salary_paise=0, age_at_start=age_on(body.date_of_birth, body.pension_start),
            office_id=office, bank_ifsc="DEMO0000000", bank_account_last4="0000", original_monthly_paise=body.monthly_paise,
            original_rule_version="transferred-in", original_working=f"Transferred in from {body.from_office}",
            status="IN_PAYMENT" if body.with_ppo else "PENDING", status_reason=None if body.with_ppo else "Awaiting the PPO from the transferring office"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.transfer_in",
                    target_type="pension", target_id=body.ppo_id, detail=body.from_office)
    return envelope({"ppo_id": body.ppo_id, "office_id": office, "status": "IN_PAYMENT" if body.with_ppo else "PENDING"})


# ── CPPS: monthly disbursement, the sponsor bank's paid statement, reconciliation, and the office BRS ──

CPPS = require_stakeholder("tech.cpps")


class RunInput(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def _run(r: Any) -> dict[str, Any]:
    return {"run_id": r["run_id"], "month": r["month"], "state": r["state"], "pensions": len(r["lines"]), "total_paise": r["total_paise"],
            "paid_total_paise": r["paid_total_paise"], "exceptions": r["exceptions"] or [], "lines": r["lines"]}


@router.post("/api/v1/cpps/disbursement-runs", status_code=201)
async def disbursement_run(body: RunInput, actor: Actor = Depends(CPPS), session: AsyncSession = Depends(db)) -> dict:
    if body.month >= month_of(today()):
        raise Problem(422, "/problems/validation", "Only a completed month can be disbursed")
    async with session.begin():
        require_step_up(actor, "run-disbursement", body.month)
        if (await session.execute(select(disbursement_runs.c.run_id).where(disbursement_runs.c.month == body.month))).first():
            raise Problem(409, "/problems/already-run", f"The run for {body.month} was already sent")
        for p in (await session.execute(select(pensioners).where(pensioners.c.status == "IN_PAYMENT"))).mappings().all():
            await catch_up_payments(session, dict(p))
        rows = (await session.execute(select(pension_payments.c.ppo_id, func.sum(pension_payments.c.amount_paise)).where(
            pension_payments.c.month == body.month).group_by(pension_payments.c.ppo_id))).all()
        lines = [{"ppo_id": ppo, "amount_paise": int(amount), "status": "SENT"} for ppo, amount in rows]
        run = {"run_id": f"RUN-{body.month}", "month": body.month, "state": "SENT", "lines": lines,
               "total_paise": sum(x["amount_paise"] for x in lines), "created_by": actor.subject}
        await session.execute(insert(disbursement_runs).values(**run))
    return envelope(_run({**run, "paid_total_paise": None, "exceptions": None}))


def bank_signature(run_id: str, paid_total: int) -> str:
    return hmac.new(BANK_SECRET.encode(), f"{run_id}|{paid_total}".encode(), hashlib.sha256).hexdigest()


class PaidStatement(BaseModel):
    run_id: str
    returned_ppo_ids: list[str] = Field(default_factory=list)
    paid_total_paise: int = Field(ge=0)
    signature: str = Field(min_length=64, max_length=64)


async def _record_statement(session: AsyncSession, run: dict[str, Any], returned: list[str], paid_total: int) -> dict[str, Any]:
    lines = [{**x, "status": "RETURNED" if x["ppo_id"] in returned else "PAID"} for x in run["lines"]]
    await session.execute(update(disbursement_runs).where(disbursement_runs.c.run_id == run["run_id"]).values(
        lines=lines, paid_total_paise=paid_total, state="STATEMENT_RECEIVED"))
    return {**run, "lines": lines, "paid_total_paise": paid_total, "state": "STATEMENT_RECEIVED"}


@router.post("/api/v1/integrations/mock-pension-bank/paid-statements")
async def paid_statement(body: PaidStatement, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    """Signed paid statement from the mock sponsor bank (HMAC-SHA256 of run_id|paid_total_paise)."""
    if not hmac.compare_digest(bank_signature(body.run_id, body.paid_total_paise), body.signature):
        raise Problem(401, "/problems/bad-signature", "The statement signature does not match")
    async with session.begin():
        run = (await session.execute(select(disbursement_runs).where(disbursement_runs.c.run_id == body.run_id))).mappings().first()
        if not run:
            raise Problem(404, "/problems/not-found", "Unknown run")
        run = await _record_statement(session, dict(run), body.returned_ppo_ids, body.paid_total_paise)
    return envelope(_run(run))


class RunRef(BaseModel):
    run_id: str


@router.post("/api/v1/cpps/reconciliations")
async def reconcile(body: RunRef, actor: Actor = Depends(CPPS), session: AsyncSession = Depends(db)) -> dict:
    """Match the paid statement with the run. With no statement yet, the mock sponsor bank answers at once
    (every credit paid except to accounts ending 0000)."""
    async with session.begin():
        run = (await session.execute(select(disbursement_runs).where(disbursement_runs.c.run_id == body.run_id).with_for_update())).mappings().first()
        if not run:
            raise Problem(404, "/problems/not-found", "Unknown run")
        require_step_up(actor, "reconcile-disbursement", body.run_id)
        run = dict(run)
        if run["state"] == "SENT":
            accounts = dict((await session.execute(select(pensioners.c.ppo_id, pensioners.c.bank_account_last4))).all())
            returned = [x["ppo_id"] for x in run["lines"] if accounts.get(x["ppo_id"]) == "0000"]
            run = await _record_statement(session, run, returned, sum(x["amount_paise"] for x in run["lines"] if x["ppo_id"] not in returned))
        exceptions = [{"ppo_id": x["ppo_id"], "amount_paise": x["amount_paise"], "reason": "Returned by the bank"} for x in run["lines"] if x["status"] == "RETURNED"]
        if run["paid_total_paise"] != sum(x["amount_paise"] for x in run["lines"] if x["status"] == "PAID"):
            exceptions.append({"ppo_id": None, "amount_paise": run["paid_total_paise"], "reason": "Bank total differs from the paid lines"})
        await session.execute(update(disbursement_runs).where(disbursement_runs.c.run_id == body.run_id).values(state="RECONCILED", exceptions=exceptions))
    return envelope(_run({**run, "state": "RECONCILED", "exceptions": exceptions}))


@router.post("/api/v1/office/pensions/brs-reconciliations", status_code=201)
async def brs(body: RunInput, actor: Actor = Depends(require_stakeholder("fo.apfc_pension")), session: AsyncSession = Depends(db)) -> dict:
    """Bank Reconciliation Statement for this office: the pension scroll against the bank's debits for the month."""
    async with session.begin():
        office = await _office(session, actor)
        run = (await session.execute(select(disbursement_runs).where(disbursement_runs.c.month == body.month))).mappings().first()
        if not run or run["state"] == "SENT":
            raise Problem(409, "/problems/no-statement", "No paid statement for that month yet", "CPPS reconciles the run first.")
        require_step_up(actor, "prepare-brs", body.month)
        ours = set((await session.execute(select(pensioners.c.ppo_id).where(pensioners.c.office_id == office))).scalars())
        scroll = sum(x["amount_paise"] for x in run["lines"] if x["ppo_id"] in ours)
        debited = sum(x["amount_paise"] for x in run["lines"] if x["ppo_id"] in ours and x["status"] == "PAID")
        row = {"brs_id": f"BRS-{office}-{body.month}-{secrets.token_hex(2).upper()}", "month": body.month, "office_id": office,
               "scroll_total_paise": scroll, "bank_debit_total_paise": debited, "difference_paise": scroll - debited, "prepared_by": actor.subject}
        await session.execute(insert(brs_statements).values(**row))
    return envelope({**row, "unreconciled": [x for x in run["lines"] if x["ppo_id"] in ours and x["status"] != "PAID"]})


@router.get("/api/v1/cpps/disbursement-runs")
async def runs(actor: Actor = Depends(require_stakeholder("tech.cpps", "fo.apfc_pension")), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(disbursement_runs).order_by(disbursement_runs.c.month.desc()))).mappings().all()
    return envelope([_run(r) for r in rows])
