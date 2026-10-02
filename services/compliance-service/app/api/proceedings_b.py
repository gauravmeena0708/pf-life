"""P2.11b — after and beside the 7A inquiry (EPFO Compliance Manual, 05/02/2024): the 14B damages / 7Q interest proceeding
from the auto-calculated demands (3.2–3.3), review under 7B (2.7), escaped amounts under 7C (2.8), setting aside an
ex-parte order (2.6.5) and the administrative scrutiny of orders (2.11)."""
import secrets
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.proceedings import (BASE, action, allocate, assigned, case_actions, dt, establishment, event, inquiry, inquiry_view,
                                 iso, next_diary, now, record, rules)
from app.api.routes import _office, db
from app.infra.tables import compliance_cases, compliance_officers, demands, inquiries, inquiry_actions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope

router = APIRouter()
NEXT_HIGHER = {"APFC": "RPFC-II", "RPFC-II": "RPFC-I", "RPFC-I": "ZONAL_ACC"}       # who gives the view / scrutinises (2.7.1, 2.11.1)


def month_end_plus(day: date, months: int) -> date:
    y, m = divmod(day.month - 1 + months, 12)
    return date(day.year + y, m + 1, 1)


# ── 14B / 7Q: the notice from the auto-calculated demands, through DA (T+1), SS (T+3), circle officer (T+5) ─────────────
async def register_14b(establishment_id: str, demand_ids: list[str], contributory_uans: int, note: str, actor: Actor,
                       session: AsyncSession) -> dict:
    office = await _office(session, actor)
    await establishment(session, establishment_id, office)
    taken = {i for (ids,) in (await session.execute(select(inquiries.c.demand_ids).where(
        inquiries.c.section == "14B", inquiries.c.state.notin_(["ORDERED"])))).all() for i in (ids or [])}
    if not demand_ids:                         # the desk review's report: every open auto-calculated demand not yet noticed (3.2.6)
        demand_ids = [d for (d,) in (await session.execute(select(demands.c.demand_id).where(
            demands.c.establishment_id == establishment_id, demands.c.state == "OPEN",
            demands.c.kind.in_(["DAMAGES_14B", "INTEREST_7Q"])))).all() if d not in taken]
    rows = (await session.execute(select(demands).where(demands.c.demand_id.in_(demand_ids)))).mappings().all()
    if not demand_ids or len(rows) != len(set(demand_ids)) or any(
            d["establishment_id"] != establishment_id or d["state"] != "OPEN" or d["kind"] not in ("DAMAGES_14B", "INTEREST_7Q") for d in rows):
        raise Problem(422, "/problems/validation", "The notice covers the establishment's open, auto-calculated 14B / 7Q demands")
    if taken & set(demand_ids):
        raise Problem(409, "/problems/already-noticed", "A 14B proceeding already covers some of these demands")
    _, limits = await rules(session)
    months = sorted(d["wage_month"] for d in rows)
    case_id, at = f"CMP-{secrets.token_hex(5).upper()}", now()
    row = dict(case_id=case_id, diary_no=f"DRAFT/{case_id}", office_id=office, establishment_id=establishment_id, dispute="DAMAGES",
               period_from=months[0], period_to=months[-1], inspection_id=None, contributory_uans=contributory_uans, officer_rank="",
               officer_subject="", registered_at=at, registration_due_at=at + timedelta(days=limits["damages_ss_days"]),
               concluded_on=None, order_due_at=None, state="NOTICE_DRAFTED", section="14B", demand_ids=sorted(set(demand_ids)))
    await session.execute(insert(inquiries).values(**row))
    await session.execute(insert(compliance_cases).values(case_id=case_id, establishment_id=establishment_id, office_id=office,
        kind="INQUIRY_14B", wage_months=months, amount_paise=sum(int(d["amount_paise"]) for d in rows), state="OPEN",
        history=[{"at": at.isoformat(), "by_role": actor.stakeholder, "action": "NOTICE_DRAFTED", "note": note}],
        opened_by=actor.subject, created_at=at))
    await action(session, case_id, "NOTICE_DRAFT", actor.subject, {"note": note, "demands": [
        {"demand_id": d["demand_id"], "kind": d["kind"], "wage_month": d["wage_month"], "days_late": int(d["days_late"]),
         "amount_paise": int(d["amount_paise"])} for d in rows]})
    await record(session, actor, "inquiry.damages_notice_drafted", "inquiry", case_id, note)
    return inquiry_view(row)


