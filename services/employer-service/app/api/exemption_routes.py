"""Synthetic trust audit and exemption proceeding workflow."""
import secrets
from datetime import UTC, date, date as Date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.routes import PRODUCER, db
from app.infra.tables import (establishment_exemptions as exemptions, establishments, exemption_proceedings as proceedings,
                              exemption_proceeding_steps as steps, office_staff, offices, trust_audits as audits)
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
TRUST = require_stakeholder("exempted.trust")
OFFICERS = require_stakeholder("fo.exemption", "fo.oic", "zo.acc", "ho.exemption")
CLOSED = {"RETURNED", "DROPPED", "CLOSED"}
FORMS = {"SURRENDER_REQUESTED": "SE-1", "SHOW_CAUSE_ISSUED": "CE-1", "PERMIT_UNEXEMPTED": "SE-5",
         "GAZETTE_NOTIFY": "Para 28(5)"}


def _id(prefix):
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def _date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


def _iso(value):
    return value.isoformat() if value is not None else None


async def _rules(session, day=None):
    return section(await rules_on(session, day or date.today()), "exempted_establishments")


async def _trust(session, actor):
    rows = (await session.execute(select(exemptions))).mappings().all()
    row = next((r for r in rows if any(u.get("subject") == actor.subject for u in r["trust_users"])), None)
    if not row:
        raise Problem(403, "/problems/forbidden", "No trust is assigned to this account")
    return row


async def _exemption(session, est_id):
    row = (await session.execute(select(exemptions).where(exemptions.c.establishment_id == est_id))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Exempted establishment not found")
    return row


async def _scope(session, actor, est_id):
    if actor.stakeholder == "ho.exemption":
        return
    posting = (await session.execute(select(office_staff.c.office_id).where(
        office_staff.c.subject == actor.subject, office_staff.c.stakeholder == actor.stakeholder))).scalar_one_or_none()
    office = (await session.execute(select(establishments.c.office_id).where(
        establishments.c.establishment_id == est_id))).scalar_one_or_none()
    if actor.stakeholder == "zo.acc" and office:
        office = (await session.execute(select(offices.c.zone_id).where(offices.c.office_id == office))).scalar_one_or_none()
    if not posting or not office or posting != office:
        raise Problem(403, "/problems/forbidden", "Establishment is outside your posting")


async def _event(session, kind, est_id, payload):
    await add_event(session, producer=PRODUCER, event_type=kind, aggregate_type="establishment",
                    aggregate_id=est_id, payload=payload)


async def _audit(session, actor, action, target, detail=None):
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                action=action, target_type="exemption_proceeding", target_id=target, detail=detail)


class AuditInput(BaseModel):
    financial_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    auditor_name: str = Field(min_length=1)
    auditor_registration: str = Field(min_length=1)
    opening_corpus_paise: int = Field(ge=0)
    contributions_paise: int = Field(ge=0)
    interest_credited_paise: int = Field(ge=0)
    claims_paid_paise: int = Field(ge=0)
    other_paise: int
    closing_corpus_paise: int = Field(ge=0)
    opinion: Literal["UNQUALIFIED", "QUALIFIED", "ADVERSE"]
    observations: str | None = None
    revised: bool = False


def _audit_view(row):
    view = dict(row)
    view["due_on"] = _iso(row["due_on"])
    view["filed_at"] = _iso(row["filed_at"])
    view["needs_attention"] = (["LATE"] if row["late_days"] else []) + (
        [row["opinion"]] if row["opinion"] != "UNQUALIFIED" else [])
    return view


