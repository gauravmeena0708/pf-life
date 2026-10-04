"""P2.21b: the civil registry's death feed (mock) and the member's documents in DigiLocker (mock). See
app/domain/life_events.py for the rules."""
import hmac
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.life_events import crs_signature, document_view, queue_document, record_registered_death
from app.infra.db import sessions
from app.infra.tables import death_registrations, digilocker_documents, employments, members, office_staff
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
MEMBER = require_stakeholder("member")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class DeathRegistration(BaseModel):
    registration_no: str = Field(min_length=5, max_length=60)
    name: str = Field(min_length=2, max_length=200)
    date_of_birth: date
    date_of_death: date
    aadhaar_ref: str | None = Field(default=None, max_length=64)
    signature: str = Field(min_length=64, max_length=64)


def _registration(r: dict) -> dict:
    return {"registration_no": r["registration_no"], "name": r["name"], "date_of_death": r["date_of_death"].isoformat(),
            "matched_uan": r["matched_uan"], "matched_by": r["matched_by"], "outcome": r["outcome"], "exits_marked": r["exits_marked"]}


@router.post("/api/v1/integrations/crs/death-registrations", status_code=201)
async def death_registration(body: DeathRegistration, response: Response, actor: Actor = Depends(require_stakeholder("ext.crs")),
                             session: AsyncSession = Depends(db)) -> dict:
    """Signed: HMAC-SHA256 of registration_no|date_of_death|name. A repeated registration returns 200 with the first outcome."""
    if not hmac.compare_digest(crs_signature(body.registration_no, body.date_of_death.isoformat(), body.name), body.signature):
        raise Problem(401, "/problems/bad-signature", "The callback signature does not match")
    if body.date_of_death > date.today() or body.date_of_death < body.date_of_birth:
        raise Problem(422, "/problems/validation", "The date of death is not possible")
    async with session.begin():
        result = await record_registered_death(session, registration_no=body.registration_no, name=body.name,
                                               date_of_birth=body.date_of_birth, date_of_death=body.date_of_death,
                                               aadhaar_ref=body.aadhaar_ref, correlation_id=actor.correlation_id)
        if not result["repeated"]:
            await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="death.registered",
                        target_type="member", target_id=result["matched_uan"] or "-", detail=f"{body.registration_no} {result['outcome']}")
    if result["repeated"]:
        response.status_code = 200
    return envelope(_registration(result))


@router.get("/api/v1/office/civil-registry/deaths")
async def office_deaths(actor: Actor = Depends(require_stakeholder("fo.pro", "fo.da_pension")), session: AsyncSession = Depends(db)) -> dict:
    """Deaths the registry reported: those of members of this office, and those that matched nobody or more than one person."""
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    mine = select(members.c.uan).join(employments, employments.c.member_id == members.c.member_id).where(employments.c.office_id == office)
    rows = (await session.execute(select(death_registrations).where(or_(death_registrations.c.matched_uan.in_(mine),
                                                                        death_registrations.c.matched_uan.is_(None)))
                                  .order_by(death_registrations.c.received_at.desc()).limit(200))).mappings().all()
    return envelope([{**_registration(dict(r)), "received_at": r["received_at"].isoformat()} for r in rows])


async def _me(session: AsyncSession, actor: Actor) -> dict:
    me = (await session.execute(select(members).where(members.c.subject == actor.subject))).mappings().first()
    if not me:
        raise Problem(404, "/problems/not-found", "Member not found")
    return dict(me)


@router.get("/api/v1/members/me/digilocker-documents")
async def my_documents(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    me = await _me(session, actor)
    rows = (await session.execute(select(digilocker_documents).where(digilocker_documents.c.uan == me["uan"])
                                  .order_by(digilocker_documents.c.created_at))).mappings().all()
    return envelope([document_view(r) for r in rows])


class DocumentRequest(BaseModel):
    doc_type: str = Field(pattern="^UAN_CARD$")


@router.post("/api/v1/members/me/digilocker-documents", status_code=202)
async def request_document(body: DocumentRequest, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """The e-UAN card for a member whose UAN predates the push (or whose push failed: it is queued again)."""
    async with session.begin():
        me = await _me(session, actor)
        row = await queue_document(session, me["uan"], body.doc_type, me["uan"])
        if row["state"] == "FAILED":
            await session.execute(update(digilocker_documents).where(digilocker_documents.c.doc_id == row["doc_id"]).values(
                state="QUEUED", attempts=0, last_error=None, next_attempt_at=datetime.now(UTC)))
        row = (await session.execute(select(digilocker_documents).where(digilocker_documents.c.doc_id == row["doc_id"]))).mappings().one()
    return envelope(document_view(row))
