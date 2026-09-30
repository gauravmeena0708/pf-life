"""Phase 2, slice 8d: grievances from people without a login (a pensioner, an employer, anyone), their status by
registration number, the complainant's reminders and closing feedback, and an office transferring a grievance to
another office. Illustrative, EPFiGMS-like:

* without a login the contact is proved with a one-time code sent to the mobile (MOCK: any six digits except
  000000); the gateway also asks for its one-use public challenge and limits the rate. Only a hash of the mobile
  and its last four digits are kept, and a status lookup shows the progress, never the grievance text;
* a reminder goes to the office at most once a day while the grievance is open;
* feedback closes a resolved grievance when the complainant is satisfied; otherwise it stays open to a reopen;
* a regional office may transfer a grievance it holds to another office (GrievanceTransferred.v1), which then
  owns it; the first office no longer sees it."""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import MEMBER, db, entry, load, move, posting, require_handler, settings, sla, view
from app.infra.tables import grievance_entries, grievances, offices
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "grievance-service"
PUBLIC = require_stakeholder("public")
PRO = require_stakeholder("fo.pro")
TYPES = ("PENSIONER", "EMPLOYER", "MEMBER", "OTHER")
OPEN = ("REGISTERED", "ROUTED", "IN_PROGRESS", "ESCALATED", "REOPEN_REQUESTED")


def mobile_hash(mobile: str) -> str:
    return hashlib.sha256(f"epfo-demo-grievance|{mobile}".encode()).hexdigest()


def check_otp(otp: str) -> None:
    if otp == "000000":
        raise Problem(422, "/problems/otp-invalid", "The one-time code is not correct",
                      "Enter the code sent to your mobile (mock: any six digits except 000000).")


class PublicGrievance(BaseModel):
    challenge_id: str                                      # checked by the gateway
    answer: int
    name: str = Field(min_length=2, max_length=120)
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    otp: str = Field(pattern=r"^[0-9]{6}$")
    complainant_type: str
    category: str
    subject: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    reference: str | None = Field(default=None, max_length=40)      # a UAN, PPO number, establishment ID or claim ID


@router.post("/api/v1/public/grievances", status_code=201)
async def register_public(body: PublicGrievance, actor: Actor = Depends(PUBLIC), session: AsyncSession = Depends(db)) -> dict:
    check_otp(body.otp)
    if body.complainant_type not in TYPES:
        raise Problem(422, "/problems/validation", "Unknown complainant type", "Choose one of: " + ", ".join(TYPES))
    async with session.begin():
        categories = (await settings(session))["categories"]
        if body.category not in categories:
            raise Problem(422, "/problems/validation", "Unknown category", "Choose one of: " + ", ".join(categories))
        home = (await session.execute(select(offices).order_by(offices.c.office_id).limit(1))).mappings().one()   # the demo's first office
        gid = f"GRV-{secrets.token_hex(4).upper()}"
        await session.execute(insert(grievances).values(
            grievance_id=gid, complainant_subject=f"PUBLIC:{gid}", category=body.category, subject_line=body.subject,
            description=body.description, linked_claim_id=body.reference if (body.reference or "").startswith("CLM-") else None,
            office_id=home["office_id"], zone_id=home["zone_id"], tier="RO", state="REGISTERED", version=1,
            sla_due_at=await sla(session, "RO"), source="PUBLIC", complainant_type=body.complainant_type,
            public_name=body.name.strip(), mobile_hash=mobile_hash(body.mobile), mobile_last4=body.mobile[-4:]))
        g = dict((await session.execute(select(grievances).where(grievances.c.grievance_id == gid))).mappings().one())
        await entry(session, g, "STATUS", "complainant", "Grievance registered without a login (mobile verified by one-time code).",
                    state="REGISTERED")
        if body.reference and not (body.reference or "").startswith("CLM-"):
            await entry(session, g, "MESSAGE", "complainant", f"Reference given: {body.reference}")
        await add_event(session, producer=PRODUCER, event_type="GrievanceRegistered.v1", aggregate_type="grievance",
                        aggregate_id=gid, correlation_id=actor.correlation_id, payload={
                            "grievance_id": gid, "category": body.category, "office_id": home["office_id"],
                            "linked_claim_id": g["linked_claim_id"] or ""})
        g = await move(session, g, "ROUTED", "system", f"Sent to the regional office {home['office_id']}.")
        await audit(session, actor_subject="anonymous", actor_stakeholder="public", action="grievance.register_public",
                    target_type="grievance", target_id=gid, detail=f"{body.complainant_type} {body.category}")
    return envelope({"registration_no": gid, "state": g["state"], "office_id": g["office_id"],
                     "sla_due_at": g["sla_due_at"].isoformat(),
                     "note": f"Keep the registration number. Check the status with it and the mobile ending {body.mobile[-4:]}."})


class StatusLookup(BaseModel):
    challenge_id: str
    answer: int
    registration_no: str = Field(pattern=r"^GRV-[0-9A-F]{8}$")
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    otp: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/api/v1/public/grievances/status-lookups")
async def status_lookup(body: StatusLookup, actor: Actor = Depends(PUBLIC), session: AsyncSession = Depends(db)) -> dict:
    check_otp(body.otp)
    g = (await session.execute(select(grievances).where(grievances.c.grievance_id == body.registration_no))).mappings().first()
    if not g or g["mobile_hash"] != mobile_hash(body.mobile):
        raise Problem(404, "/problems/not-found", "No grievance matches this registration number and mobile")
    steps = (await session.execute(select(grievance_entries.c.at, grievance_entries.c.state).where(
        grievance_entries.c.grievance_id == g["grievance_id"], grievance_entries.c.kind == "STATUS")
        .order_by(grievance_entries.c.id))).mappings().all()
    return envelope({"registration_no": g["grievance_id"], "state": g["state"], "tier": g["tier"], "office_id": g["office_id"],
                     "sla_due_at": g["sla_due_at"].isoformat() if g["sla_due_at"] else None,
                     "resolved_at": g["resolved_at"].isoformat() if g["resolved_at"] else None,
                     "resolution": g["resolution"],
                     "steps": [{"at": s["at"].isoformat() if s["at"] else None, "state": s["state"]} for s in steps]})