class ApprovalInput(BaseModel):
    note: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/approvals")
async def approve_notice(case_id: str, body: ApprovalInput, actor: Actor = Depends(require_stakeholder("fo.ss", "fo.apfc")),
                         session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await inquiry(session, case_id, await _office(session, actor))
        expected = {"fo.ss": "NOTICE_DRAFTED", "fo.apfc": "SS_ENDORSED"}[actor.stakeholder]
        if row.get("section") != "14B" or row["state"] != expected:
            raise Problem(409, "/problems/invalid-state", f"Expected a 14B notice at {expected}")
        _, limits = await rules(session)
        at = now()
        if actor.stakeholder == "fo.ss":
            values = {"state": "SS_ENDORSED", "registration_due_at": at + timedelta(days=limits["damages_approval_days"] - limits["damages_ss_days"])}
        else:                                   # the circle officer approves: filed on e-Proceedings, diary number, allotted by size
            rank, officer = await allocate(session, row["office_id"], int(row["contributory_uans"]))
            values = {"state": "REGISTERED", "diary_no": await next_diary(session, row["office_id"]), "officer_rank": rank, "officer_subject": officer}
        late = at > dt(row["registration_due_at"])
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(**values))
        await action(session, case_id, "APPROVAL", actor.subject, {"by": actor.stakeholder, "note": body.note, "late": late})
        if values["state"] == "REGISTERED":
            await event(session, actor, "InquiryRegistered.v1", "compliance_case", case_id,
                        {"case_id": case_id, "diary_no": values["diary_no"], "establishment_id": row["establishment_id"], "section": "14B",
                         "officer_rank": values["officer_rank"], "contributory_uans": int(row["contributory_uans"])})
        await record(session, actor, "inquiry.damages_notice_" + ("endorsed" if actor.stakeholder == "fo.ss" else "approved"), "inquiry", case_id, body.note)
    return envelope(inquiry_view({**row, **values}))


# ── the employer's applications: review under 7B, setting aside an ex-parte order ──────────────────────────────────────
class ApplicationInput(BaseModel):
    kind: Literal["REVIEW_7B", "SET_ASIDE"]
    grounds: Literal["NEW_EVIDENCE", "ERROR_APPARENT", "OTHER_SUFFICIENT", "NOT_SERVED", "SUFFICIENT_CAUSE"]
    text: str = Field(min_length=1)
    documents: list[str] = Field(default_factory=list)


async def open_application(session: AsyncSession, case_id: str) -> dict | None:
    for a in reversed(await case_actions(session, case_id)):
        if a["kind"] == "APPLICATION" and a["detail"]["status"] == "PENDING":
            return a
    return None


