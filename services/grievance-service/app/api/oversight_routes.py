"""Illustrative office RTI register and signed CPGRAMS grievance intake."""
import hashlib
import hmac
import os
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, entry, move, posting, settings, sla
from app.api.public_routes import mobile_hash
from app.infra.tables import grievances, offices, rti_requests
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
PRO = require_stakeholder("fo.pro")
CPGRAMS = require_stakeholder("ext.cpgrams")
SECRET = os.getenv("CPGRAMS_SECRET", "dev-cpgrams")
PRODUCER = "grievance-service"
EXEMPTIONS = {"8(1)(d)", "8(1)(e)", "8(1)(g)", "8(1)(j)", "9", "11"}


async def office(session: AsyncSession, actor: Actor) -> str:
    staff = await posting(session, actor)
    if not staff or staff["stakeholder"] != "fo.pro":
        raise Problem(404, "/problems/not-found", "No office posting found")
    return staff["office_id"]


class RtiInput(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=120)
    received_on: date
    mode: Literal["POST", "COUNTER", "RTI_PORTAL"]
    subject: str = Field(min_length=10, max_length=200)
    information_sought: str = Field(min_length=20, max_length=4000)
    fee_paid: bool
    bpl: bool


@router.post("/api/v1/office/rti-requests", status_code=201)
async def register_rti(body: RtiInput, actor: Actor = Depends(PRO), session: AsyncSession = Depends(db)) -> dict:
    if body.received_on > datetime.now(UTC).date():
        raise Problem(422, "/problems/validation", "Received date cannot be in the future")
    if not (body.fee_paid or body.bpl):
        raise Problem(422, "/problems/rti-fee-required", "the RTI fee or a BPL card is needed")
    async with session.begin():
        office_id = await office(session, actor)
        rules = await rules_on(session, body.received_on)
        due = body.received_on + timedelta(days=section(rules, "oversight_periods")["rti_reply_days"])
        query = select(offices).where(offices.c.office_id == office_id)
        if session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        if not (await session.execute(query)).first():
            raise Problem(404, "/problems/not-found", "Office not found")
        number = int((await session.execute(select(func.count()).select_from(rti_requests).where(
            rti_requests.c.office_id == office_id, rti_requests.c.registration_year == body.received_on.year))).scalar_one()) + 1
        request_id = f"RTI-{secrets.token_hex(8).upper()}"
        registration_no = f"RTI/{office_id}/{body.received_on.year}/{number}"
        await session.execute(insert(rti_requests).values(request_id=request_id, registration_no=registration_no,
            registration_year=body.received_on.year, office_id=office_id, applicant_name=body.applicant_name.strip(),
            received_on=body.received_on, mode=body.mode, subject=body.subject, information_sought=body.information_sought,
            fee_paid=body.fee_paid, bpl=body.bpl, reply_due=due, state="OPEN"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="rti.register", target_type="rti_request", target_id=request_id)
    return envelope({"request_id": request_id, "registration_no": registration_no, "reply_due": due.isoformat(), "state": "OPEN"})


@router.get("/api/v1/office/rti-requests")
async def list_rti(state: Literal["OPEN", "REPLIED"] | None = None, actor: Actor = Depends(PRO),
                   session: AsyncSession = Depends(db)) -> dict:
    office_id = await office(session, actor)
    q = select(rti_requests).where(rti_requests.c.office_id == office_id)
    if state:
        q = q.where(rti_requests.c.state == state)
    rows = (await session.execute(q.order_by(rti_requests.c.registration_no))).mappings().all()
    today = datetime.now(UTC).date()
    return envelope([{**dict(r), "received_on": str(r["received_on"]), "reply_due": str(r["reply_due"]),
                      "replied_at": r["replied_at"].isoformat() if r["replied_at"] else None,
                      "days_left": (date.fromisoformat(str(r["reply_due"])) - today).days,
                      "overdue": r["state"] == "OPEN" and date.fromisoformat(str(r["reply_due"])) < today} for r in rows])


class RtiReply(BaseModel):
    outcome: Literal["INFORMATION_PROVIDED", "PARTLY_PROVIDED", "REFUSED", "TRANSFERRED"]
    reply: str = Field(min_length=20, max_length=4000)
    exemption_section: str | None = None
    transferred_to: str | None = None


@router.post("/api/v1/office/rti-requests/{requestId}/replies")
async def reply_rti(requestId: str, body: RtiReply, actor: Actor = Depends(PRO), session: AsyncSession = Depends(db)) -> dict:
    if body.outcome in {"REFUSED", "PARTLY_PROVIDED"} and body.exemption_section not in EXEMPTIONS:
        raise Problem(422, "/problems/validation", "A valid exemption section is required")
    if body.outcome == "TRANSFERRED" and not (body.transferred_to or "").strip():
        raise Problem(422, "/problems/validation", "The receiving authority is required")
    async with session.begin():
        office_id = await office(session, actor)
        q = select(rti_requests).where(rti_requests.c.request_id == requestId, rti_requests.c.office_id == office_id)
        if session.bind.dialect.name == "postgresql":
            q = q.with_for_update()
        row = (await session.execute(q)).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "RTI request not found")
        if row["state"] != "OPEN":
            raise Problem(409, "/problems/invalid-state", "Only an open RTI request can be replied to")
        today = datetime.now(UTC).date()
        late = today > date.fromisoformat(str(row["reply_due"]))
        transfer_late = body.outcome == "TRANSFERRED" and today > date.fromisoformat(str(row["received_on"])) + timedelta(days=5)
        await session.execute(update(rti_requests).where(rti_requests.c.request_id == requestId).values(
            state="REPLIED", outcome=body.outcome, reply=body.reply, exemption_section=body.exemption_section,
            transferred_to=body.transferred_to, replied_at=datetime.now(UTC), late=late, transfer_late=transfer_late))
        await add_event(session, producer=PRODUCER, event_type="RtiReplied.v1", aggregate_type="rti_request",
                        aggregate_id=requestId, correlation_id=actor.correlation_id,
                        payload={"request_id": requestId, "office_id": office_id, "outcome": body.outcome, "late": late})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="rti.reply", target_type="rti_request", target_id=requestId, detail=body.outcome)
    return envelope({"request_id": requestId, "state": "REPLIED", "outcome": body.outcome,
                     "late": late, "transfer_late": transfer_late})


