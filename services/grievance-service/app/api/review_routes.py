"""P2.24 illustrative independent review after a member grievance is closed."""
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, entry, load, move, notify, posting, sla, view
from app.domain.review import DECISION_DAYS, check_request_window, deadline
from app.infra.tables import grievance_entries, grievance_reviews, grievances
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
MEMBER = require_stakeholder("member")
REVIEWER = require_stakeholder("zo.rpfc1")


class ReviewRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class ReviewDecision(BaseModel):
    outcome: Literal["UPHELD", "FRESH_DECISION"]
    reasons: str = Field(min_length=10, max_length=4000)


def review_view(row) -> dict:
    return {**{key: row[key] for key in ("grievance_id", "reason", "original_resolution", "state", "outcome", "reasons")},
            **{key: row[key].isoformat() if row[key] else None for key in
               ("requested_at", "request_deadline", "decision_due_at", "decided_at")}}


async def closure(session: AsyncSession, grievance_id: str):
    return (await session.execute(select(grievance_entries.c.at).where(
        grievance_entries.c.grievance_id == grievance_id, grievance_entries.c.state == "CLOSED")
        .order_by(grievance_entries.c.id.desc()).limit(1))).scalar_one_or_none()


async def reviewer_posting(session: AsyncSession, actor: Actor):
    staff = await posting(session, actor)
    if not staff or staff["stakeholder"] != "zo.rpfc1":
        raise Problem(403, "/problems/not-reviewer", "A zonal reviewer posting is required")
    return staff


def handling_office():
    # Independent review must cross the office that made the closed decision, including a zonal decision.
    return case((grievances.c.tier == "ZO", grievances.c.zone_id), else_=grievances.c.office_id)


@router.get("/api/v1/members/me/grievances/{grievance_id}/review")
async def member_review(grievance_id: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    g = await load(session, grievance_id, actor)
    row = (await session.execute(select(grievance_reviews).where(
        grievance_reviews.c.grievance_id == grievance_id))).mappings().first()
    if row:
        return envelope(review_view(row))
    closed_at = await closure(session, grievance_id)
    return envelope({"grievance_id": grievance_id, "state": "NOT_REQUESTED", "request_deadline":
                     deadline(closed_at).isoformat() if closed_at and g["state"] == "CLOSED" else None})


@router.post("/api/v1/members/me/grievances/{grievance_id}/reviews", status_code=201)
async def request_review(grievance_id: str, body: ReviewRequest, actor: Actor = Depends(MEMBER),
                         session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        existing = (await session.execute(select(grievance_reviews.c.grievance_id).where(
            grievance_reviews.c.grievance_id == grievance_id))).scalar_one_or_none()
        if existing:
            raise Problem(409, "/problems/review-already-requested", "A review was already requested")
        if g["state"] != "CLOSED":
            raise Problem(409, "/problems/invalid-state", "Only a closed grievance can be reviewed")
        closed_at = await closure(session, grievance_id)
        if not closed_at:
            raise Problem(409, "/problems/missing-closure", "The closure date is unavailable")
        now = datetime.now(UTC)
        request_deadline = check_request_window(closed_at, now)
        await session.execute(insert(grievance_reviews).values(
            grievance_id=grievance_id, reason=body.reason, original_resolution=g["resolution"],
            requested_at=now, request_deadline=request_deadline,
            decision_due_at=now + timedelta(days=DECISION_DAYS), state="PENDING"))
        await entry(session, g, "MESSAGE", "member", f"Independent review requested: {body.reason}")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="grievance.review_request", target_type="grievance", target_id=grievance_id)
        row = (await session.execute(select(grievance_reviews).where(
            grievance_reviews.c.grievance_id == grievance_id))).mappings().one()
    return envelope(review_view(row))


@router.get("/api/v1/office/grievance-reviews")
async def review_queue(actor: Actor = Depends(REVIEWER), session: AsyncSession = Depends(db)) -> dict:
    staff = await reviewer_posting(session, actor)
    rows = (await session.execute(select(grievance_reviews, grievances.c.subject_line,
                                       handling_office().label("office_id"))
        .join(grievances, grievance_reviews.c.grievance_id == grievances.c.grievance_id)
        .where(handling_office() != staff["office_id"])
        .order_by(grievance_reviews.c.decision_due_at))).mappings().all()
    return envelope([{**review_view(row), "subject": row["subject_line"], "office_id": row["office_id"]} for row in rows])


@router.post("/api/v1/office/grievance-reviews/{grievance_id}/decisions")
async def decide_review(grievance_id: str, body: ReviewDecision, actor: Actor = Depends(REVIEWER),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await reviewer_posting(session, actor)
        row = (await session.execute(select(grievance_reviews).where(
            grievance_reviews.c.grievance_id == grievance_id).with_for_update())).mappings().first()
        g = (await session.execute(select(grievances).where(grievances.c.grievance_id == grievance_id))).mappings().first()
        reviewing_office = g["zone_id"] if g and g["tier"] == "ZO" else g["office_id"] if g else None
        if not row or not g or reviewing_office == staff["office_id"]:
            raise Problem(404, "/problems/not-found", "Review not found")
        if row["state"] != "PENDING":
            raise Problem(409, "/problems/review-decided", "This review already has a decision")
        now = datetime.now(UTC)
        await session.execute(update(grievance_reviews).where(grievance_reviews.c.grievance_id == grievance_id).values(
            state="DECIDED", outcome=body.outcome, reasons=body.reasons,
            reviewer_subject=actor.subject, decided_at=now))
        if body.outcome == "FRESH_DECISION":
            # P2.24 illustrative remedy: return the case to its original handling tier for a new decision.
            g = await move(session, dict(g), "REOPEN_REQUESTED", actor.stakeholder,
                           f"Independent review directed a fresh decision: {body.reasons}",
                           resolution=None, resolved_at=None, sla_due_at=await sla(session, g["tier"]))
        else:
            await entry(session, dict(g), "MESSAGE", actor.stakeholder,
                        f"Independent review upheld the resolution: {body.reasons}")
        await notify(session, g, "GRIEVANCE_REPLY", actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="grievance.review_decision", target_type="grievance", target_id=grievance_id,
                    detail=body.outcome)
        decided = (await session.execute(select(grievance_reviews).where(
            grievance_reviews.c.grievance_id == grievance_id))).mappings().one()
    return envelope(review_view(decided))
