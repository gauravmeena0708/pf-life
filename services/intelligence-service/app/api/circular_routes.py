"""Phase 2, slice 8d: circulars and notifications. HO Public Relations publishes one (a number, a title, a summary
and the text); publishing the same number again makes a new version and supersedes the last, which stays readable.
Anyone reads the current ones without a login. The seeded circulars are synthetic, not EPFO's."""
import hashlib
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import circulars
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "intelligence-service"
CATEGORIES = ("CLAIMS", "PENSION", "COMPLIANCE", "MEMBER_SERVICES", "GENERAL")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _view(r: Any, text: bool = True) -> dict[str, Any]:
    out = {"circular_id": r["circular_id"], "number": r["number"], "version": r["version"], "title": r["title"],
           "category": r["category"], "issued_on": r["issued_on"].isoformat(), "summary": r["summary"], "state": r["state"],
           "sha256": r["sha256"], "published_at": r["published_at"].isoformat() if r["published_at"] else None}
    return {**out, "body": r["body"]} if text else out


@router.get("/api/v1/public/circulars")
async def public_circulars(category: str | None = Query(default=None, max_length=30), q: str | None = Query(default=None, max_length=100),
                           number: str | None = Query(default=None, max_length=60),
                           actor: Actor = Depends(require_stakeholder("public", "ho.publicity")),
                           session: AsyncSession = Depends(db)) -> dict:
    query = select(circulars).order_by(circulars.c.issued_on.desc(), circulars.c.number, circulars.c.version.desc())
    if number:                                         # one circular's versions, newest first
        query = query.where(circulars.c.number == number)
    else:
        query = query.where(circulars.c.state == "CURRENT")
    if category:
        query = query.where(circulars.c.category == category)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(func.lower(circulars.c.title).like(like) | func.lower(circulars.c.summary).like(like))
    rows = (await session.execute(query.limit(100))).mappings().all()
    return envelope({"circulars": [_view(r) for r in rows], "categories": list(CATEGORIES),
                     "note": "Synthetic circulars for the demonstration; not EPFO's."})


class CircularInput(BaseModel):
    number: str = Field(min_length=3, max_length=60)
    title: str = Field(min_length=5, max_length=200)
    category: str
    issued_on: date
    summary: str = Field(min_length=10, max_length=1000)
    body: str = Field(min_length=20, max_length=20000)


async def publish(session: AsyncSession, body: CircularInput, by: str) -> dict[str, Any]:
    if body.category not in CATEGORIES:
        raise Problem(422, "/problems/validation", "Unknown category", "Choose one of: " + ", ".join(CATEGORIES))
    if body.issued_on > date.today():
        raise Problem(422, "/problems/validation", "A circular cannot be dated in the future")
    number = body.number.strip()
    latest = (await session.execute(select(circulars).where(circulars.c.number == number)
                                    .order_by(circulars.c.version.desc()).limit(1))).mappings().first()
    digest = hashlib.sha256(f"{body.title}\n{body.summary}\n{body.body}".encode()).hexdigest()
    if latest and latest["sha256"] == digest:
        raise Problem(409, "/problems/unchanged", "This version is already published", f"Circular {number} version {latest['version']}.")
    if latest:
        await session.execute(update(circulars).where(circulars.c.number == number).values(state="SUPERSEDED"))
    circular_id = f"CIR-{secrets.token_hex(4).upper()}"
    await session.execute(insert(circulars).values(
        circular_id=circular_id, number=number, version=(latest["version"] + 1) if latest else 1, title=body.title.strip(),
        category=body.category, issued_on=body.issued_on, summary=body.summary.strip(), body=body.body.strip(), state="CURRENT",
        sha256=digest, published_by=by))
    return dict((await session.execute(select(circulars).where(circulars.c.circular_id == circular_id))).mappings().one())


@router.post("/api/v1/ho/circulars", status_code=201)
async def publish_circular(body: CircularInput, actor: Actor = Depends(require_stakeholder("ho.publicity")),
                           session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        row = await publish(session, body, actor.subject)
        await add_event(session, producer=PRODUCER, event_type="CircularPublished.v1", aggregate_type="circular",
                        aggregate_id=row["circular_id"], correlation_id=actor.correlation_id, payload={
                            "circular_id": row["circular_id"], "number": row["number"], "version": row["version"],
                            "category": row["category"], "issued_on": row["issued_on"].isoformat(), "sha256": row["sha256"]})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="circular.publish",
                    target_type="circular", target_id=row["circular_id"], detail=f"{row['number']} v{row['version']}")
    return envelope(_view(row))
