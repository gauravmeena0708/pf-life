"""Phase 2, slice 8e: the NDC Issue Tracker (FIA SOP, simplified). An officer raises a request with the order behind it —
freeze or de-freeze a member's account, or show a notice when the member next logs in — and the IS Division executes
or rejects it. An executed request is carried out by member-service (IssueTrackerExecuted.v1), which owns the
account state and publishes AccountFrozen.v1 / AccountDefrozen.v1 as for any freeze. Illustrative."""
import base64
import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.infra.tables import issue_tracker_requests
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "platform-service"
RAISERS = ("fo.oic", "fo.apfc", "zo.rpfc1", "ho.vigilance", "ho.security")
KINDS = ("FREEZE_MEMBER", "DEFREEZE_MEMBER", "LOGIN_NOTICE")


def _view(r: Any) -> dict[str, Any]:
    return {k: (r[k].isoformat() if hasattr(r[k], "isoformat") else r[k])
            for k in ("request_id", "kind", "target_uan", "order_ref", "order_document", "reason", "notice", "state",
                      "raised_role", "raised_at", "executed_at", "execution_note")}


class IssueInput(BaseModel):
    kind: str
    target_uan: str = Field(pattern=r"^[0-9]{12}$")
    order_ref: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=10, max_length=2000)
    notice: str | None = Field(default=None, max_length=500)
    order_filename: str | None = Field(default=None, max_length=200)
    order_base64: str | None = Field(default=None, max_length=3_000_000)


@router.post("/api/v1/ndc/issue-tracker/requests", status_code=201)
async def raise_request(body: IssueInput, actor: Actor = Depends(require_stakeholder(*RAISERS)), session: AsyncSession = Depends(db)) -> dict:
    if body.kind not in KINDS:
        raise Problem(422, "/problems/validation", "Unknown request kind", "Choose one of: " + ", ".join(KINDS))
    if body.kind == "LOGIN_NOTICE" and not (body.notice or "").strip():
        raise Problem(422, "/problems/validation", "Write the notice the member will see")
    document = None
    if body.order_base64:
        try:
            content = base64.b64decode(body.order_base64, validate=True)
        except ValueError:
            raise Problem(422, "/problems/validation", "The order could not be read") from None
        if not content.startswith(b"%PDF") or len(content) > 2 * 1024 * 1024:
            raise Problem(422, "/problems/validation", "Attach the order as a PDF of at most 2 MB")
        document = {"filename": body.order_filename or "order.pdf", "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    async with session.begin():
        if (await session.execute(select(issue_tracker_requests.c.request_id).where(
                issue_tracker_requests.c.target_uan == body.target_uan, issue_tracker_requests.c.kind == body.kind,
                issue_tracker_requests.c.state == "RAISED"))).first():
            raise Problem(409, "/problems/request-open", "The same request for this UAN is already waiting for the IS Division")
        request_id = f"ITR-{secrets.token_hex(4).upper()}"
        await session.execute(insert(issue_tracker_requests).values(
            request_id=request_id, kind=body.kind, target_uan=body.target_uan, order_ref=body.order_ref, order_document=document,
            reason=body.reason, notice=(body.notice or "").strip() or None, state="RAISED", raised_by=actor.subject,
            raised_role=actor.stakeholder))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="issue_tracker.raise",
                    target_type="member", target_id=body.target_uan, detail=f"{request_id} {body.kind} {body.order_ref}")
        row = (await session.execute(select(issue_tracker_requests).where(issue_tracker_requests.c.request_id == request_id))).mappings().one()
    return envelope(_view(row))


@router.get("/api/v1/ndc/issue-tracker/requests")
async def list_requests(actor: Actor = Depends(require_stakeholder("ho.is", *RAISERS)), session: AsyncSession = Depends(db)) -> dict:
    query = select(issue_tracker_requests).order_by(issue_tracker_requests.c.raised_at.desc()).limit(200)
    if actor.stakeholder != "ho.is":                         # an officer sees the requests they raised
        query = query.where(issue_tracker_requests.c.raised_by == actor.subject)
    return envelope([_view(r) for r in (await session.execute(query)).mappings().all()])


class Execution(BaseModel):
    decision: str = Field(pattern="^(EXECUTE|REJECT)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/ndc/issue-tracker/requests/{requestId}/executions")
async def execute(requestId: str, body: Execution, actor: Actor = Depends(require_stakeholder("ho.is")),
                  session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        row = (await session.execute(select(issue_tracker_requests).where(issue_tracker_requests.c.request_id == requestId))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Request not found")
        if row["state"] != "RAISED":
            raise Problem(409, "/problems/invalid-state", "This request is already dealt with", f"Status: {row['state']}.")
        require_step_up(actor, "execute-issue-tracker", requestId)
        state = "EXECUTED" if body.decision == "EXECUTE" else "REJECTED"
        await session.execute(update(issue_tracker_requests).where(issue_tracker_requests.c.request_id == requestId).values(
            state=state, executed_by=actor.subject, executed_at=datetime.now(UTC), execution_note=body.note))
        if state == "EXECUTED":
            await add_event(session, producer=PRODUCER, event_type="IssueTrackerExecuted.v1", aggregate_type="issue_tracker_request",
                            aggregate_id=requestId, correlation_id=actor.correlation_id, payload={
                                "request_id": requestId, "kind": row["kind"], "target_uan": row["target_uan"],
                                "order_ref": row["order_ref"], "notice": row["notice"] or ""})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"issue_tracker.{state.lower()}",
                    target_type="member", target_id=row["target_uan"], detail=f"{requestId}: {body.note}")
        row = (await session.execute(select(issue_tracker_requests).where(issue_tracker_requests.c.request_id == requestId))).mappings().one()
    return envelope(_view(row))