@router.post("/api/v1/exempted/me/audits", status_code=201)
async def file_audit(body: AuditInput, actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)):
    today = date.today()
    async with session.begin():
        ex = await _trust(session, actor)
        year = int(body.financial_year[:4])
        if int(body.financial_year[-2:]) != (year + 1) % 100 or date(year + 1, 3, 31) >= today or year < _date(ex["effective_from"]).year - 1:
            raise Problem(422, "/problems/validation", "Financial year must have ended during this exemption")
        if date(year + 1, 3, 31) < _date(ex["effective_from"]):
            raise Problem(422, "/problems/validation", "Financial year precedes the exemption")
        if body.opinion != "UNQUALIFIED" and not (body.observations or "").strip():
            raise Problem(422, "/problems/validation", "Observations are required for this opinion")
        expected = body.opening_corpus_paise + body.contributions_paise + body.interest_credited_paise - body.claims_paid_paise + body.other_paise
        if body.closing_corpus_paise != expected:
            raise Problem(422, "/problems/validation", "Closing corpus must equal opening + contributions + interest - claims + other")
        prior = (await session.execute(select(audits).where(audits.c.establishment_id == ex["establishment_id"],
            audits.c.financial_year == body.financial_year, audits.c.status == "CURRENT"))).mappings().first()
        if prior and not body.revised:
            raise Problem(409, "/problems/conflict", "Audit already filed for this year; mark revised to supersede")
        if body.revised and not prior:
            raise Problem(409, "/problems/conflict", "No audit exists to revise")
        if prior:
            await session.execute(update(audits).where(audits.c.audit_id == prior["audit_id"]).values(status="SUPERSEDED"))
        month, day = map(int, (await _rules(session, today))["audit_due"].split("-"))
        due = date(year + 1, month, day)
        row = {**body.model_dump(exclude={"revised"}), "audit_id": _id("AUD"), "establishment_id": ex["establishment_id"],
               "status": "CURRENT", "due_on": due, "late_days": max(0, (today - due).days),
               "filed_at": datetime.now(UTC), "filed_by": actor.subject}
        try:
            async with session.begin_nested():
                await session.execute(insert(audits).values(**row))
        except IntegrityError:
            raise Problem(409, "/problems/conflict", "A current audit already exists for this year") from None
        await _event(session, "TrustAuditFiled.v1", ex["establishment_id"], {k: row[k] for k in
                     ("audit_id", "establishment_id", "financial_year", "opinion", "late_days")})
        await _audit(session, actor, "trust.audit_filed", row["audit_id"])
    return envelope(_audit_view(row))


@router.get("/api/v1/exempted/me/audits")
async def my_audits(actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)):
    ex = await _trust(session, actor)
    rows = (await session.execute(select(audits).where(audits.c.establishment_id == ex["establishment_id"])
                                  .order_by(audits.c.financial_year.desc(), audits.c.filed_at.desc()))).mappings().all()
    return envelope([_audit_view(r) for r in rows])


@router.get("/api/v1/office/exempted/{estId}/audits")
async def office_audits(estId: str, actor: Actor = Depends(require_stakeholder("fo.exemption", "ho.exemption")),
                        session: AsyncSession = Depends(db)):
    await _exemption(session, estId)
    await _scope(session, actor, estId)
    rows = (await session.execute(select(audits).where(audits.c.establishment_id == estId)
                                  .order_by(audits.c.financial_year.desc()))).mappings().all()
    return envelope([_audit_view(r) for r in rows])


async def _open(session, est_id):
    return (await session.execute(select(proceedings).where(proceedings.c.establishment_id == est_id,
        proceedings.c.open.is_(True)))).mappings().first()


