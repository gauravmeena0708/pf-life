"""Illustrative internal audit paras and data-principal requests."""
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.infra.oversight_tables import internal_paras, internal_reports, office_staff, offices, privacy_requests
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
PRODUCER = "audit-service"
INTERNAL_AUDITOR = require_stakeholder("zo.internal_audit")
DPO = require_stakeholder("ho.data_protection")
MEMBER = require_stakeholder("member")


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(value)


async def _posting(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if office is None:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


async def _office_in_zone(session: AsyncSession, office_id: str, zone_id: str) -> None:
    found = (await session.execute(select(offices.c.office_id).where(offices.c.office_id == office_id,
                                                                     offices.c.zone_id == zone_id))).first()
    if not found:
        raise Problem(404, "/problems/not-found", "No such office in your zone")


async def _due(session: AsyncSession, key: str) -> date:
    today = datetime.now(UTC).date()
    days = int(section(await rules_on(session, today), "oversight_periods")[key])
    return today + timedelta(days=days)


async def _audit(session: AsyncSession, actor: Actor, action: str, target_type: str, target_id: str) -> None:
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=action,
                target_type=target_type, target_id=target_id)


class ReportInput(BaseModel):
    office_id: str = Field(min_length=3, max_length=40)
    period_from: date
    period_to: date
    scope: str = Field(min_length=20, max_length=4000)


@router.post("/api/v1/audit/internal/reports", status_code=201)
async def create_report(body: ReportInput, actor: Actor = Depends(INTERNAL_AUDITOR), session: AsyncSession = Depends(db)) -> dict:
    if body.period_to < body.period_from:
        raise Problem(400, "/problems/validation", "Period end must be on or after period start")
    async with session.begin():
        zone = await _posting(session, actor)
        await _office_in_zone(session, body.office_id, zone)
        report_id = f"IAR-{secrets.token_hex(4).upper()}"
        await session.execute(insert(internal_reports).values(report_id=report_id, office_id=body.office_id, zone_id=zone,
                              period_from=body.period_from, period_to=body.period_to, scope=body.scope, created_by=actor.subject))
        await _audit(session, actor, "internal-report-created", "internal_report", report_id)
    return envelope({"report_id": report_id, "office_id": body.office_id,
                     "period": {"from": body.period_from.isoformat(), "to": body.period_to.isoformat()},
                     "scope": body.scope, "paras": []})


class ParaInput(BaseModel):
    category: Literal["CLAIMS", "ACCOUNTS", "COMPLIANCE", "PENSION", "ADMINISTRATION", "IT"]
    observation: str = Field(min_length=20, max_length=4000)
    amount_at_risk_paise: int = Field(ge=0)
    references: list[str] = Field(default_factory=list)
    recommendation: str = Field(min_length=1, max_length=4000)


def _para(row: Any) -> dict:
    item = {k: _iso(row[k]) for k in ("para_id", "report_id", "office_id", "zone_id", "category", "observation",
                                      "amount_at_risk_paise", "references", "recommendation", "reply_due", "state",
                                      "replies", "decisions", "raised_at")}
    item["overdue"] = row["state"] == "OPEN" and _day(row["reply_due"]) < datetime.now(UTC).date()
    return item


