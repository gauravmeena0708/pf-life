"""Synthetic inspection and section 7A inquiry workflow."""
import json
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _office, db
from app.infra.tables import (compliance_cases, compliance_officers, establishments, inquiry_actions, inquiries,
                              inspection_steps, inspections, office_staff)
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
BASE = "/api/v1/office/compliance"
PRODUCER = "compliance-service"


def now() -> datetime:
    return datetime.now(UTC)


def dt(value: Any) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def iso(value: Any) -> str | None:
    return dt(value).isoformat() if value is not None else None


def rupees(paise: int) -> str:
    """₹ with Indian digit grouping."""
    whole, frac = divmod(int(paise), 100)
    digits = str(whole)
    if len(digits) > 3:
        head, groups = digits[:-3], [digits[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join(([head] if head else []) + groups)
    return f"₹{digits}" + (f".{frac:02d}" if frac else "")


def month(value: str) -> bool:
    try:
        return date.fromisoformat(value + "-01").strftime("%Y-%m") == value
    except ValueError:
        return False


def period(start: str, end: str) -> None:
    if not month(start) or not month(end) or start > end:
        raise Problem(422, "/problems/validation", "Wage period must be ordered YYYY-MM months")


async def rules(session: AsyncSession) -> tuple[dict, dict]:
    document = await rules_on(session, now().date())
    return document, section(document, "compliance_proceedings")


async def establishment(session: AsyncSession, establishment_id: str, office: str) -> dict:
    row = (await session.execute(select(establishments).where(establishments.c.establishment_id == establishment_id))).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Establishment not found in this office")
    return dict(row)


async def inspection(session: AsyncSession, inspection_id: str, office: str) -> dict:
    row = (await session.execute(select(inspections).where(inspections.c.inspection_id == inspection_id))).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Inspection not found")
    return dict(row)


async def inquiry(session: AsyncSession, case_id: str, office: str | None = None) -> dict:
    row = (await session.execute(select(inquiries).where(inquiries.c.case_id == case_id))).mappings().first()
    if not row or (office is not None and row["office_id"] != office):
        raise Problem(404, "/problems/not-found", "Inquiry not found")
    return dict(row)


async def action(session: AsyncSession, case_id: str, kind: str, subject: str, detail: dict) -> None:
    await session.execute(insert(inquiry_actions).values(action_id=f"ACT-{secrets.token_hex(8)}", case_id=case_id,
        kind=kind, actor_subject=subject, detail=detail, occurred_at=now()))


async def event(session: AsyncSession, actor: Actor, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict) -> None:
    await add_event(session, producer=PRODUCER, event_type=event_type, aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id, correlation_id=actor.correlation_id, payload=payload)


async def record(session: AsyncSession, actor: Actor, action_name: str, target_type: str, target_id: str, detail: str) -> None:
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=action_name,
                target_type=target_type, target_id=target_id, detail=detail)


class InspectionInput(BaseModel):
    establishment_id: str
    purpose: Literal["COMPLAINT", "CAIU_ALLOCATION", "DEFAULTER", "SURVEY"]
    period_from: str
    period_to: str
    eo_subject: str | None = None          # left out: one of the office's Enforcement Officers at random
    note: str = Field(min_length=1)
    signal_id: str | None = None


async def inspection_view(session: AsyncSession, row: dict) -> dict:
    steps = (await session.execute(select(inspection_steps).where(inspection_steps.c.inspection_id == row["inspection_id"])
                                   .order_by(inspection_steps.c.occurred_at))).mappings().all()
    return {**row, "due_at": iso(row["due_at"]), "created_at": iso(row["created_at"]),
            "overdue": row["state"] not in ("DECIDED_INITIATE", "CLOSED") and now() > dt(row["due_at"]),
            "steps": [{**s, "due_at": iso(s["due_at"]), "occurred_at": iso(s["occurred_at"]),
                       "overdue": s["due_at"] is not None and dt(s["occurred_at"]) > dt(s["due_at"])} for s in steps]}


@router.post(BASE + "/inspections", status_code=201)
async def schedule(body: InspectionInput, actor: Actor = Depends(require_stakeholder("fo.apfc")), session: AsyncSession = Depends(db)):
    period(body.period_from, body.period_to)
    async with session.begin():
        office = await _office(session, actor)
        await establishment(session, body.establishment_id, office)
        eos = (await session.execute(select(office_staff.c.subject).where(office_staff.c.office_id == office,
               office_staff.c.stakeholder == "fo.eo"))).scalars().all()
        if not eos or (body.eo_subject and body.eo_subject not in eos):
            raise Problem(422, "/problems/validation", "EO must be posted to this office")
        body.eo_subject = body.eo_subject or secrets.choice(eos)
        _, limits = await rules(session)
        created = now()
        row = dict(inspection_id=f"INS-{secrets.token_hex(5).upper()}", establishment_id=body.establishment_id,
                   office_id=office, eo_subject=body.eo_subject, circle_officer=actor.subject, purpose=body.purpose,
                   period_from=body.period_from, period_to=body.period_to, signal_id=body.signal_id, note=body.note,
                   state="SCHEDULED", report=None, decision=None, created_at=created,
                   due_at=created + timedelta(days=limits["inspection_report_days"]))
        await session.execute(insert(inspections).values(**row))
        await record(session, actor, "inspection.scheduled", "inspection", row["inspection_id"], body.note)
        result = await inspection_view(session, row)
    return envelope(result)


@router.get(BASE + "/inspections")
async def list_inspections(state: str | None = Query(None), actor: Actor = Depends(require_stakeholder(
        "fo.apfc", "fo.eo", "fo.da_compliance", "fo.ss", "fo.oic")), session: AsyncSession = Depends(db)):
    office = await _office(session, actor)
    query = select(inspections).where(inspections.c.office_id == office)
    if actor.stakeholder == "fo.eo":
        query = query.where(inspections.c.eo_subject == actor.subject)
    if state:
        query = query.where(inspections.c.state == state)
    rows = (await session.execute(query.order_by(inspections.c.created_at.desc()))).mappings().all()
    return envelope([await inspection_view(session, dict(row)) for row in rows])


class ReportInput(BaseModel):
    visited_on: date
    employees_found: int = Field(ge=0)
    employees_not_enrolled: int = Field(ge=0)
    wages_paise_monthly: int = Field(ge=0)
    findings: str = Field(min_length=1)
    dues_estimate_paise: int = Field(ge=0)
    recommendation: Literal["INITIATE_7A_DUES", "INITIATE_7A_APPLICABILITY", "NO_ACTION"]
    documents: list[str] = Field(default_factory=list)


@router.post(BASE + "/inspections/{inspection_id}/reports")
async def report(inspection_id: str, body: ReportInput, actor: Actor = Depends(require_stakeholder("fo.eo")),
                 session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await inspection(session, inspection_id, await _office(session, actor))
        if row["eo_subject"] != actor.subject:
            raise Problem(403, "/problems/assigned-officer", "Only the assigned EO may report")
        if row["state"] != "SCHEDULED" or body.visited_on > now().date() or body.employees_not_enrolled > body.employees_found:
            raise Problem(422, "/problems/validation", "Report state, visit date or employee counts are invalid")
        _, limits = await rules(session)
        at = now()
        due = at + timedelta(days=limits["da_note_days"])
        detail = body.model_dump(mode="json")
        await session.execute(update(inspections).where(inspections.c.inspection_id == inspection_id).values(
            state="REPORTED", report=detail, due_at=due))
        await session.execute(insert(inspection_steps).values(step_id=f"ST-{secrets.token_hex(8)}", inspection_id=inspection_id,
            stage="REPORT", actor_subject=actor.subject, note=body.findings, detail=detail, due_at=row["due_at"], occurred_at=at))
        await event(session, actor, "InspectionReported.v1", "inspection", inspection_id,
                    {"inspection_id": inspection_id, "establishment_id": row["establishment_id"],
                     "recommendation": body.recommendation, "dues_estimate_paise": body.dues_estimate_paise})
        await record(session, actor, "inspection.reported", "inspection", inspection_id, body.findings)
        result = await inspection_view(session, {**row, "state": "REPORTED", "report": detail, "due_at": due})
    return envelope(result)


class ProcessingNote(BaseModel):
    note: str = Field(min_length=1)
    decision: Literal["INITIATE_7A", "NO_ACTION"] | None = None


@router.post(BASE + "/inspections/{inspection_id}/processing-notes")
async def process_note(inspection_id: str, body: ProcessingNote, actor: Actor = Depends(require_stakeholder(
        "fo.da_compliance", "fo.ss", "fo.apfc")), session: AsyncSession = Depends(db)):
    stages = {"fo.da_compliance": ("REPORTED", "DA_NOTED", "DA_NOTE", "ss_note_days"),
              "fo.ss": ("DA_NOTED", "SS_NOTED", "SS_NOTE", "decision_days"),
              "fo.apfc": ("SS_NOTED", "DECIDED_INITIATE" if body.decision == "INITIATE_7A" else "CLOSED", "DECISION", "registration_days")}
    expected, state, stage, next_key = stages[actor.stakeholder]
    async with session.begin():
        row = await inspection(session, inspection_id, await _office(session, actor))
        if row["state"] != expected:
            raise Problem(409, "/problems/invalid-state", f"Expected {expected}")
        if actor.stakeholder == "fo.apfc" and (actor.subject != row["circle_officer"] or body.decision is None):
            raise Problem(403, "/problems/assigned-officer", "Circle officer decision required")
        if actor.stakeholder != "fo.apfc" and body.decision is not None:
            raise Problem(422, "/problems/validation", "Decision belongs to the circle officer")
        _, limits = await rules(session)
        at = now()
        due = at + timedelta(days=limits[next_key])
        values = {"state": state, "due_at": due, "decision": body.decision if stage == "DECISION" else row["decision"]}
        await session.execute(update(inspections).where(inspections.c.inspection_id == inspection_id).values(**values))
        await session.execute(insert(inspection_steps).values(step_id=f"ST-{secrets.token_hex(8)}", inspection_id=inspection_id,
            stage=stage, actor_subject=actor.subject, note=body.note, detail={"decision": body.decision} if body.decision else {},
            due_at=row["due_at"], occurred_at=at))
        await record(session, actor, "inspection." + stage.lower(), "inspection", inspection_id, body.note)
        result = await inspection_view(session, {**row, **values})
    return envelope(result)


class InquiryInput(BaseModel):
    establishment_id: str
    kind: Literal["INQUIRY_7A"] = "INQUIRY_7A"
    dispute: Literal["DUES", "APPLICABILITY"]
    period_from: str
    period_to: str
    inspection_id: str | None = None
    contributory_uans: int = Field(ge=0)
    note: str = Field(min_length=1)
    oic_approval: str | None = None        # without an inspection: the OIC's approval on credible information (para 2.3.1 iii)


async def register(body: InquiryInput, actor: Actor, session: AsyncSession) -> dict:
    period(body.period_from, body.period_to)
    office = await _office(session, actor)
    await establishment(session, body.establishment_id, office)
    source = await inspection(session, body.inspection_id, office) if body.inspection_id else None
    if source:
        if source["state"] != "DECIDED_INITIATE" or source["establishment_id"] != body.establishment_id:
            raise Problem(422, "/problems/validation", "Inspection must be approved for this establishment")
        if body.contributory_uans < int(source["report"]["employees_found"]):
            raise Problem(422, "/problems/validation", "Contributory UAN count cannot be below the EO count")
    elif not (body.oic_approval or "").strip():
        raise Problem(422, "/problems/validation", "Without an inspection report, record the OIC's approval of the inquiry on credible information",
                      "Compliance Manual para 2.3.1 (iii).")
    document, limits = await rules(session)
    rank = next(t["rank"] for t in limits["allocation_tiers"] if t["up_to_uans"] is None or body.contributory_uans <= t["up_to_uans"])
    officers = (await session.execute(select(compliance_officers).where(compliance_officers.c.office_id == office,
                compliance_officers.c.rank == rank, compliance_officers.c.barred.is_(False)))).mappings().all()
    eligible = [r["subject"] for r in officers if not source or r["subject"] != source["eo_subject"]]
    if eligible:
        assigned = secrets.choice(eligible)
    else:
        assigned = (await session.execute(select(office_staff.c.subject).where(office_staff.c.office_id == office,
                    office_staff.c.stakeholder == "fo.oic"))).scalar_one_or_none()
        if not assigned:
            raise Problem(422, "/problems/no-officer", "No eligible officer or OIC is posted")
    year = now().year
    prefix = f"EPR/{office}/{year}/"
    prior = (await session.execute(select(inquiries.c.diary_no).where(inquiries.c.diary_no.like(prefix + "%")))).scalars().all()
    sequence = max((int(s.rsplit("/", 1)[-1]) for s in prior), default=0) + 1
    case_id = f"CMP-{secrets.token_hex(5).upper()}"
    at = now()
    registration_due = dt(source["due_at"]) if source else None
    row = dict(case_id=case_id, diary_no=prefix + f"{sequence:04d}", office_id=office,
               establishment_id=body.establishment_id, dispute=body.dispute, period_from=body.period_from,
               period_to=body.period_to, inspection_id=body.inspection_id, contributory_uans=body.contributory_uans,
               officer_rank=rank, officer_subject=assigned, registered_at=at, registration_due_at=registration_due,
               concluded_on=None, order_due_at=None, state="REGISTERED")
    await session.execute(insert(inquiries).values(**row))
    await session.execute(insert(compliance_cases).values(case_id=case_id, establishment_id=body.establishment_id,
        office_id=office, kind="INQUIRY_7A", wage_months=[], amount_paise=0, state="OPEN",
        history=[{"at": at.isoformat(), "by_role": actor.stakeholder, "action": "REGISTERED", "note": body.note}],
        opened_by=actor.subject, created_at=at))
    await event(session, actor, "InquiryRegistered.v1", "compliance_case", case_id,
                {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": body.establishment_id,
                 "section": "7A", "officer_rank": rank, "contributory_uans": body.contributory_uans})
    await record(session, actor, "inquiry.registered", "inquiry", case_id, body.note)
    return inquiry_view(row)


def inquiry_view(row: dict) -> dict:
    return {**row, "registered_at": iso(row["registered_at"]), "registration_due_at": iso(row["registration_due_at"]),
            "registration_overdue": bool(row["registration_due_at"] and dt(row["registered_at"]) > dt(row["registration_due_at"])),
            "concluded_on": iso(row["concluded_on"]), "order_due_at": iso(row["order_due_at"])}


async def assigned(session: AsyncSession, case_id: str, actor: Actor) -> dict:
    row = await inquiry(session, case_id, await _office(session, actor))
    if row["officer_subject"] != actor.subject:
        raise Problem(403, "/problems/assigned-officer", "Only the assigned inquiry officer may act")
    return row


class AllocationInput(BaseModel):
    officer_subject: str
    reason: Literal["TRANSFER", "SENSITIVE_POST_BAR", "EARLIER_IN_CASE", "OTHER"]
    note: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/allocations")
async def reallocate(case_id: str, body: AllocationInput, actor: Actor = Depends(require_stakeholder("fo.oic")),
                     session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await inquiry(session, case_id, await _office(session, actor))
        require_step_up(actor, "reallocate-inquiry", case_id)
        if body.officer_subject == row["officer_subject"]:
            raise Problem(422, "/problems/validation", "Choose a different officer")
        candidate = (await session.execute(select(compliance_officers).where(compliance_officers.c.subject == body.officer_subject,
                     compliance_officers.c.office_id == row["office_id"]))).mappings().first()
        is_oic = (await session.execute(select(office_staff.c.subject).where(office_staff.c.subject == body.officer_subject,
                  office_staff.c.office_id == row["office_id"], office_staff.c.stakeholder == "fo.oic"))).first()
        if not is_oic and (not candidate or candidate["rank"] != row["officer_rank"] or candidate["barred"]):
            raise Problem(422, "/problems/validation", "Replacement must be an eligible officer of the same rank or the OIC")
        source = await inspection(session, row["inspection_id"], row["office_id"]) if row["inspection_id"] else None
        if source and source["eo_subject"] == body.officer_subject:
            raise Problem(422, "/problems/validation", "The inspecting EO cannot conduct this inquiry")
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(officer_subject=body.officer_subject))
        await action(session, case_id, "ALLOCATION", actor.subject, body.model_dump())
        await record(session, actor, "inquiry.reallocated", "inquiry", case_id, body.note)
    return envelope(inquiry_view({**row, "officer_subject": body.officer_subject}))


class NoticeInput(BaseModel):
    hearing_at: datetime
    scope: str = Field(min_length=1)
    period: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/notices")
async def notice(case_id: str, body: NoticeInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                 session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await assigned(session, case_id, actor)
        require_step_up(actor, "issue-summons", case_id)
        if dt(body.hearing_at) <= now() or row["state"] == "ORDERED":
            raise Problem(422, "/problems/validation", "Summons need a future hearing in an open inquiry")
        detail = {"diary_no": row["diary_no"], "hearing_at": iso(body.hearing_at), "scope": body.scope,
                  "period": body.period, "meeting_link": f"https://meet.example.invalid/{case_id}",
                  "case_status_url": f"http://eproceedings.epfindia.gov.in/epfo/public/caseenowisesearch.php?diary={row['diary_no']}",
                  "served": True, "service_records": ["e-mail (mock)", "speed post (mock)"],
                  "service_method": "by e-mail and speed post"}
        await action(session, case_id, "SUMMONS", actor.subject, detail)
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(state="SUMMONED"))
        await event(session, actor, "SummonsIssued.v1", "compliance_case", case_id,
                    {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": row["establishment_id"],
                     "hearing_at": detail["hearing_at"]})
        await record(session, actor, "inquiry.summons_issued", "inquiry", case_id, body.scope)
    return envelope(detail)


class HearingInput(BaseModel):
    held_at: datetime
    employer_present: bool
    eo_present: bool
    proceedings: str = Field(min_length=1)
    documents_received: list[str] = Field(default_factory=list)
    next_hearing_at: datetime | None = None
    concluded: bool = False
    adjournment_reason: str | None = None

    @model_validator(mode="after")
    def conclusion(self):
        if self.concluded == (self.next_hearing_at is not None):
            raise ValueError("Give either a next hearing or concluded=true")
        return self


def working_day_after(start: datetime, count: int) -> datetime:
    day = start
    for _ in range(count):
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
    return day


@router.post(BASE + "/cases/{case_id}/hearings")
async def hearing(case_id: str, body: HearingInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                  session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await assigned(session, case_id, actor)
        if row["state"] not in ("SUMMONED", "HEARING"):
            raise Problem(409, "/problems/invalid-state", "Issue summons before recording a hearing")
        summons = (await session.execute(select(inquiry_actions).where(inquiry_actions.c.case_id == case_id,
                   inquiry_actions.c.kind == "SUMMONS").order_by(inquiry_actions.c.occurred_at.desc()))).mappings().first()
        if dt(body.held_at) < dt(summons["detail"]["hearing_at"]) or dt(body.held_at) > now():
            raise Problem(422, "/problems/validation", "Hearing date must follow the summons and cannot be future")
        document, limits = await rules(session)
        if body.next_hearing_at and (dt(body.next_hearing_at) <= dt(body.held_at) or
            (dt(body.next_hearing_at) > dt(body.held_at) + timedelta(days=limits["adjournment_max_days"]) and not body.adjournment_reason)):
            raise Problem(422, "/problems/adjournment", "Adjournment beyond the rule limit needs a reason")
        detail = body.model_dump(mode="json")
        await action(session, case_id, "HEARING", actor.subject, detail)
        values = {"state": "CONCLUDED" if body.concluded else "HEARING"}
        if body.concluded:
            values.update(concluded_on=dt(body.held_at), order_due_at=working_day_after(dt(body.held_at), limits["order_working_days"]))
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(**values))
        await record(session, actor, "inquiry.hearing", "inquiry", case_id, body.proceedings)
    return envelope({**detail, "order_due_at": iso(values.get("order_due_at"))})


class SubmissionInput(BaseModel):
    kind: Literal["REPLY", "EVIDENCE"]
    text: str = Field(min_length=1)
    documents: list[str] = Field(default_factory=list)


async def case_actions(session: AsyncSession, case_id: str) -> list[dict]:
    rows = (await session.execute(select(inquiry_actions).where(inquiry_actions.c.case_id == case_id)
                                   .order_by(inquiry_actions.c.occurred_at))).mappings().all()
    return [{"kind": r["kind"], "detail": r["detail"], "at": iso(r["occurred_at"])} for r in rows]


@router.get("/api/v1/employers/me/proceedings")
async def employer_proceedings(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")),
                               session: AsyncSession = Depends(db)):
    rows = (await session.execute(select(inquiries).where(inquiries.c.establishment_id == (actor.establishment_id or ""))
                                  .order_by(inquiries.c.registered_at.desc()))).mappings().all()
    result = []
    for row in rows:
        actions = await case_actions(session, row["case_id"])
        safe = inquiry_view(dict(row))
        safe.pop("officer_subject", None)
        result.append({**safe, "summons": [a for a in actions if a["kind"] == "SUMMONS"],
                       "hearings": [a for a in actions if a["kind"] == "HEARING"],
                       "daily_orders": [a for a in actions if a["kind"] == "HEARING"],
                       "submissions": [a for a in actions if a["kind"] == "SUBMISSION"],
                       "order": next((a for a in actions if a["kind"] == "ORDER"), None)})
    return envelope(result)


@router.post("/api/v1/employers/me/proceedings/{case_id}/submissions")
async def submit(case_id: str, body: SubmissionInput, actor: Actor = Depends(require_stakeholder(
        "employer.owner", "employer.signatory")), session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await inquiry(session, case_id)
        if row["establishment_id"] != actor.establishment_id:
            raise Problem(404, "/problems/not-found", "Inquiry not found")
        if row["state"] == "ORDERED":
            raise Problem(409, "/problems/invalid-state", "Order already passed")
        detail = body.model_dump()
        await action(session, case_id, "SUBMISSION", actor.subject, detail)
        await record(session, actor, "inquiry.submitted", "inquiry", case_id, body.kind)
    return envelope(detail)


class DuesRow(BaseModel):
    wage_month: str
    ac1_employee_paise: int = Field(ge=0)
    ac1_employer_paise: int = Field(ge=0)
    ac10_pension_paise: int = Field(ge=0)
    ac21_edli_paise: int = Field(ge=0)
    ac2_admin_paise: int = Field(ge=0)


class OrderInput(BaseModel):
    kind: str
    dues: list[DuesRow] = Field(min_length=1)
    lump_sum_reason: str | None = None
    reasoning: str = Field(min_length=1)
    ex_parte: bool


@router.post(BASE + "/cases/{case_id}/orders")
async def order(case_id: str, body: OrderInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                session: AsyncSession = Depends(db)):
    if body.kind in ("14B", "7Q"):
        raise Problem(501, "/problems/not-implemented", "P2.11b")
    if body.kind != "7A":
        raise Problem(422, "/problems/validation", "Order kind must be 7A")
    async with session.begin():
        row = await assigned(session, case_id, actor)
        if row["state"] != "CONCLUDED":
            raise Problem(422, "/problems/validation", "A served summons and a concluded hearing are required")
        actions = await case_actions(session, case_id)
        summons = [a for a in actions if a["kind"] == "SUMMONS"]
        hearings = [a for a in actions if a["kind"] == "HEARING"]
        if not summons or not hearings or not hearings[-1]["detail"]["concluded"]:
            raise Problem(422, "/problems/validation", "A served summons and a concluded hearing are required")
        if body.ex_parte and (not summons[-1]["detail"]["served"] or hearings[-1]["detail"]["employer_present"]):
            raise Problem(422, "/problems/ex-parte", "Para 2.6.2 requires due service and employer absence at the last hearing")
        months = [d.wage_month for d in body.dues]
        if (len(set(months)) != len(months) or any(not month(m) and m != "LUMP_SUM" for m in months)
            or ("LUMP_SUM" in months and (len(months) != 1 or not body.lump_sum_reason))):
            raise Problem(422, "/problems/validation", "Use distinct wage months or give a lump sum reason")
        if any(m != "LUMP_SUM" and not row["period_from"] <= m <= row["period_to"] for m in months):
            raise Problem(422, "/problems/validation", "Dues month falls outside inquiry period")
        dues = [d.model_dump() for d in body.dues]
        total = sum(sum(v for k, v in d.items() if k.endswith("_paise")) for d in dues)
        require_step_up(actor, "pass-order", case_id, None, total)
        document, _ = await rules(session)
        name = (await session.execute(select(establishments.c.legal_name).where(
            establishments.c.establishment_id == row["establishment_id"]))).scalar_one()
        table = "\n".join(f"{d['wage_month']}: A/c 1 employee {rupees(d['ac1_employee_paise'])}, A/c 1 employer "
                          f"{rupees(d['ac1_employer_paise'])}, A/c 10 {rupees(d['ac10_pension_paise'])}, A/c 21 "
                          f"{rupees(d['ac21_edli_paise'])}, A/c 2 {rupees(d['ac2_admin_paise'])}" for d in dues)
        text = (f"ORDER UNDER SECTION 7A — {row['diary_no']}\nParties: EPFO and {name} ({row['establishment_id']}).\n"
                f"Period: {row['period_from']} to {row['period_to']}.\nSummons served by e-mail and speed post; "
                f"hearings: {', '.join(a['detail']['held_at'] for a in hearings)}.\nFindings and reasons: {body.reasoning}\n"
                f"Dues by account and month:\n{table}\nTotal dues assessed: {rupees(total)}. "
                "The establishment is directed to pay within 15 days.")
        late = now() > dt(row["order_due_at"])
        demand_id = f"D7A-{case_id}"
        detail = {"kind": "7A", "diary_no": row["diary_no"], "dues": dues, "total_paise": total,
                  "reasoning": body.reasoning, "ex_parte": body.ex_parte, "late": late,
                  "order_due_at": iso(row["order_due_at"]), "text": text, "demand_id": demand_id}
        await action(session, case_id, "ORDER", actor.subject, detail)
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(state="ORDERED"))
        await session.execute(update(compliance_cases).where(compliance_cases.c.case_id == case_id).values(
            state="CLOSED", amount_paise=total))
        await event(session, actor, "DemandRaised.v1", "demand", demand_id,
                    {"demand_id": demand_id, "establishment_id": row["establishment_id"], "demand_type": "DUES_7A",
                     "amount_paise": total, "supersedes_demand_ids": [], "working": json.dumps(dues),
                     "rule_version": document["rule_version"]})
        await event(session, actor, "InquiryOrderPassed.v1", "compliance_case", case_id,
                    {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": row["establishment_id"],
                     "section": "7A", "ex_parte": body.ex_parte, "total_paise": total, "demand_id": demand_id})
        await record(session, actor, "inquiry.order_passed", "inquiry", case_id, body.reasoning)
    return envelope(detail)