async def _proceeding(session, proceeding_id):
    row = (await session.execute(select(proceedings).where(proceedings.c.proceeding_id == proceeding_id))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Proceeding not found")
    return row


def _next(row, history, days):
    stage, kind = row["stage"], row["kind"]
    if stage in CLOSED:
        return [], None, None
    if stage == "APPLIED":
        options, key = ([{"step": "RETURN_INCOMPLETE", "role": "fo.exemption"},
                         {"step": "PERMIT_UNEXEMPTED", "role": "fo.oic"}], "return_incomplete")
    elif stage == "SHOW_CAUSE_ISSUED":
        options, key = ([{"step": "REPLY", "role": "exempted.trust"},
                         {"step": "AGENDA_TO_ZO", "role": "fo.exemption"}], "show_cause_reply")
    elif stage == "REPLIED":
        options, key = ([{"step": "DROP", "role": "fo.exemption"},
                         {"step": "AGENDA_TO_ZO", "role": "fo.exemption"}], "ro_agenda")
    elif stage == "RELINQUISHED":
        options, key = ([{"step": "PERMIT_UNEXEMPTED", "role": "fo.oic"}], "past_accumulations")
    elif stage == "UNEXEMPTED_COMPLIANCE":
        options, key = ([{"step": "AGENDA_TO_ZO", "role": "fo.exemption"}], "ro_agenda")
    elif stage == "AT_ZO":
        options, key = ([{"step": "FORWARD_TO_HO", "role": "zo.acc"},
                         {"step": "REMAND", "role": "zo.acc"}], "zo_forward")
    elif stage == "AT_HO":
        options, key = ([{"step": "EEC_RECOMMENDED", "role": "ho.exemption"},
                         {"step": "EEC_RETURNED", "role": "ho.exemption"}], "ho_placement")
    elif stage == "EEC_RECOMMENDED":
        options, key = ([{"step": "CBT_RATIFIED", "role": "ho.exemption"}], "ho_placement")
    elif stage == "CBT_RATIFIED":
        options, key = ([{"step": "SENT_TO_GOVERNMENT", "role": "ho.exemption"}], "to_government")
    elif stage == "SENT_TO_GOVERNMENT":
        options, key = ([{"step": "GOVERNMENT_NOTIFIED", "role": "ho.exemption"}], "to_government")
    else:
        options, key = ([{"step": "GAZETTE_NOTIFY", "role": "fo.exemption"}], "to_government")
    last_day = _date(history[-1]["at"].date() if history else row["created_at"].date())
    for option in options:
        if stage == "APPLIED" and option["step"] == "PERMIT_UNEXEMPTED":
            due = _date(row["surrender_date"])
        elif stage == "SHOW_CAUSE_ISSUED":
            due = _date(row["reply_due"])
        else:
            due = last_day + timedelta(days=days[key])
        option["due_by"] = due.isoformat()
        option["overdue"] = date.today() > due
    return options, min(date.fromisoformat(o["due_by"]) for o in options), key


async def _view(session, row):
    history = (await session.execute(select(steps).where(steps.c.proceeding_id == row["proceeding_id"])
                                     .order_by(steps.c.at, steps.c.step_id))).mappings().all()
    days = (await _rules(session))["proceeding_days"]
    options, due, _ = _next(row, history, days)
    def history_item(h):
        form = {"AGENDA_TO_ZO": "SE-2" if row["kind"] == "SURRENDER" else "CE-2",
                "FORWARD_TO_HO": "SE-3" if row["kind"] == "SURRENDER" else "CE-4"}.get(h["step"], FORMS.get(h["step"]))
        return {**dict(h), "at": _iso(h["at"]), "form": form}

    return {"proceeding_id": row["proceeding_id"], "establishment_id": row["establishment_id"], "kind": row["kind"],
            "stage": row["stage"], "open": row["open"], "details": row["details"],
            "surrender_date": _iso(row["surrender_date"]), "reply_due": _iso(row["reply_due"]),
            "history": [history_item(h) for h in history],
            "what_is_due_next": options, "due_next": options, "due_by": _iso(due),
            "overdue": bool(due and date.today() > due)}


async def _create(session, actor, est_id, kind, stage, details, surrender_date=None, reply_due=None, step=None):
    ex = await _exemption(session, est_id)
    if ex["status"] != "ACTIVE":
        raise Problem(409, "/problems/conflict", "Exemption is no longer active")
    if await _open(session, est_id):
        raise Problem(409, "/problems/conflict", "An open proceeding already exists")
    now = datetime.now(UTC)
    row = {"proceeding_id": _id("EXPR"), "establishment_id": est_id, "kind": kind, "stage": stage,
           "open": True, "details": details, "surrender_date": surrender_date, "reply_due": reply_due, "created_at": now}
    try:
        async with session.begin_nested():
            await session.execute(insert(proceedings).values(**row))
    except IntegrityError:
        raise Problem(409, "/problems/conflict", "An open proceeding already exists") from None
    await session.execute(insert(steps).values(step_id=_id("EXST"), proceeding_id=row["proceeding_id"],
        step=step or stage, stage_after=stage, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
        note=details.get("note") or "Proceeding opened", reference=details.get("bot_resolution_ref"), at=now))
    await _event(session, "ExemptionProceedingAdvanced.v1", est_id,
                 {"proceeding_id": row["proceeding_id"], "establishment_id": est_id,
                  "kind": kind, "step": step or stage, "stage": stage})
    await _audit(session, actor, f"exemption.{(step or stage).lower()}", row["proceeding_id"])
    return row


class SurrenderInput(BaseModel):
    surrender_date: date
    bot_resolution_ref: str = Field(min_length=1)
    employer_undertaking: bool
    employees_consent: bool
    corpus_paise: int = Field(ge=0)
    members: int = Field(ge=0)


@router.post("/api/v1/exempted/me/surrender-requests", status_code=201)
async def surrender(body: SurrenderInput, actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)):
    async with session.begin():
        ex = await _trust(session, actor)
        est_id = ex["establishment_id"]
        require_step_up(actor, "surrender-exemption", est_id)
        days = (await _rules(session))["proceeding_days"]
        if body.surrender_date < date.today() + timedelta(days=days["surrender_notice"]):
            raise Problem(422, "/problems/validation", "Surrender date is earlier than the required notice period")
        if not body.employer_undertaking or not body.employees_consent:
            raise Problem(422, "/problems/validation", "Employer undertaking and employees consent are required")
        row = await _create(session, actor, est_id, "SURRENDER", "APPLIED", body.model_dump(mode="json"), body.surrender_date,
                            step="SURRENDER_REQUESTED")
        await _event(session, "ExemptionSurrenderRequested.v1", est_id,
                     {"proceeding_id": row["proceeding_id"], "establishment_id": est_id, "surrender_date": _iso(body.surrender_date)})
        view = await _view(session, row)
    return envelope(view)


