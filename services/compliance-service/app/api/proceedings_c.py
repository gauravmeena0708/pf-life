"""P2.11c — membership disputes under Para 26B (Compliance Manual ch. 4), appeals to the Tribunal under s.7-I with the
s.7-O pre-deposit, the legal case register and the effect of court / tribunal orders (remand: heard by an officer one
level higher, para 2.9), and prosecution (ch. 5: show-cause, the RPFC's sanction, the Enforcement Officer's complaint)."""
import math
import secrets
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.proceedings import (BASE, action, allocate, case_actions, dt, establishment, event, inquiry, inquiry_view, iso,
                                 next_diary, now, record, rules, working_day_after)
from app.api.proceedings_b import withdraw_order
from app.api.routes import _office, db
from app.infra.tables import compliance_cases, compliance_officers, demands, inquiries, legal_cases, office_staff, prosecutions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope

router = APIRouter()
LEGAL = "/api/v1/office/legal"
HIGHER = {"APFC": "RPFC-II", "RPFC-II": "RPFC-I", "RPFC-I": "RPFC-I"}      # who hears a remanded case (para 2.9)


# ── 26B: whether an employee is a member, and from when ───────────────────────────────────────────────────────────────
class DisputedEmployee(BaseModel):
    name: str = Field(min_length=1)
    uan: str | None = None
    claimed_from: date


class DisputeInput(BaseModel):
    establishment_id: str
    trigger: Literal["EMPLOYEE_COMPLAINT", "INSPECTOR_OBSERVATION", "DURING_7A", "UNION_COMPLAINT"]
    employees: list[DisputedEmployee] = Field(min_length=1)
    contributory_uans: int = Field(ge=0)
    related_case_id: str | None = None
    note: str = Field(min_length=10)


