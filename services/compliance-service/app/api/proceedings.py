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
from app.infra.tables import (compliance_cases, compliance_officers, demands, establishments, inquiry_actions, inquiries,
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


class ContractorFinding(BaseModel):
    contractor_name: str = Field(min_length=1)
    contractor_establishment_id: str | None = None
    traceable: bool = True
    unpaid_dues_paise: int = Field(default=0, ge=0)
    workers_count: int = Field(default=0, ge=0)
    work_order_ref: str | None = None
    findings: str | None = None


class ReportInput(BaseModel):
    visited_on: date
    employees_found: int = Field(ge=0)
    employees_not_enrolled: int = Field(ge=0)
    wages_paise_monthly: int = Field(ge=0)
    findings: str = Field(min_length=1)
    dues_estimate_paise: int = Field(ge=0)
    recommendation: Literal["INITIATE_7A_DUES", "INITIATE_7A_APPLICABILITY", "NO_ACTION"]
    documents: list[str] = Field(default_factory=list)
    contractors: list[ContractorFinding] = Field(default_factory=list)


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


async def allocate(session: AsyncSession, office: str, uans: int, exclude: set[str] = frozenset()) -> tuple[str, str]:
    """The rank the size calls for (para 2.5.1 / 3.3.7) and an officer of it at random, never one barred from a sensitive
    charge nor one excluded (the inspecting EO, an officer earlier in the case); the OIC when there is none."""
    _, limits = await rules(session)
    rank = next(t["rank"] for t in limits["allocation_tiers"] if t["up_to_uans"] is None or uans <= t["up_to_uans"])
    officers = (await session.execute(select(compliance_officers).where(compliance_officers.c.office_id == office,
                compliance_officers.c.rank == rank, compliance_officers.c.barred.is_(False)))).mappings().all()
    eligible = [r["subject"] for r in officers if r["subject"] not in exclude]
    if eligible:
        return rank, secrets.choice(eligible)
    oic = (await session.execute(select(office_staff.c.subject).where(office_staff.c.office_id == office,
           office_staff.c.stakeholder == "fo.oic"))).scalar_one_or_none()
    if not oic:
        raise Problem(422, "/problems/no-officer", "No eligible officer or OIC is posted")
    return rank, oic


async def next_diary(session: AsyncSession, office: str) -> str:
    prefix = f"EPR/{office}/{now().year}/"
    prior = (await session.execute(select(inquiries.c.diary_no).where(inquiries.c.diary_no.like(prefix + "%")))).scalars().all()
    return prefix + f"{max((int(s.rsplit('/', 1)[-1]) for s in prior), default=0) + 1:04d}"


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
    rank, assigned = await allocate(session, office, body.contributory_uans, exclude={source["eo_subject"]} if source else set())
    diary = await next_diary(session, office)
    case_id = f"CMP-{secrets.token_hex(5).upper()}"
    at = now()
    registration_due = dt(source["due_at"]) if source else None
    row = dict(case_id=case_id, diary_no=diary, office_id=office, section="7A",
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
                       "applications": [a for a in actions if a["kind"] == "APPLICATION"],
                       "order": next((a for a in reversed(actions) if a["kind"] == "ORDER" and not a["detail"].get("superseded")), None),
                       "orders": [a for a in actions if a["kind"] == "ORDER"]})
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


class LevyItem(BaseModel):
    demand_id: str
    amount_paise: int = Field(ge=0)


class MemberDecision(BaseModel):
    name: str
    uan: str | None = None
    eligible: bool
    from_date: date | None = None                  # membership from this date when eligible


class ContractorLiability(BaseModel):
    contractor_name: str = Field(min_length=1)
    contractor_establishment_id: str | None = None
    traceable: bool = True
    work_order_ref: str | None = None