class Ground(BaseModel):
    code: Literal["CLAIMS_LATE", "LOW_SCORE", "NO_RETURNS", "NO_RETURN", "PF_DUES_DEFAULT",
                  "INTEREST_BELOW_EPFO", "RECONCILIATION", "CONDITION_25", "CONDITION_29", "AUDIT_FINDINGS", "COMPLAINT"]
    text: str = Field(min_length=1)


class CancellationInput(BaseModel):
    grounds: list[Ground] = Field(min_length=1)
    flag_ids: list[str] = Field(default_factory=list)
    note: str = Field(min_length=1)


@router.post("/api/v1/office/exempted/{estId}/cancellation-proceedings", status_code=201)
async def cancellation(estId: str, body: CancellationInput, actor: Actor = Depends(require_stakeholder("fo.exemption")),
                       session: AsyncSession = Depends(db)):
    async with session.begin():
        await _scope(session, actor, estId)
        require_step_up(actor, "show-cause-exemption", estId)
        due = date.today() + timedelta(days=(await _rules(session))["proceeding_days"]["show_cause_reply"])
        row = await _create(session, actor, estId, "CANCELLATION", "SHOW_CAUSE_ISSUED", body.model_dump(), reply_due=due,
                            step="SHOW_CAUSE_ISSUED")
        await _event(session, "ExemptionShowCauseIssued.v1", estId,
                     {"proceeding_id": row["proceeding_id"], "establishment_id": estId, "reply_due": _iso(due)})
        view = await _view(session, row)
    return envelope(view)


async def _advance(session, actor, row, step, stage, note, reference=None, at_date=None, reply_due=None):
    now = datetime.now(UTC)
    values = {"stage": stage, "open": stage not in CLOSED}
    if reply_due is not None:
        values["reply_due"] = reply_due
    await session.execute(update(proceedings).where(proceedings.c.proceeding_id == row["proceeding_id"]).values(**values))
    await session.execute(insert(steps).values(step_id=_id("EXST"), proceeding_id=row["proceeding_id"], step=step,
        stage_after=stage, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, note=note,
        reference=reference, at=now))
    await _event(session, "ExemptionProceedingAdvanced.v1", row["establishment_id"],
                 {"proceeding_id": row["proceeding_id"], "establishment_id": row["establishment_id"],
                  "kind": row["kind"], "step": step, "stage": stage})
    await _audit(session, actor, f"exemption.{step.lower()}", row["proceeding_id"], note)
    if step in {"PERMIT_UNEXEMPTED", "GOVERNMENT_NOTIFIED"}:
        ex = await _exemption(session, row["establishment_id"])
        ended = _date(ex["ended_on"]) or at_date
        status = "UNEXEMPTED_COMPLIANCE" if step == "PERMIT_UNEXEMPTED" else (
            "SURRENDERED" if row["kind"] == "SURRENDER" else "CANCELLED")
        await session.execute(update(exemptions).where(exemptions.c.establishment_id == row["establishment_id"])
                              .values(status=status, ended_on=ended))
        await session.execute(update(establishments).where(establishments.c.establishment_id == row["establishment_id"])
                              .values(exemption_status=status))
        due = ended + timedelta(days=(await _rules(session))["proceeding_days"]["past_accumulations"])
        await _event(session, "ExemptionStatusChanged.v1", row["establishment_id"],
                     {"establishment_id": row["establishment_id"], "status": status, "ended_on": _iso(ended),
                      "past_accumulations_due": _iso(due)})
    return {**dict(row), **values}