@router.post(BASE + "/membership-disputes", status_code=201)
async def membership_dispute(body: DisputeInput, actor: Actor = Depends(require_stakeholder("fo.ss")), session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        await establishment(session, body.establishment_id, office)
        require_step_up(actor, "register-26b", body.establishment_id)
        # Para 26B proceedings are held by an RPFC-II or RPFC-I (para 2.3.1, note **): never below RPFC-II whatever the size
        rank, officer = await allocate(session, office, max(body.contributory_uans, 251))
        start = min(e.claimed_from for e in body.employees)
        case_id, at = f"CMP-{secrets.token_hex(5).upper()}", now()
        row = dict(case_id=case_id, diary_no=await next_diary(session, office), office_id=office, establishment_id=body.establishment_id,
                   dispute="MEMBERSHIP", period_from=start.strftime("%Y-%m"), period_to=at.strftime("%Y-%m"), inspection_id=None,
                   contributory_uans=body.contributory_uans, officer_rank=rank, officer_subject=officer, registered_at=at,
                   registration_due_at=None, concluded_on=None, order_due_at=None, state="REGISTERED", section="26B",
                   parent_case_id=body.related_case_id)
        await session.execute(insert(inquiries).values(**row))
        await session.execute(insert(compliance_cases).values(case_id=case_id, establishment_id=body.establishment_id, office_id=office,
            kind="INQUIRY_26B", wage_months=[], amount_paise=0, state="OPEN",
            history=[{"at": at.isoformat(), "by_role": actor.stakeholder, "action": "REGISTERED_26B", "note": body.note}],
            opened_by=actor.subject, created_at=at))
        await action(session, case_id, "DISPUTE", actor.subject, body.model_dump(mode="json"))
        await event(session, actor, "InquiryRegistered.v1", "compliance_case", case_id,
                    {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": body.establishment_id, "section": "26B",
                     "officer_rank": rank, "contributory_uans": body.contributory_uans})
        await record(session, actor, "inquiry.membership_dispute", "inquiry", case_id, body.note)
    return envelope(inquiry_view(row))


# ── appeals under s.7-I, the s.7-O pre-deposit ────────────────────────────────────────────────────────────────────────
def legal_view(row: dict) -> dict:
    view = {**row, "created_at": iso(row["created_at"])}
    if row["kind"] == "APPEAL_7I":
        required = math.ceil(int(row["amount_paise"] or 0) * int(row["pre_deposit_percent"] or 0) / 100)
        deposited = sum(int(d["amount_paise"]) for d in row["pre_deposits"] or [])
        view.update(pre_deposit_required_paise=required, pre_deposited_paise=deposited, heard=deposited >= required)
    return view


async def legal_case(session: AsyncSession, legal_case_id: str, office: str) -> dict:
    row = (await session.execute(select(legal_cases).where(legal_cases.c.legal_case_id == legal_case_id))).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Legal case not found")
    return dict(row)


class AppealInput(BaseModel):
    forum: str = Field(default="CGIT-cum-Labour Court (EPF Appellate Tribunal)", min_length=3)
    case_no: str = Field(min_length=1)
    filed_on: date
    delay_condonation: bool = False
    note: str | None = None


@router.post(BASE + "/cases/{case_id}/appeals", status_code=201)
async def appeal(case_id: str, body: AppealInput, actor: Actor = Depends(require_stakeholder("fo.legal")), session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        row = await inquiry(session, case_id, office)
        if row["state"] not in ("ORDERED", "PART_ORDERED") or (row.get("section") or "7A") == "26B":
            raise Problem(409, "/problems/invalid-state", "An appeal under s.7-I lies against a passed 7A, 7B, 7C or 14B order")
        if (await session.execute(select(legal_cases.c.legal_case_id).where(legal_cases.c.inquiry_case_id == case_id,
                                                                            legal_cases.c.kind == "APPEAL_7I"))).first():
            raise Problem(409, "/problems/already-appealed", "An appeal against this order is already on the register")
        _, limits = await rules(session)
        ordered = dt(row["ordered_at"]).date()
        if body.filed_on > now().date() or body.filed_on < ordered:
            raise Problem(422, "/problems/validation", "Filed between the order and today")
        late = body.filed_on > ordered + timedelta(days=limits["appeal_days"])
        if late and (not body.delay_condonation or body.filed_on > ordered + timedelta(days=limits["appeal_days"] + limits["appeal_condonable_days"])):
            raise Problem(422, "/problems/out-of-time", f"Within {limits['appeal_days']} days of the order, or "
                          f"{limits['appeal_condonable_days']} more with the delay condoned")
        orders = [a for a in await case_actions(session, case_id) if a["kind"] == "ORDER" and not a["detail"].get("superseded")]
        appealable = [a for a in orders if a["detail"]["kind"] != "7Q"]            # interest under 7Q is not among the s.7-I orders
        impugned = [a["detail"]["demand_id"] for a in appealable]
        amount = sum(int(a["detail"]["total_paise"]) for a in appealable)
        legal_id, at = f"LC-{secrets.token_hex(4).upper()}", now()
        new = dict(legal_case_id=legal_id, office_id=office, establishment_id=row["establishment_id"], kind="APPEAL_7I", forum=body.forum,
                   case_no=body.case_no, filed_on=body.filed_on.isoformat(), inquiry_case_id=case_id, impugned_demand_ids=impugned,
                   amount_paise=amount, pre_deposit_percent=limits["pre_deposit_percent"], pre_deposits=[], delay_condonation=late,
                   stayed=False, state="PENDING", orders=[], note=body.note, created_by=actor.subject, created_at=at)
        await session.execute(insert(legal_cases).values(**new))
        await action(session, case_id, "APPEAL", actor.subject, {"legal_case_id": legal_id, "case_no": body.case_no, "filed_on": new["filed_on"]})
        await event(session, actor, "LegalCaseRegistered.v1", "legal_case", legal_id,
                    {"legal_case_id": legal_id, "kind": "APPEAL_7I", "establishment_id": row["establishment_id"], "inquiry_case_id": case_id})
        await record(session, actor, "legal.appeal_registered", "legal_case", legal_id, body.case_no)
    return envelope(legal_view(new))


class PreDepositInput(BaseModel):
    amount_paise: int = Field(gt=0)
    reference: str = Field(min_length=4)          # the challan (TRRN) or the Tribunal's receipt
    deposited_on: date


@router.post(BASE + "/cases/{case_id}/appeals/{appeal_id}/pre-deposits", status_code=201)
async def pre_deposit(case_id: str, appeal_id: str, body: PreDepositInput, actor: Actor = Depends(require_stakeholder("fo.legal")),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await legal_case(session, appeal_id, await _office(session, actor))
        if row["kind"] != "APPEAL_7I" or row["inquiry_case_id"] != case_id:
            raise Problem(404, "/problems/not-found", "No such appeal on this case")
        deposits = list(row["pre_deposits"] or [])
        if any(d["reference"] == body.reference for d in deposits):           # recorded once, whatever the retry
            return envelope(legal_view(row))
        deposits.append({**body.model_dump(mode="json"), "recorded_by": actor.subject, "idempotency_key": idempotency_key})
        await session.execute(update(legal_cases).where(legal_cases.c.legal_case_id == appeal_id).values(pre_deposits=deposits))
        await record(session, actor, "legal.pre_deposit", "legal_case", appeal_id, f"{body.amount_paise} {body.reference}")
    return envelope(legal_view({**row, "pre_deposits": deposits}))


class WaiverInput(BaseModel):
    percent: int = Field(ge=0, le=100)
    tribunal_order_ref: str = Field(min_length=3)
    order_date: date


@router.post(BASE + "/cases/{case_id}/appeals/{appeal_id}/pre-deposit-waivers")
async def pre_deposit_waiver(case_id: str, appeal_id: str, body: WaiverInput, actor: Actor = Depends(require_stakeholder("fo.legal")),
                             session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await legal_case(session, appeal_id, await _office(session, actor))
        require_step_up(actor, "record-pre-deposit-waiver", appeal_id)
        if row["kind"] != "APPEAL_7I" or row["inquiry_case_id"] != case_id:
            raise Problem(404, "/problems/not-found", "No such appeal on this case")
        if body.percent > int(row["pre_deposit_percent"]):
            raise Problem(422, "/problems/validation", "The Tribunal may reduce or waive the pre-deposit, not raise it")
        orders = [*row["orders"], {"order_date": body.order_date.isoformat(), "outcome": "PRE_DEPOSIT_REDUCED", "percent": body.percent,
                                   "reference": body.tribunal_order_ref, "recorded_by": actor.subject}]
        await session.execute(update(legal_cases).where(legal_cases.c.legal_case_id == appeal_id).values(pre_deposit_percent=body.percent, orders=orders))
        await record(session, actor, "legal.pre_deposit_waiver", "legal_case", appeal_id, f"{body.percent}% {body.tribunal_order_ref}")
    return envelope(legal_view({**row, "pre_deposit_percent": body.percent, "orders": orders}))


# ── the legal case register and the effect of orders ──────────────────────────────────────────────────────────────────
class LegalCaseInput(BaseModel):
    establishment_id: str
    kind: Literal["WRIT", "NCLT", "OTHER"]
    forum: str = Field(min_length=3)
    case_no: str = Field(min_length=1)
    filed_on: date
    inquiry_case_id: str | None = None
    note: str | None = None


@router.post(LEGAL + "/cases", status_code=201)
async def register_legal(body: LegalCaseInput, actor: Actor = Depends(require_stakeholder("fo.legal")), session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        await establishment(session, body.establishment_id, office)
        linked = await inquiry(session, body.inquiry_case_id, office) if body.inquiry_case_id else None
        legal_id = f"LC-{secrets.token_hex(4).upper()}"
        new = dict(legal_case_id=legal_id, office_id=office, establishment_id=body.establishment_id, kind=body.kind, forum=body.forum,
                   case_no=body.case_no, filed_on=body.filed_on.isoformat(), inquiry_case_id=body.inquiry_case_id,
                   impugned_demand_ids=[a["detail"]["demand_id"] for a in await case_actions(session, linked["case_id"])
                                        if a["kind"] == "ORDER" and not a["detail"].get("superseded")] if linked else [],
                   amount_paise=None, pre_deposit_percent=None, pre_deposits=None, delay_condonation=None, stayed=False, state="PENDING",
                   orders=[], note=body.note, created_by=actor.subject, created_at=now())
        await session.execute(insert(legal_cases).values(**new))
        await event(session, actor, "LegalCaseRegistered.v1", "legal_case", legal_id,
                    {"legal_case_id": legal_id, "kind": body.kind, "establishment_id": body.establishment_id, "inquiry_case_id": body.inquiry_case_id or ""})
        await record(session, actor, "legal.case_registered", "legal_case", legal_id, body.case_no)
    return envelope(legal_view(new))


@router.get(LEGAL + "/cases")
async def legal_register(state: str | None = Query(None), kind: str | None = Query(None),
                         actor: Actor = Depends(require_stakeholder("fo.legal", "fo.oic", "fo.apfc")), session: AsyncSession = Depends(db)):
    query = select(legal_cases).where(legal_cases.c.office_id == await _office(session, actor)).order_by(legal_cases.c.created_at.desc())
    if state:
        query = query.where(legal_cases.c.state == state)
    if kind:
        query = query.where(legal_cases.c.kind == kind)
    return envelope([legal_view(dict(r)) for r in (await session.execute(query)).mappings().all()])


class CourtOrderInput(BaseModel):
    order_date: date
    outcome: Literal["INTERIM_STAY", "STAY_VACATED", "DISMISSED", "ALLOWED", "PARTLY_ALLOWED", "REMANDED", "CONVICTED", "ACQUITTED", "OTHER"]
    note: str = Field(min_length=1)
    revised_amount_paise: int | None = Field(default=None, ge=0)


@router.post(LEGAL + "/cases/{legal_case_id}/orders")
async def court_order(legal_case_id: str, body: CourtOrderInput, actor: Actor = Depends(require_stakeholder("fo.legal")),
                      session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        row = await legal_case(session, legal_case_id, office)
        if row["state"] == "DECIDED":
            raise Problem(409, "/problems/decided", "The case is decided; register a further appeal or writ as a new case")
        if row["kind"] == "APPEAL_7I" and body.outcome in ("DISMISSED", "ALLOWED", "PARTLY_ALLOWED", "REMANDED") and not legal_view(row)["heard"]:
            raise Problem(422, "/problems/pre-deposit", "The Tribunal hears the appeal after the s.7-O pre-deposit (or its waiver)")
        if (body.outcome in ("CONVICTED", "ACQUITTED")) != (row["kind"] == "PROSECUTION"):
            raise Problem(422, "/problems/validation", "Conviction and acquittal are outcomes of a prosecution")
        values: dict = {"orders": [*row["orders"], {**body.model_dump(mode="json"), "recorded_by": actor.subject}]}
        if body.outcome == "INTERIM_STAY":
            values["stayed"] = True
        elif body.outcome == "STAY_VACATED":
            values["stayed"] = False
        elif body.outcome != "OTHER":
            values.update(state="DECIDED", stayed=False)
        effect = ""
        target = await inquiry(session, row["inquiry_case_id"], office) if row["inquiry_case_id"] else None
        if target and body.outcome in ("ALLOWED", "REMANDED", "PARTLY_ALLOWED"):
            document, _ = await rules(session)
            impugned = [d for d in row["impugned_demand_ids"] or []]
            if body.outcome == "PARTLY_ALLOWED":
                if body.revised_amount_paise is None:
                    raise Problem(422, "/problems/validation", "Give the amount the order leaves payable")
                kinds = (await session.execute(select(demands.c.kind).where(demands.c.demand_id.in_(impugned)))).scalars().all()
                demand_id = f"DT-{target['case_id']}-{secrets.token_hex(2)}"
                await event(session, actor, "DemandRaised.v1", "demand", demand_id,
                            {"demand_id": demand_id, "establishment_id": target["establishment_id"],
                             "demand_type": kinds[0] if kinds else "DUES_7A", "amount_paise": body.revised_amount_paise,
                             "supersedes_demand_ids": impugned, "working": f"As revised by {row['forum']} in {row['case_no']}",
                             "rule_version": document["rule_version"]})
                effect = "demand revised"
            else:                                       # allowed: the order goes; remanded: heard again one level higher
                await withdraw_order(session, actor, target, f"{body.outcome.title()} by {row['forum']} in {row['case_no']}")
                await session.execute(update(inquiries).where(inquiries.c.case_id == target["case_id"]).values(
                    state="CLOSED_ON_APPEAL" if body.outcome == "ALLOWED" else "REGISTERED", order_demand_ids=[], concluded_on=None,
                    order_due_at=None))
                effect = "order set aside"
                if body.outcome == "REMANDED":
                    rank = HIGHER.get(target["officer_rank"], "RPFC-I")
                    officers = (await session.execute(select(compliance_officers.c.subject).where(compliance_officers.c.office_id == office,
                                compliance_officers.c.rank == rank, compliance_officers.c.barred.is_(False)))).scalars().all()
                    officer = secrets.choice(officers) if officers else (await session.execute(select(office_staff.c.subject).where(
                        office_staff.c.office_id == office, office_staff.c.stakeholder == "fo.oic"))).scalar_one()
                    await session.execute(update(inquiries).where(inquiries.c.case_id == target["case_id"]).values(officer_rank=rank, officer_subject=officer))
                    await action(session, target["case_id"], "REMANDED", actor.subject, {"legal_case_id": legal_case_id, "to_rank": rank, "note": body.note})
                    effect = f"remanded to the {rank}"
        await session.execute(update(legal_cases).where(legal_cases.c.legal_case_id == legal_case_id).values(**values))
        if row["kind"] == "PROSECUTION" and body.outcome in ("CONVICTED", "ACQUITTED"):
            await session.execute(update(prosecutions).where(prosecutions.c.legal_case_id == legal_case_id).values(state=body.outcome))
        await event(session, actor, "LegalOrderRecorded.v1", "legal_case", legal_case_id,
                    {"legal_case_id": legal_case_id, "kind": row["kind"], "outcome": body.outcome, "inquiry_case_id": row["inquiry_case_id"] or ""})
        await record(session, actor, "legal.order_recorded", "legal_case", legal_case_id, f"{body.outcome} {effect}".strip())
    return envelope({**legal_view({**row, **values}), "effect": effect})


# ── prosecution: show-cause, reply, the RPFC's sanction, the Enforcement Officer's complaint ───────────────────────────
class ProsecutionInput(BaseModel):
    offence: Literal["NON_PAYMENT", "NON_FILING_RETURNS", "OTHER"]
    particulars: str = Field(min_length=10)


def prosecution_view(row: dict) -> dict:
    return {**row, "scn_at": iso(row["scn_at"]), "reply_due": iso(row["reply_due"]),
            "reply_overdue": row["state"] == "SCN_ISSUED" and now() > dt(row["reply_due"])}


@router.post(BASE + "/cases/{case_id}/prosecutions", status_code=201)
async def prosecute(case_id: str, body: ProsecutionInput, actor: Actor = Depends(require_stakeholder("fo.apfc")), session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        case = (await session.execute(select(compliance_cases).where(compliance_cases.c.case_id == case_id))).mappings().first()
        if not case or case["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Case not found")
        require_step_up(actor, "issue-prosecution-scn", case_id)
        if body.offence == "NON_PAYMENT":
            # dues are assessed under 7A first; prosecution only once the time allowed to pay has run out (para 5.2.2 iii)
            row = (await session.execute(select(inquiries).where(inquiries.c.case_id == case_id))).mappings().first()
            unpaid = (await session.execute(select(demands.c.demand_id).where(demands.c.demand_id.in_((row or {}).get("order_demand_ids") or ["-"]),
                                                                               demands.c.state == "OPEN"))).first() if row else None
            if not row or row["state"] != "ORDERED" or not unpaid or now() <= dt(row["ordered_at"]) + timedelta(days=15):
                raise Problem(422, "/problems/assess-first", "For non-payment, assess the dues under 7A first; prosecute only if they stay unpaid "
                              "after the 15 days the order allows (Compliance Manual 5.2.2 iii)")
        _, limits = await rules(session)
        at = now()
        new = dict(prosecution_id=f"PRS-{secrets.token_hex(4).upper()}", office_id=office, establishment_id=case["establishment_id"],
                   inquiry_case_id=case_id, offence=body.offence, particulars=body.particulars, state="SCN_ISSUED", scn_at=at,
                   reply_due=working_day_after(at, limits["scn_reply_working_days"]), legal_case_id=None, created_by=actor.subject,
                   history=[{"step": "SCN_ISSUED", "by": actor.stakeholder, "at": at.isoformat(), "note": body.particulars}])
        await session.execute(insert(prosecutions).values(**new))
        await event(session, actor, "ProsecutionStepTaken.v1", "prosecution", new["prosecution_id"],
                    {"prosecution_id": new["prosecution_id"], "establishment_id": new["establishment_id"], "step": "SCN_ISSUED", "state": "SCN_ISSUED"})
        await record(session, actor, "prosecution.scn", "prosecution", new["prosecution_id"], body.offence)
    return envelope(prosecution_view(new))


@router.get(BASE + "/prosecutions")
async def list_prosecutions(actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "fo.eo", "fo.legal")), session: AsyncSession = Depends(db)):
    rows = (await session.execute(select(prosecutions).where(prosecutions.c.office_id == await _office(session, actor))
                                  .order_by(prosecutions.c.scn_at.desc()))).mappings().all()
    return envelope([prosecution_view(dict(r)) for r in rows])


class ProsecutionStep(BaseModel):
    step: Literal["SANCTION", "COMPLAINT", "DROP"]
    note: str = Field(min_length=1)
    court: str | None = None
    complaint_no: str | None = None


@router.post(BASE + "/prosecutions/{prosecution_id}/steps")
async def prosecution_step(prosecution_id: str, body: ProsecutionStep, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "fo.eo")),
                           session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        row = (await session.execute(select(prosecutions).where(prosecutions.c.prosecution_id == prosecution_id))).mappings().first()
        if not row or row["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Prosecution not found")
        row = dict(row)
        role = {"SANCTION": "fo.oic", "COMPLAINT": "fo.eo", "DROP": "fo.apfc"}[body.step]
        if actor.stakeholder != role:
            raise Problem(403, "/problems/role", {"SANCTION": "The RPFC sanctions the prosecution", "COMPLAINT": "Only an Inspector (the Enforcement "
                          "Officer) may file the complaint (s.14AC)", "DROP": "The circle officer drops it when the default is set right"}[body.step])
        _, limits = await rules(session)
        at, values, late = now(), {}, False
        if body.step == "SANCTION":
            if row["state"] not in ("REPLIED",) and not (row["state"] == "SCN_ISSUED" and at > dt(row["reply_due"])):
                raise Problem(409, "/problems/invalid-state", "Sanction after the reply, or once the time to reply has run out")
            values["state"] = "SANCTIONED"
        elif body.step == "COMPLAINT":
            if row["state"] != "SANCTIONED" or not body.court or not body.complaint_no:
                raise Problem(422, "/problems/validation", "After the sanction: give the court and the complaint number")
            sanctioned = dt(next(h["at"] for h in reversed(row["history"]) if h["step"] == "SANCTION"))
            late = at > sanctioned + timedelta(days=limits["complaint_days"])
            legal_id = f"LC-{secrets.token_hex(4).upper()}"
            await session.execute(insert(legal_cases).values(legal_case_id=legal_id, office_id=office, establishment_id=row["establishment_id"],
                kind="PROSECUTION", forum=body.court, case_no=body.complaint_no, filed_on=at.date().isoformat(), inquiry_case_id=None,
                impugned_demand_ids=[], amount_paise=None, pre_deposit_percent=None, pre_deposits=None, delay_condonation=None, stayed=False,
                state="PENDING", orders=[], note=row["particulars"], created_by=actor.subject, created_at=at))
            values.update(state="COMPLAINT_FILED", legal_case_id=legal_id)
        else:
            if row["state"] in ("COMPLAINT_FILED", "CONVICTED", "ACQUITTED", "DROPPED"):
                raise Problem(409, "/problems/invalid-state", "Too late to drop: the complaint is in court")
            values["state"] = "DROPPED"
        values["history"] = [*row["history"], {"step": body.step, "by": actor.stakeholder, "at": at.isoformat(), "note": body.note, "late": late,
                                               **({"court": body.court, "complaint_no": body.complaint_no} if body.step == "COMPLAINT" else {})}]
        await session.execute(update(prosecutions).where(prosecutions.c.prosecution_id == prosecution_id).values(**values))
        await event(session, actor, "ProsecutionStepTaken.v1", "prosecution", prosecution_id,
                    {"prosecution_id": prosecution_id, "establishment_id": row["establishment_id"], "step": body.step, "state": values["state"]})
        await record(session, actor, "prosecution." + body.step.lower(), "prosecution", prosecution_id, body.note)
    return envelope(prosecution_view({**row, **values}))


class ScnReply(BaseModel):
    text: str = Field(min_length=10)
    documents: list[str] = Field(default_factory=list)


@router.get("/api/v1/employers/me/prosecutions")
async def my_prosecutions(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")), session: AsyncSession = Depends(db)):
    rows = (await session.execute(select(prosecutions).where(prosecutions.c.establishment_id == (actor.establishment_id or ""))
                                  .order_by(prosecutions.c.scn_at.desc()))).mappings().all()
    return envelope([{k: v for k, v in prosecution_view(dict(r)).items() if k not in ("created_by",)} for r in rows])


@router.post("/api/v1/employers/me/prosecutions/{prosecution_id}/replies")
async def reply_scn(prosecution_id: str, body: ScnReply, actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")),
                    session: AsyncSession = Depends(db)):
    async with session.begin():
        row = (await session.execute(select(prosecutions).where(prosecutions.c.prosecution_id == prosecution_id))).mappings().first()
        if not row or row["establishment_id"] != actor.establishment_id:
            raise Problem(404, "/problems/not-found", "Show-cause notice not found")
        if row["state"] != "SCN_ISSUED":
            raise Problem(409, "/problems/invalid-state", "The notice is no longer open for a reply")
        history = [*row["history"], {"step": "REPLY", "by": actor.stakeholder, "at": now().isoformat(), "note": body.text, "documents": body.documents,
                                     "late": now() > dt(row["reply_due"])}]
        await session.execute(update(prosecutions).where(prosecutions.c.prosecution_id == prosecution_id).values(state="REPLIED", history=history))
        await record(session, actor, "prosecution.reply", "prosecution", prosecution_id, body.text[:80])
    return envelope(prosecution_view({**dict(row), "state": "REPLIED", "history": history}))