@router.post("/api/v1/audit/internal/reports/{reportId}/paras", status_code=201)
async def raise_para(reportId: str, body: ParaInput, actor: Actor = Depends(INTERNAL_AUDITOR),
                     session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        zone = await _posting(session, actor)
        report = (await session.execute(select(internal_reports).where(internal_reports.c.report_id == reportId,
                                                                  internal_reports.c.zone_id == zone))).mappings().first()
        if report is None:
            raise Problem(404, "/problems/not-found", "Report not found")
        await _office_in_zone(session, report["office_id"], zone)
        due = await _due(session, "para_reply_days")
        para_id = f"PAR-{secrets.token_hex(4).upper()}"
        await session.execute(insert(internal_paras).values(para_id=para_id, report_id=reportId, office_id=report["office_id"],
                              zone_id=zone, category=body.category, observation=body.observation,
                              amount_at_risk_paise=body.amount_at_risk_paise, references=body.references,
                              recommendation=body.recommendation, reply_due=due, state="OPEN", replies=[], decisions=[]))
        await add_event(session, producer=PRODUCER, event_type="AuditParaRaised.v1", aggregate_type="audit_para",
                        aggregate_id=para_id, correlation_id=actor.correlation_id,
                        payload={"para_id": para_id, "report_id": reportId, "office_id": report["office_id"],
                                 "category": body.category, "reply_due": due.isoformat()})
        await _audit(session, actor, "audit-para-raised", "audit_para", para_id)
        row = (await session.execute(select(internal_paras).where(internal_paras.c.para_id == para_id))).mappings().one()
    return envelope(_para(row))


@router.get("/api/v1/audit/internal/paras")
async def list_paras(state: str | None = Query(default=None),
                     actor: Actor = Depends(require_stakeholder("fo.oic", "zo.internal_audit", "ho.audit")),
                     session: AsyncSession = Depends(db)) -> dict:
    query = select(internal_paras)
    if actor.stakeholder != "ho.audit":
        posted = await _posting(session, actor)
        column = internal_paras.c.office_id if actor.stakeholder == "fo.oic" else internal_paras.c.zone_id
        query = query.where(column == posted)
    if state:
        query = query.where(internal_paras.c.state == state)
    rows = (await session.execute(query.order_by(internal_paras.c.raised_at.desc()))).mappings().all()
    return envelope([_para(row) for row in rows])


class ParaReplyInput(BaseModel):
    reply: str = Field(min_length=20, max_length=4000)
    action_taken: str = Field(min_length=1, max_length=4000)
    request_drop: bool


@router.post("/api/v1/audit/internal/paras/{paraId}/replies")
async def reply_para(paraId: str, body: ParaReplyInput, actor: Actor = Depends(require_stakeholder("fo.oic")),
                     session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        posted = await _posting(session, actor)
        row = (await session.execute(select(internal_paras).where(internal_paras.c.para_id == paraId,
                                                                 internal_paras.c.office_id == posted).with_for_update())).mappings().first()
        if row is None:
            raise Problem(404, "/problems/not-found", "Para not found")
        if row["state"] != "OPEN":
            raise Problem(409, "/problems/invalid-state", "Para is not open for a reply")
        today = datetime.now(UTC).date()
        record = {"reply": body.reply, "action_taken": body.action_taken, "request_drop": body.request_drop,
                  "by": actor.subject, "at": datetime.now(UTC).isoformat(), "late": today > _day(row["reply_due"])}
        await session.execute(update(internal_paras).where(internal_paras.c.para_id == paraId)
                              .values(state="REPLIED", replies=[*(row["replies"] or []), record]))
        await _audit(session, actor, "audit-para-replied", "audit_para", paraId)
        updated = (await session.execute(select(internal_paras).where(internal_paras.c.para_id == paraId))).mappings().one()
    return envelope(_para(updated))


class ParaDecisionInput(BaseModel):
    decision: Literal["DROP", "KEEP"]
    note: str = Field(min_length=1, max_length=4000)


@router.post("/api/v1/audit/internal/paras/{paraId}/decisions")
async def decide_para(paraId: str, body: ParaDecisionInput, actor: Actor = Depends(require_stakeholder("ho.audit")),
                      session: AsyncSession = Depends(db)) -> dict:
    require_step_up(actor, "decide-audit-para", paraId)
    async with session.begin():
        row = (await session.execute(select(internal_paras).where(internal_paras.c.para_id == paraId)
                                     .with_for_update())).mappings().first()
        if row is None:
            raise Problem(404, "/problems/not-found", "Para not found")
        if row["state"] != "REPLIED":
            raise Problem(409, "/problems/invalid-state", "Para requires a reply before decision")
        state = "DROPPED" if body.decision == "DROP" else "OPEN"
        due = row["reply_due"] if state == "DROPPED" else await _due(session, "para_reply_days")
        decisions = [*(row["decisions"] or []), {"decision": state if state == "DROPPED" else "KEPT",
                                                    "note": body.note, "by": actor.subject, "at": datetime.now(UTC).isoformat()}]
        await session.execute(update(internal_paras).where(internal_paras.c.para_id == paraId)
                              .values(state=state, reply_due=due, decisions=decisions))
        await add_event(session, producer=PRODUCER, event_type="AuditParaDecided.v1", aggregate_type="audit_para",
                        aggregate_id=paraId, correlation_id=actor.correlation_id,
                        payload={"para_id": paraId, "office_id": row["office_id"], "decision": "DROPPED" if state == "DROPPED" else "KEPT"})
        await _audit(session, actor, "audit-para-decided", "audit_para", paraId)
        updated = (await session.execute(select(internal_paras).where(internal_paras.c.para_id == paraId))).mappings().one()
    return envelope(_para(updated))


class PrivacyInput(BaseModel):
    kind: Literal["ACCESS", "CORRECTION", "ERASURE", "GRIEVANCE", "NOMINATE"]
    details: str = Field(min_length=10, max_length=4000)


def _member_request(row: Any) -> dict:
    return {k: _iso(row[k]) for k in ("request_id", "kind", "details", "state", "due_on", "answer", "legal_basis", "created_at", "decided_at")}


@router.post("/api/v1/members/me/privacy-requests", status_code=201)
async def create_privacy_request(body: PrivacyInput, actor: Actor = Depends(MEMBER),
                                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        due = await _due(session, "privacy_response_days")
        request_id = f"DPR-{secrets.token_hex(4).upper()}"
        await session.execute(insert(privacy_requests).values(request_id=request_id, member_subject=actor.subject,
                              kind=body.kind, details=body.details, state="OPEN", due_on=due))
        await _audit(session, actor, "privacy-request-created", "privacy_request", request_id)
    return envelope({"request_id": request_id, "kind": body.kind, "state": "OPEN", "due_on": due.isoformat(),
                     "next_step": "The data protection office will review and respond to your request."})


@router.get("/api/v1/members/me/privacy-requests")
async def my_privacy_requests(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(privacy_requests).where(privacy_requests.c.member_subject == actor.subject)
                                  .order_by(privacy_requests.c.created_at.desc()))).mappings().all()
    return envelope([_member_request(row) for row in rows])


@router.get("/api/v1/privacy/requests")
async def privacy_queue(state: str | None = Query(default=None), actor: Actor = Depends(DPO),
                        session: AsyncSession = Depends(db)) -> dict:
    query = select(privacy_requests)
    if state:
        query = query.where(privacy_requests.c.state == state)
    rows = (await session.execute(query.order_by(privacy_requests.c.created_at.desc()))).mappings().all()
    today = datetime.now(UTC).date()
    return envelope([{"request_id": row["request_id"], "kind": row["kind"], "state": row["state"],
                      "due_on": _iso(row["due_on"]), "overdue": row["state"] == "OPEN" and _day(row["due_on"]) < today,
                      "member_subject": row["member_subject"], "member_reference": "****" + row["member_subject"][-4:]}
                     for row in rows])


class PrivacyDecisionInput(BaseModel):
    decision: Literal["FULFILLED", "PARTLY_FULFILLED", "REJECTED"]
    answer: str = Field(min_length=20, max_length=4000)
    legal_basis: str | None = Field(default=None, max_length=4000)


@router.post("/api/v1/privacy/requests/{requestId}/decisions")
async def decide_privacy_request(requestId: str, body: PrivacyDecisionInput, actor: Actor = Depends(DPO),
                                 session: AsyncSession = Depends(db)) -> dict:
    require_step_up(actor, "decide-privacy-request", requestId)
    if body.decision != "FULFILLED" and not (body.legal_basis or "").strip():
        raise Problem(400, "/problems/validation", "Legal basis is required for this decision")
    async with session.begin():
        row = (await session.execute(select(privacy_requests).where(privacy_requests.c.request_id == requestId)
                                     .with_for_update())).mappings().first()
        if row is None:
            raise Problem(404, "/problems/not-found", "Privacy request not found")
        if row["state"] != "OPEN":
            raise Problem(409, "/problems/invalid-state", "Privacy request has already been decided")
        await session.execute(update(privacy_requests).where(privacy_requests.c.request_id == requestId)
                              .values(state=body.decision, answer=body.answer, legal_basis=body.legal_basis,
                                      decided_at=datetime.now(UTC)))
        await add_event(session, producer=PRODUCER, event_type="PrivacyRequestDecided.v1", aggregate_type="privacy_request",
                        aggregate_id=requestId, correlation_id=actor.correlation_id,
                        payload={"request_id": requestId, "kind": row["kind"], "decision": body.decision})
        await _audit(session, actor, "privacy-request-decided", "privacy_request", requestId)
        updated = (await session.execute(select(privacy_requests).where(privacy_requests.c.request_id == requestId))).mappings().one()
    return envelope(_member_request(updated))