class ReplyInput(BaseModel):
    reply: str = Field(min_length=1)
    relinquish: bool = False


@router.post("/api/v1/exempted/me/proceedings/{proceedingId}/replies")
async def reply(proceedingId: str, body: ReplyInput, actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)):
    async with session.begin():
        ex = await _trust(session, actor)
        row = await _proceeding(session, proceedingId)
        if row["establishment_id"] != ex["establishment_id"]:
            raise Problem(404, "/problems/not-found", "Proceeding not found")
        require_step_up(actor, "reply-show-cause", proceedingId)
        if row["kind"] != "CANCELLATION" or row["stage"] != "SHOW_CAUSE_ISSUED":
            raise Problem(409, "/problems/invalid-stage", f"Stage {row['stage']}; expected SHOW_CAUSE_ISSUED")
        row = await _advance(session, actor, row, "RELINQUISH" if body.relinquish else "REPLY",
                             "RELINQUISHED" if body.relinquish else "REPLIED", body.reply)
        view = await _view(session, row)
    return envelope(view)


@router.get("/api/v1/exempted/me/proceedings")
async def my_proceedings(actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)):
    ex = await _trust(session, actor)
    rows = (await session.execute(select(proceedings).where(proceedings.c.establishment_id == ex["establishment_id"])
                                  .order_by(proceedings.c.created_at.desc()))).mappings().all()
    return envelope([await _view(session, r) for r in rows])


@router.get("/api/v1/office/exempted/proceedings")
async def office_proceedings(stage: str | None = Query(default=None), actor: Actor = Depends(OFFICERS),
                             session: AsyncSession = Depends(db)):
    query = select(proceedings)
    if stage:
        query = query.where(proceedings.c.stage == stage)
    rows = (await session.execute(query.order_by(proceedings.c.created_at.desc()))).mappings().all()
    visible = []
    for row in rows:
        try:
            await _scope(session, actor, row["establishment_id"])
        except Problem:
            continue
        visible.append(await _view(session, row))
    return envelope(visible)


class StepInput(BaseModel):
    step: Literal["RETURN_INCOMPLETE", "DROP", "AGENDA_TO_ZO", "GAZETTE_NOTIFY", "PERMIT_UNEXEMPTED", "FORWARD_TO_HO", "REMAND"]
    note: str = Field(min_length=1)
    reference: str | None = None
    date: Date | None = None


def _stage_error(row, expected):
    raise Problem(409, "/problems/invalid-stage", f"Stage {row['stage']}; expected {expected}")