class CpgramsInput(BaseModel):
    cpgrams_registration_no: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    mobile: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    category: str
    description: str = Field(min_length=10, max_length=4000)
    received_on: date
    uan: str | None = None
    office_id: str | None = None
    signature: str = Field(min_length=64, max_length=64)


def cpgrams_message(body: CpgramsInput) -> bytes:
    """HMAC-SHA256 over all fields, in this fixed order, joined with |; absent fields are empty strings."""
    return "|".join([body.cpgrams_registration_no, body.name, body.mobile or "", body.category,
                     body.description, body.received_on.isoformat(), body.uan or "", body.office_id or ""]).encode()


@router.post("/api/v1/integrations/cpgrams/grievances", status_code=201)
async def cpgrams_intake(body: CpgramsInput, response: Response, actor: Actor = Depends(CPGRAMS),
                         session: AsyncSession = Depends(db)) -> dict:
    expected = hmac.new(SECRET.encode(), cpgrams_message(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.signature):
        raise Problem(401, "/problems/bad-signature", "The callback signature does not match")
    async with session.begin():
        existing = (await session.execute(select(grievances).where(
            grievances.c.cpgrams_registration_no == body.cpgrams_registration_no))).mappings().first()
        if existing:
            response.status_code = 200
            return envelope({"registration_no": existing["grievance_id"], "grievance_id": existing["grievance_id"],
                             "cpgrams_registration_no": body.cpgrams_registration_no, "state": existing["state"],
                             "office_id": existing["office_id"]})
        categories = (await settings(session))["categories"]
        if body.category not in categories:
            raise Problem(422, "/problems/validation", "Unknown category")
        q = select(offices).where(offices.c.office_id == body.office_id) if body.office_id else select(offices).order_by(offices.c.office_id).limit(1)
        home = (await session.execute(q)).mappings().first()
        if not home:
            raise Problem(422, "/problems/validation", "Unknown office")
        gid = f"GRV-{secrets.token_hex(4).upper()}"
        await session.execute(insert(grievances).values(grievance_id=gid, complainant_subject=f"CPGRAMS:{gid}",
            category=body.category, subject_line=body.description[:200], description=body.description,
            linked_claim_id=None, office_id=home["office_id"], zone_id=home["zone_id"], tier="RO",
            state="REGISTERED", version=1, sla_due_at=await sla(session, "RO"), source="CPGRAMS",
            cpgrams_registration_no=body.cpgrams_registration_no, complainant_type="OTHER", public_name=body.name.strip(),
            mobile_hash=mobile_hash(body.mobile) if body.mobile else None, mobile_last4=body.mobile[-4:] if body.mobile else None))
        g = dict((await session.execute(select(grievances).where(grievances.c.grievance_id == gid))).mappings().one())
        await entry(session, g, "STATUS", "cpgrams", "Grievance received from CPGRAMS.", state="REGISTERED")
        if body.uan:
            await entry(session, g, "MESSAGE", "cpgrams", f"UAN reference: {body.uan}")
        await add_event(session, producer=PRODUCER, event_type="GrievanceRegistered.v1", aggregate_type="grievance",
                        aggregate_id=gid, correlation_id=actor.correlation_id, payload={"grievance_id": gid,
                            "category": body.category, "office_id": home["office_id"], "linked_claim_id": ""})
        g = await move(session, g, "ROUTED", "system", f"Sent to the regional office {home['office_id']}.")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="grievance.register_cpgrams", target_type="grievance", target_id=gid,
                    detail=body.cpgrams_registration_no)
    return envelope({"registration_no": gid, "grievance_id": gid, "cpgrams_registration_no": body.cpgrams_registration_no,
                     "state": g["state"], "office_id": g["office_id"]})


@router.get("/api/v1/office/grievances")
async def office_grievances(actor: Actor = Depends(PRO), session: AsyncSession = Depends(db)) -> dict:
    office_id = await office(session, actor)
    rows = (await session.execute(select(grievances).where(grievances.c.office_id == office_id,
            grievances.c.tier == "RO").order_by(grievances.c.created_at.desc()))).mappings().all()
    return envelope([{"grievance_id": r["grievance_id"], "registration_no": r["grievance_id"],
                      "cpgrams_registration_no": r["cpgrams_registration_no"], "source": r["source"],
                      "category": r["category"], "subject": r["subject_line"], "state": r["state"],
                      "office_id": r["office_id"]} for r in rows])