@router.post("/api/v1/employers/me/proceedings/{case_id}/applications", status_code=201)
async def apply(case_id: str, body: ApplicationInput, actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")),
                session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await inquiry(session, case_id)
        if row["establishment_id"] != actor.establishment_id:
            raise Problem(404, "/problems/not-found", "Inquiry not found")
        if row["state"] != "ORDERED" or (row.get("section") or "7A") == "14B" and body.kind == "REVIEW_7B":
            raise Problem(409, "/problems/invalid-state", "An application lies against a passed order (review: a 7A / 7C order)")
        from app.infra.tables import legal_cases
        if body.kind == "REVIEW_7B" and (await session.execute(select(legal_cases.c.legal_case_id).where(
                legal_cases.c.inquiry_case_id == case_id, legal_cases.c.kind == "APPEAL_7I"))).first():
            raise Problem(409, "/problems/appealed", "No review once an appeal has been preferred against the order (s.7B(1))")
        if await open_application(session, case_id):
            raise Problem(409, "/problems/application-pending", "An application is already pending")
        _, limits = await rules(session)
        ordered = dt(row["ordered_at"]).date()
        if body.kind == "REVIEW_7B":
            if body.grounds not in ("NEW_EVIDENCE", "ERROR_APPARENT", "OTHER_SUFFICIENT"):
                raise Problem(422, "/problems/validation", "Review lies for new evidence, an error apparent on the record or another sufficient reason (s.7B(1))")
            if now().date() > ordered + timedelta(days=limits["review_days"]):
                raise Problem(422, "/problems/out-of-time", f"A review is applied for within {limits['review_days']} days of the order")
        else:
            if not row.get("ex_parte"):
                raise Problem(422, "/problems/validation", "Only an ex-parte order can be set aside on the employer's application (s.7A(4))")
            if body.grounds not in ("NOT_SERVED", "SUFFICIENT_CAUSE"):
                raise Problem(422, "/problems/validation", "Set aside for a notice not duly served or a sufficient cause for absence (para 2.6.5)")
            if now().date() > month_end_plus(ordered, limits["set_aside_months"]) + timedelta(days=ordered.day - 1):
                raise Problem(422, "/problems/out-of-time", f"Within {limits['set_aside_months']} months of the order")
        detail = {"application_id": f"APP-{secrets.token_hex(4).upper()}", **body.model_dump(), "status": "PENDING"}
        await action(session, case_id, "APPLICATION", actor.subject, detail)
        await record(session, actor, "inquiry.application", "inquiry", case_id, body.kind)
    return envelope(detail)


async def close_application(session: AsyncSession, case_id: str, application_id: str, status: str) -> None:
    rows = (await session.execute(select(inquiry_actions).where(inquiry_actions.c.case_id == case_id,
                                                               inquiry_actions.c.kind == "APPLICATION"))).mappings().all()
    for r in rows:
        if r["detail"].get("application_id") == application_id:
            await session.execute(update(inquiry_actions).where(inquiry_actions.c.action_id == r["action_id"]).values(
                detail={**r["detail"], "status": status}))


async def withdraw_order(session: AsyncSession, actor: Actor, row: dict, reason: str) -> None:
    """The order goes (set aside, or reopened on review before a fresh order): its demand is withdrawn, the case is heard again."""
    document, _ = await rules(session)
    for a in await case_actions(session, row["case_id"]):
        if a["kind"] == "ORDER" and not a["detail"].get("superseded"):
            rows = (await session.execute(select(inquiry_actions).where(inquiry_actions.c.case_id == row["case_id"],
                                                                       inquiry_actions.c.kind == "ORDER"))).mappings().all()
            for r in rows:
                await session.execute(update(inquiry_actions).where(inquiry_actions.c.action_id == r["action_id"]).values(
                    detail={**r["detail"], "superseded": True}))
    withdrawn = list(row.get("order_demand_ids") or [])
    if withdrawn:
        marker = f"W-{row['case_id']}-{secrets.token_hex(2)}"
        await event(session, actor, "DemandRaised.v1", "demand", marker,
                    {"demand_id": marker, "establishment_id": row["establishment_id"],
                     "demand_type": "DUES_7A", "amount_paise": 0, "supersedes_demand_ids": withdrawn, "working": reason,   # 0: withdrawn
                     "rule_version": document["rule_version"]})


class ReviewInput(BaseModel):
    application_id: str | None = None                 # none: the officer's own motion (proviso to s.7B(1))
    view_by_rank: Literal["RPFC-II", "RPFC-I", "ZONAL_ACC"]
    view_note: str = Field(min_length=1)
    decision: Literal["GRANTED", "REJECTED"]
    note: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/reviews-7b")
async def review(case_id: str, body: ReviewInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                 session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await assigned(session, case_id, actor)
        require_step_up(actor, "review-order", case_id)
        if row["state"] != "ORDERED" or (row.get("section") or "7A") == "14B":
            raise Problem(409, "/problems/invalid-state", "Review lies against a passed 7A / 7C order")
        if body.view_by_rank != NEXT_HIGHER.get(row["officer_rank"]):
            raise Problem(422, "/problems/next-higher-view", f"Obtain the view of the {NEXT_HIGHER.get(row['officer_rank'])} first (para 2.7.1)")
        pending = await open_application(session, case_id)
        if body.application_id and (not pending or pending["detail"]["application_id"] != body.application_id
                                    or pending["detail"]["kind"] != "REVIEW_7B"):
            raise Problem(404, "/problems/not-found", "No such pending review application")
        if body.application_id:
            await close_application(session, case_id, body.application_id, body.decision)
        await action(session, case_id, "REVIEW", actor.subject, {**body.model_dump(), "own_motion": not body.application_id})
        values = {}
        if body.decision == "GRANTED":                 # notice to the parties, then a hearing and an order passed under review
            values = {"state": "REGISTERED", "concluded_on": None, "order_due_at": None}
            await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(**values))
        await record(session, actor, "inquiry.review_" + body.decision.lower(), "inquiry", case_id, body.note)
    return envelope(inquiry_view({**row, **values}))


class SetAsideInput(BaseModel):
    application_id: str
    decision: Literal["SET_ASIDE", "REJECTED"]
    note: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/set-asides")
async def set_aside(case_id: str, body: SetAsideInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                    session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await assigned(session, case_id, actor)
        require_step_up(actor, "set-aside-order", case_id)
        pending = await open_application(session, case_id)
        if not pending or pending["detail"]["application_id"] != body.application_id or pending["detail"]["kind"] != "SET_ASIDE":
            raise Problem(404, "/problems/not-found", "No such pending set-aside application")
        await close_application(session, case_id, body.application_id, body.decision)
        await action(session, case_id, "SET_ASIDE", actor.subject, body.model_dump())
        values = {}
        if body.decision == "SET_ASIDE":                # heard de novo (para 2.6.5); the demand is withdrawn
            await withdraw_order(session, actor, row, "Ex-parte order set aside under s.7A(4)")
            values = {"state": "REGISTERED", "concluded_on": None, "order_due_at": None, "order_demand_ids": [], "ex_parte": None}
            await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(**values))
            await session.execute(update(compliance_cases).where(compliance_cases.c.case_id == case_id).values(state="OPEN"))
        await record(session, actor, "inquiry.set_aside_" + body.decision.lower(), "inquiry", case_id, body.note)
    return envelope(inquiry_view({**row, **values}))


# ── 7C: an escaped amount, within 5 years of the 7A / 7B order ───────────────────────────────────────────────────────────
class EscapedInput(BaseModel):
    reason_type: Literal["OMISSION_BY_EMPLOYER", "INFORMATION_IN_POSSESSION"]
    reason: str = Field(min_length=1)
    period_from: str | None = None
    period_to: str | None = None


@router.post(BASE + "/cases/{case_id}/escaped-assessments-7c", status_code=201)
async def escaped(case_id: str, body: EscapedInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                  session: AsyncSession = Depends(db)):
    async with session.begin():
        parent = await assigned(session, case_id, actor)
        require_step_up(actor, "escaped-assessment", case_id)
        if parent["state"] != "ORDERED" or (parent.get("section") or "7A") == "14B":
            raise Problem(409, "/problems/invalid-state", "7C reopens a passed 7A / 7B order")
        _, limits = await rules(session)
        ordered = dt(parent["ordered_at"]).date()
        if now().date() > ordered.replace(year=ordered.year + limits["escaped_assessment_years"]):
            raise Problem(422, "/problems/out-of-time", f"7C lies within {limits['escaped_assessment_years']} years of the order (para 2.8.1)")
        child, at = f"CMP-{secrets.token_hex(5).upper()}", now()
        row = dict(case_id=child, diary_no=await next_diary(session, parent["office_id"]), office_id=parent["office_id"],
                   establishment_id=parent["establishment_id"], dispute="DUES", period_from=body.period_from or parent["period_from"],
                   period_to=body.period_to or parent["period_to"], inspection_id=parent["inspection_id"],
                   contributory_uans=parent["contributory_uans"], officer_rank=parent["officer_rank"], officer_subject=parent["officer_subject"],
                   registered_at=at, registration_due_at=None, concluded_on=None, order_due_at=None, state="REGISTERED",
                   section="7C", parent_case_id=case_id)
        await session.execute(insert(inquiries).values(**row))
        await session.execute(insert(compliance_cases).values(case_id=child, establishment_id=parent["establishment_id"],
            office_id=parent["office_id"], kind="INQUIRY_7C", wage_months=[], amount_paise=0, state="OPEN",
            history=[{"at": at.isoformat(), "by_role": actor.stakeholder, "action": "REOPENED_7C", "note": body.reason}],
            opened_by=actor.subject, created_at=at))
        await action(session, child, "REOPENED", actor.subject, {**body.model_dump(), "parent_case_id": case_id})
        await action(session, case_id, "ESCAPED_7C", actor.subject, {"child_case_id": child, **body.model_dump()})
        await event(session, actor, "InquiryRegistered.v1", "compliance_case", child,
                    {"case_id": child, "diary_no": row["diary_no"], "establishment_id": row["establishment_id"], "section": "7C",
                     "officer_rank": row["officer_rank"], "contributory_uans": int(row["contributory_uans"])})
        await record(session, actor, "inquiry.escaped_7c", "inquiry", child, body.reason)
    return envelope(inquiry_view(row))


# ── administrative scrutiny of orders (para 2.11): the next-higher officer, by the 15th of the following month ──────────
async def scrutiny_rank(session: AsyncSession, actor: Actor) -> str:
    if actor.stakeholder == "zo.acc":
        return "ZONAL_ACC"
    rank = (await session.execute(select(compliance_officers.c.rank).where(compliance_officers.c.subject == actor.subject))).scalar_one_or_none()
    return rank or ("RPFC-I" if actor.stakeholder == "fo.oic" else "")


async def due_for_scrutiny(session: AsyncSession, actor: Actor, month: str | None) -> list[dict]:
    rank = await scrutiny_rank(session, actor)
    query = select(inquiries).where(inquiries.c.state.in_(["ORDERED", "PART_ORDERED"]))
    if actor.stakeholder != "zo.acc":                  # the demo has one zone: the Zonal ACC sees every office's RPFC-I orders
        query = query.where(inquiries.c.office_id == await _office(session, actor))
    out = []
    for r in (await session.execute(query)).mappings().all():
        if NEXT_HIGHER.get(r["officer_rank"]) != rank or not r["ordered_at"]:
            continue
        ordered = dt(r["ordered_at"]).date()
        if month and ordered.strftime("%Y-%m") != month:
            continue
        done = [a for a in await case_actions(session, r["case_id"]) if a["kind"] == "SCRUTINY"]
        due = month_end_plus(ordered, 1) + timedelta(days=14)            # the 15th of the following month
        out.append({**inquiry_view(dict(r)), "ordered_at": iso(r["ordered_at"]), "scrutiny_due": due.isoformat(),
                    "scrutinised": bool(done), "overdue": not done and now().date() > due})
    return out


@router.get(BASE + "/scrutinies")
async def scrutinies(month: str | None = Query(None), actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "zo.acc")),
                     session: AsyncSession = Depends(db)):
    return envelope(await due_for_scrutiny(session, actor, month))


class ScrutinyInput(BaseModel):
    observations: str = Field(min_length=1)
    direct_7c: bool = False


@router.post(BASE + "/cases/{case_id}/scrutinies")
async def scrutinise(case_id: str, body: ScrutinyInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic", "zo.acc")),
                     session: AsyncSession = Depends(db)):
    async with session.begin():
        listed = {r["case_id"]: r for r in await due_for_scrutiny(session, actor, None)}
        if case_id not in listed:
            raise Problem(403, "/problems/not-the-scrutinising-officer", "The order is scrutinised by the officer next above the one who passed it (para 2.11.1)")
        if listed[case_id]["scrutinised"]:
            raise Problem(409, "/problems/already-scrutinised", "The order is already scrutinised")
        detail = {**body.model_dump(), "by_rank": await scrutiny_rank(session, actor), "late": listed[case_id]["overdue"]}
        await action(session, case_id, "SCRUTINY", actor.subject, detail)
        await record(session, actor, "inquiry.scrutiny", "inquiry", case_id, body.observations)
    return envelope(detail)