class OrderInput(BaseModel):
    kind: Literal["7A", "14B", "7Q", "26B"]
    decisions: list[MemberDecision] = Field(default_factory=list)   # 26B: each disputed employee's membership
    dues: list[DuesRow] = Field(default_factory=list)          # 7A / 7C: month-wise dues by account
    levies: list[LevyItem] = Field(default_factory=list)       # 14B / 7Q: the amount levied for each auto-calculated demand
    lump_sum_reason: str | None = None
    reasoning: str = Field(min_length=1)
    ex_parte: bool
    contractor: ContractorLiability | None = None


DEMAND_KIND = {"14B": "DAMAGES_14B", "7Q": "INTEREST_7Q"}


@router.post(BASE + "/cases/{case_id}/orders")
async def order(case_id: str, body: OrderInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await assigned(session, case_id, actor)
        if body.contractor:
            # EPF Act s.8A: A contractor with its own EPF code number who is traceable is liable itself — dues cannot be assessed against principal.
            if body.contractor.contractor_establishment_id and body.contractor.traceable:
                raise Problem(422, "/problems/validation",
                              "Contractor liable itself",
                              "A contractor with its own EPF code number who is traceable is liable itself — "
                              "dues cannot be assessed against the principal employer under EPF Act s.8A")
        section = row.get("section") or "7A"
        takes = {"7A": {"7A"}, "7C": {"7A"}, "14B": {"14B", "7Q"}, "26B": {"26B"}}[section]
        if body.kind not in takes:
            raise Problem(422, "/problems/validation", f"A section {section} case takes a {' or '.join(sorted(takes))} order")
        if row["state"] not in ("CONCLUDED", "PART_ORDERED"):
            raise Problem(422, "/problems/validation", "A served summons and a concluded hearing are required")
        actions = await case_actions(session, case_id)
        summons = [a for a in actions if a["kind"] == "SUMMONS"]
        hearings = [a for a in actions if a["kind"] == "HEARING"]
        if not summons or not hearings or not hearings[-1]["detail"]["concluded"]:
            raise Problem(422, "/problems/validation", "A served summons and a concluded hearing are required")
        if body.ex_parte and (not summons[-1]["detail"]["served"] or hearings[-1]["detail"]["employer_present"]):
            raise Problem(422, "/problems/ex-parte", "Para 2.6.2 requires due service and employer absence at the last hearing")
        document, _ = await rules(session)
        if section == "26B":                            # whether each disputed employee is a member, and from when (ch. 4)
            disputed = next(a for a in actions if a["kind"] == "DISPUTE")["detail"]["employees"]
            given = {d.name: d for d in body.decisions}
            if set(given) != {e["name"] for e in disputed} or any(d.eligible and not d.from_date for d in body.decisions):
                raise Problem(422, "/problems/validation", "Decide each disputed employee; an eligible one needs the date membership starts")
            text = (f"ORDER UNDER PARA 26B OF THE EPF SCHEME — {row['diary_no']}\nFindings and reasons: {body.reasoning}\n" + "\n".join(
                f"{d.name}{f' (UAN {d.uan})' if d.uan else ''}: {'a member from ' + d.from_date.isoformat() if d.eligible else 'not eligible'}"
                for d in body.decisions) + "\nThe employer is directed to enrol the eligible employees; if not, the dues are determined under 7A (para 4.6.3).")
            detail = {"kind": "26B", "diary_no": row["diary_no"], "decisions": [d.model_dump(mode="json") for d in body.decisions], "total_paise": 0,
                      "reasoning": body.reasoning, "ex_parte": body.ex_parte, "late": now() > dt(row["order_due_at"]), "text": text, "demand_id": ""}
            require_step_up(actor, "pass-order", case_id, None, 0)
            await action(session, case_id, "ORDER", actor.subject, detail)
            await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(state="ORDERED", ordered_at=now(), ex_parte=body.ex_parte))
            await session.execute(update(compliance_cases).where(compliance_cases.c.case_id == case_id).values(state="CLOSED"))
            await event(session, actor, "InquiryOrderPassed.v1", "compliance_case", case_id,
                        {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": row["establishment_id"], "section": "26B",
                         "ex_parte": body.ex_parte, "total_paise": 0, "demand_id": ""})
            await record(session, actor, "inquiry.order_passed", "inquiry", case_id, body.reasoning)
            return envelope(detail)
        name = (await session.execute(select(establishments.c.legal_name).where(
            establishments.c.establishment_id == row["establishment_id"]))).scalar_one()
        earlier = [a for a in actions if a["kind"] == "ORDER"]
        if section == "14B":
            kind = DEMAND_KIND[body.kind]
            if any(a["detail"]["kind"] == body.kind for a in earlier if not a["detail"].get("superseded")):
                raise Problem(409, "/problems/already-ordered", f"The {body.kind} order is already passed")
            covered = (await session.execute(select(demands).where(demands.c.demand_id.in_(row["demand_ids"] or []),
                       demands.c.kind == kind))).mappings().all()
            given = {item.demand_id: item.amount_paise for item in body.levies}
            if not covered or set(given) != {d["demand_id"] for d in covered}:
                raise Problem(422, "/problems/validation", f"Levy an amount for each {body.kind} demand the notice covers, and only those")
            for d in covered:
                if given[d["demand_id"]] > int(d["amount_paise"]):
                    raise Problem(422, "/problems/validation", "No more than the amount the notice worked out")
                if body.kind == "7Q" and given[d["demand_id"]] != int(d["amount_paise"]):
                    raise Problem(422, "/problems/validation", "Interest under 7Q is at the statutory rate; it cannot be varied")
            total = sum(given.values())
            lines = [{"demand_id": d["demand_id"], "wage_month": d["wage_month"], "days_late": int(d["days_late"]),
                      "auto_paise": int(d["amount_paise"]), "levied_paise": given[d["demand_id"]]} for d in covered]
            table = "\n".join(f"{x['wage_month']} ({x['days_late']} days late): worked out {rupees(x['auto_paise'])}, levied {rupees(x['levied_paise'])}"
                              for x in lines)
            demand_id, demand_type, supersedes = f"D{body.kind}-{case_id}", kind, [d["demand_id"] for d in covered]
            heading = "DAMAGES UNDER SECTION 14B" if body.kind == "14B" else "INTEREST UNDER SECTION 7Q"
            working = json.dumps(lines)
        else:
            dues = [d.model_dump() for d in body.dues]
            if not dues:
                raise Problem(422, "/problems/validation", "Give the dues month by month")
            months = [d["wage_month"] for d in dues]
            if (len(set(months)) != len(months) or any(not month(m) and m != "LUMP_SUM" for m in months)
                    or ("LUMP_SUM" in months and (len(months) != 1 or not body.lump_sum_reason))):
                raise Problem(422, "/problems/validation", "Use distinct wage months or give a lump sum reason")
            if any(m != "LUMP_SUM" and not row["period_from"] <= m <= row["period_to"] for m in months):
                raise Problem(422, "/problems/validation", "Dues month falls outside inquiry period")
            total = sum(sum(v for k, v in d.items() if k.endswith("_paise")) for d in dues)
            table = "\n".join(f"{d['wage_month']}: A/c 1 employee {rupees(d['ac1_employee_paise'])}, A/c 1 employer "
                              f"{rupees(d['ac1_employer_paise'])}, A/c 10 {rupees(d['ac10_pension_paise'])}, A/c 21 "
                              f"{rupees(d['ac21_edli_paise'])}, A/c 2 {rupees(d['ac2_admin_paise'])}" for d in dues)
            tag = "D7C" if section == "7C" else "D7A"
            demand_id = f"{tag}-{case_id}" + (f"-R{len(earlier)}" if earlier else "")       # after a review: a fresh demand
            demand_type = "DUES_7A"
            supersedes = list(row.get("order_demand_ids") or []) if earlier else []           # the order under review is replaced
            heading = "ORDER UNDER SECTION 7C (ESCAPED AMOUNT)" if section == "7C" else "ORDER UNDER SECTION 7A"
            lines, working = dues, json.dumps(dues)
        require_step_up(actor, "pass-order", case_id, None, total)
        review = " (order passed under review, section 7B)" if earlier and section != "14B" else ""
        contractor_note = ""
        if body.contractor:
            # EPF Act s.8A: Contractor dues assessed against principal employer when contractor is not traceable.
            # Principal employer may recover from contractor by deduction from amounts payable or as a debt.
            contractor_note = (
                f"\nContractor liability (EPF Act s.8A): Contractor '{body.contractor.contractor_name}' "
                f"({'code: ' + body.contractor.contractor_establishment_id if body.contractor.contractor_establishment_id else 'no EPF code'}) "
                f"is not traceable at site. Dues are assessed against the principal employer under EPF Act s.8A, who may recover them "
                f"from the contractor by deduction from amounts payable or as a debt."
            )
        text = (f"{heading}{review} — {row['diary_no']}\nParties: EPFO and {name} ({row['establishment_id']}).\n"
                f"Period: {row['period_from']} to {row['period_to']}.\nNotice served by e-mail and speed post; "
                f"hearings: {', '.join(a['detail']['held_at'] for a in hearings)}.\nFindings and reasons: {body.reasoning}\n"
                f"{'Dues by account and month' if section != '14B' else 'Delayed remittances'}:\n{table}\n"
                f"Total: {rupees(total)}. The establishment is directed to pay within 15 days."
                f"{contractor_note}")
        late = now() > dt(row["order_due_at"])
        detail = {"kind": body.kind, "diary_no": row["diary_no"], "dues": lines, "total_paise": total, "reasoning": body.reasoning,
                  "ex_parte": body.ex_parte, "late": late, "order_due_at": iso(row["order_due_at"]), "text": text, "demand_id": demand_id}
        if body.contractor:
            detail["contractor_liability"] = body.contractor.model_dump(mode="json")
        for a in earlier:                                                                     # a 7A order replaced under review
            if section != "14B" and not a["detail"].get("superseded"):
                await session.execute(update(inquiry_actions).where(inquiry_actions.c.case_id == case_id,
                    inquiry_actions.c.kind == "ORDER").values(detail={**a["detail"], "superseded": True}))
        await action(session, case_id, "ORDER", actor.subject, detail)
        ordered = list(row.get("order_demand_ids") or []) if section == "14B" else []
        ordered.append(demand_id)
        kinds_due = set()
        if section == "14B":
            kinds_due = {k for k, v in DEMAND_KIND.items() if (await session.execute(select(demands.c.demand_id).where(
                demands.c.demand_id.in_(row["demand_ids"] or []), demands.c.kind == v))).first()}
            done = {a["detail"]["kind"] for a in earlier} | {body.kind}
        state = "PART_ORDERED" if section == "14B" and not kinds_due <= done else "ORDERED"
        await session.execute(update(inquiries).where(inquiries.c.case_id == case_id).values(
            state=state, ordered_at=now(), ex_parte=body.ex_parte, order_demand_ids=ordered))
        await session.execute(update(compliance_cases).where(compliance_cases.c.case_id == case_id).values(
            state="CLOSED" if state == "ORDERED" else "OPEN", amount_paise=total))
        await event(session, actor, "DemandRaised.v1", "demand", demand_id,
                    {"demand_id": demand_id, "establishment_id": row["establishment_id"], "demand_type": demand_type,
                     "amount_paise": total, "supersedes_demand_ids": supersedes, "working": working,
                     "rule_version": document["rule_version"]})
        await event(session, actor, "InquiryOrderPassed.v1", "compliance_case", case_id,
                    {"case_id": case_id, "diary_no": row["diary_no"], "establishment_id": row["establishment_id"],
                     "section": body.kind if section == "14B" else section, "ex_parte": body.ex_parte, "total_paise": total,
                     "demand_id": demand_id})
        await record(session, actor, "inquiry.order_passed", "inquiry", case_id, body.reasoning)
    return envelope(detail)