class Reminder(BaseModel):
    note: str = Field(default="", max_length=500)


@router.post("/api/v1/grievances/{grievanceId}/reminders", status_code=201)
async def remind(grievanceId: str, body: Reminder, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievanceId, actor, lock=True)
        if g["state"] not in OPEN:
            raise Problem(409, "/problems/invalid-state", "Only an open grievance can be followed up", f"Current status: {g['state']}.")
        now = datetime.now(UTC)
        last = g["last_reminded_at"]
        if last and (last if last.tzinfo else last.replace(tzinfo=UTC)) > now - timedelta(days=1):
            raise Problem(429, "/problems/reminder-too-soon", "You sent a reminder in the last 24 hours",
                          "The office has it; you can send another tomorrow.")
        await session.execute(update(grievances).where(grievances.c.grievance_id == grievanceId).values(
            reminders=g["reminders"] + 1, last_reminded_at=now))
        due = g["sla_due_at"] if g["sla_due_at"].tzinfo else g["sla_due_at"].replace(tzinfo=UTC)
        await entry(session, g, "MESSAGE", "member", f"Reminder {g['reminders'] + 1} from the complainant"
                    + (" (the service level has passed)" if now > due else "") + (f": {body.note}" if body.note.strip() else "."))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.reminder",
                    target_type="grievance", target_id=grievanceId)
        g = dict((await session.execute(select(grievances).where(grievances.c.grievance_id == grievanceId))).mappings().one())
        result = {**await view(session, g), "reminders": g["reminders"], "overdue": now > due}
    return envelope(result)


class Feedback(BaseModel):
    rating: int = Field(ge=1, le=5)
    satisfied: bool
    comment: str = Field(default="", max_length=1000)


@router.post("/api/v1/grievances/{grievanceId}/feedback", status_code=201)
async def feedback(grievanceId: str, body: Feedback, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievanceId, actor, lock=True)
        if g["state"] != "RESOLVED":
            raise Problem(409, "/problems/invalid-state", "Feedback is given on a resolved grievance", f"Current status: {g['state']}.")
        if g["feedback"]:
            raise Problem(409, "/problems/feedback-given", "Feedback was already given on this grievance")
        record = {**body.model_dump(), "at": datetime.now(UTC).isoformat()}
        await session.execute(update(grievances).where(grievances.c.grievance_id == grievanceId).values(feedback=record))
        g = {**g, "feedback": record}
        if body.satisfied:
            g = await move(session, g, "CLOSED", "member", f"Closed with the complainant's feedback ({body.rating}/5).")
        else:
            window = (await settings(session))["reopen_window_days"]
            await entry(session, g, "MESSAGE", "member", f"Feedback {body.rating}/5: not satisfied. The grievance can be reopened "
                                                           f"within {window} days of its resolution." + (f" {body.comment}" if body.comment else ""))
        await add_event(session, producer=PRODUCER, event_type="GrievanceFeedbackGiven.v1", aggregate_type="grievance",
                        aggregate_id=grievanceId, correlation_id=actor.correlation_id, payload={
                            "grievance_id": grievanceId, "office_id": g["office_id"], "rating": body.rating, "satisfied": body.satisfied})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.feedback",
                    target_type="grievance", target_id=grievanceId, detail=f"{body.rating}")
        result = {**await view(session, g), "feedback": record}
    return envelope(result)


class OfficeTransfer(BaseModel):
    to_office_id: str = Field(min_length=3, max_length=40)
    reason: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/grievances/{grievanceId}/office-transfers")
async def transfer(grievanceId: str, body: OfficeTransfer, actor: Actor = Depends(PRO), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievanceId, actor, lock=True)
        require_handler(g, actor)
        if g["state"] not in OPEN:
            raise Problem(409, "/problems/invalid-state", "Only an open grievance can be transferred", f"Current status: {g['state']}.")
        target = (await session.execute(select(offices).where(offices.c.office_id == body.to_office_id))).mappings().first()
        if not target or target["office_id"] == g["office_id"]:
            raise Problem(422, "/problems/validation", "Choose another office",
                          "Offices: " + ", ".join((await session.execute(select(offices.c.office_id).where(
                              offices.c.office_id != g["office_id"]))).scalars()))
        g = await move(session, g, "ROUTED", "fo.pro", f"Transferred from {g['office_id']} to {target['office_id']}: {body.reason}",
                       office_id=target["office_id"], zone_id=target["zone_id"], sla_due_at=await sla(session, "RO"))
        await add_event(session, producer=PRODUCER, event_type="GrievanceTransferred.v1", aggregate_type="grievance",
                        aggregate_id=grievanceId, correlation_id=actor.correlation_id, payload={
                            "grievance_id": grievanceId, "from_office_id": (await posting(session, actor))["office_id"],
                            "to_office_id": target["office_id"], "reason": body.reason})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.office_transfer",
                    target_type="grievance", target_id=grievanceId, detail=target["office_id"])
    return envelope({"grievance_id": grievanceId, "office_id": target["office_id"], "state": g["state"],
                     "note": f"The grievance now belongs to {target['name']}; your office no longer sees it."})