@router.post("/api/v1/office/exempted/proceedings/{proceedingId}/steps")
async def office_step(proceedingId: str, body: StepInput, actor: Actor = Depends(OFFICERS),
                      session: AsyncSession = Depends(db)):
    role = {"RETURN_INCOMPLETE": "fo.exemption", "DROP": "fo.exemption", "AGENDA_TO_ZO": "fo.exemption",
            "GAZETTE_NOTIFY": "fo.exemption", "PERMIT_UNEXEMPTED": "fo.oic", "FORWARD_TO_HO": "zo.acc", "REMAND": "zo.acc"}
    if actor.stakeholder != role[body.step]:
        raise Problem(403, "/problems/forbidden", f"{body.step} requires {role[body.step]}")
    async with session.begin():
        row = await _proceeding(session, proceedingId)
        await _scope(session, actor, row["establishment_id"])
        require_step_up(actor, "exemption-step", proceedingId)
        stage, kind = row["stage"], row["kind"]
        allowed = {"RETURN_INCOMPLETE": kind == "SURRENDER" and stage == "APPLIED",
                   "DROP": kind == "CANCELLATION" and stage == "REPLIED",
                   "AGENDA_TO_ZO": (kind == "SURRENDER" and stage == "UNEXEMPTED_COMPLIANCE") or
                       (kind == "CANCELLATION" and (stage in {"REPLIED", "UNEXEMPTED_COMPLIANCE"} or
                        (stage == "SHOW_CAUSE_ISSUED" and date.today() > _date(row["reply_due"])))),
                   "GAZETTE_NOTIFY": stage == "NOTIFIED", "PERMIT_UNEXEMPTED":
                       (kind == "SURRENDER" and stage == "APPLIED") or (kind == "CANCELLATION" and stage == "RELINQUISHED"),
                   "FORWARD_TO_HO": stage == "AT_ZO", "REMAND": stage == "AT_ZO"}
        if not allowed[body.step]:
            _stage_error(row, ", ".join(x for x, valid in allowed.items() if valid and role[x] == actor.stakeholder) or
                         "a different stage or step")
        if body.step == "PERMIT_UNEXEMPTED":
            effective = row["surrender_date"] if kind == "SURRENDER" else body.date or date.today()
            if kind == "SURRENDER" and body.date and body.date != _date(row["surrender_date"]):
                raise Problem(422, "/problems/validation", "Permit date must equal surrender date")
        else:
            effective = None
        if body.step == "REMAND":
            # back to the RO's stage before the latest agenda went up (also after HO returned it to the zone)
            history = (await session.execute(select(steps.c.step, steps.c.stage_after).where(steps.c.proceeding_id == proceedingId)
                                             .order_by(steps.c.at, steps.c.step_id))).all()
            sent = max(i for i, h in enumerate(history) if h.step == "AGENDA_TO_ZO")
            next_stage = history[sent - 1].stage_after if sent else ("UNEXEMPTED_COMPLIANCE" if kind == "SURRENDER" else "REPLIED")
        else:
            next_stage = {"RETURN_INCOMPLETE": "RETURNED", "DROP": "DROPPED", "AGENDA_TO_ZO": "AT_ZO",
                          "GAZETTE_NOTIFY": "CLOSED", "PERMIT_UNEXEMPTED": "UNEXEMPTED_COMPLIANCE",
                          "FORWARD_TO_HO": "AT_HO"}[body.step]
        row = await _advance(session, actor, row, body.step, next_stage, body.note, body.reference, effective)
        view = await _view(session, row)
    return envelope(view)


class DecisionInput(BaseModel):
    decision: Literal["EEC_RECOMMENDED", "EEC_RETURNED", "CBT_RATIFIED", "SENT_TO_GOVERNMENT", "GOVERNMENT_NOTIFIED"]
    note: str = Field(min_length=1)
    reference: str | None = None
    date: Date | None = None


@router.post("/api/v1/ho/exemptions/{estId}/decisions")
async def ho_decision(estId: str, body: DecisionInput, actor: Actor = Depends(require_stakeholder("ho.exemption")),
                      session: AsyncSession = Depends(db)):
    async with session.begin():
        await _exemption(session, estId)
        require_step_up(actor, "exemption-decision", estId)
        row = await _open(session, estId)
        if not row:
            raise Problem(404, "/problems/not-found", "No open proceeding")
        expected = {"EEC_RECOMMENDED": "AT_HO", "EEC_RETURNED": "AT_HO", "CBT_RATIFIED": "EEC_RECOMMENDED",
                    "SENT_TO_GOVERNMENT": "CBT_RATIFIED", "GOVERNMENT_NOTIFIED": "SENT_TO_GOVERNMENT"}[body.decision]
        if row["stage"] != expected:
            _stage_error(row, expected)
        if body.decision == "GOVERNMENT_NOTIFIED" and (not body.reference or not body.date):
            raise Problem(422, "/problems/validation", "Government notification number and effective date are required")
        stage = {"EEC_RETURNED": "AT_ZO", "GOVERNMENT_NOTIFIED": "NOTIFIED"}.get(body.decision, body.decision)
        row = await _advance(session, actor, row, body.decision, stage, body.note, body.reference, body.date)
        view = await _view(session, row)
    return envelope(view)
