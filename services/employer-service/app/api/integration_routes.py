"""Signed synthetic MCA and Shram Suvidha registration feeds."""
import hashlib
import hmac
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _new_id, db
from app.config import settings
from app.infra.tables import establishments, offices, registration_requests
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()


class FeedAddress(BaseModel):
    line1: str = Field(min_length=3, max_length=200)
    city: str = Field(min_length=2, max_length=80)
    district: str = Field(min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^[0-9]{6}$")


class McaRegistration(BaseModel):
    cin: str = Field(min_length=5, max_length=40)
    company_name: str = Field(min_length=3, max_length=200)
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    incorporated_on: date
    address: FeedAddress
    office_id: str | None = None
    signature: str = Field(min_length=64, max_length=64)


class ShramRegistration(BaseModel):
    lin: str = Field(min_length=5, max_length=40)
    establishment_name: str = Field(min_length=3, max_length=200)
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    registered_on: date
    address: FeedAddress
    signature: str = Field(min_length=64, max_length=64)


async def _register(session: AsyncSession, response: Response, actor: Actor, source: str, source_ref: str,
                    name: str, pan: str, registered_on: date, address: FeedAddress,
                    office_id: str | None, signature: str, secret: str) -> dict:
    # The signature covers the stable identity and registration fields in the published order.
    message = f"{source_ref}|{name}|{pan}|{registered_on.isoformat()}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise Problem(401, "/problems/bad-signature", "The callback signature does not match")
    async with session.begin():
        prior = (await session.execute(select(registration_requests).where(
            registration_requests.c.source == source, registration_requests.c.source_ref == source_ref))).mappings().first()
        if prior:
            response.status_code = 200
            return envelope({"request_id": prior["request_id"], "establishment_id": prior["establishment_id"],
                             "state": prior["state"], "source": source})
        if (await session.execute(select(establishments.c.establishment_id).where(establishments.c.pan == pan))).first():
            raise Problem(409, "/problems/duplicate-pan", "PAN belongs to another establishment")
        target_office = office_id or "RO-DEMO-01"
        if not (await session.execute(select(offices.c.office_id).where(offices.c.office_id == target_office))).first():
            raise Problem(422, "/problems/validation", "Unknown office")
        est_id, req_id = _new_id("EST"), _new_id("REQ")
        now = datetime.now(UTC)
        await session.execute(establishments.insert().values(
            establishment_id=est_id, registration_number=f"DEMO/{est_id[-5:]}/000", legal_name=name,
            office_id=target_office, pincode=address.pincode, city=address.city, district=address.district,
            pan=pan, status="VERIFIED", verified_at=now,
            address={"line": address.line1, "city": address.city, "district": address.district, "pincode": address.pincode},
            kyc={"PAN": {"value": pan, "status": "VERIFIED"},
                 ("CIN" if source == "MCA_SPICE" else "LIN"): {"value": source_ref, "status": "VERIFIED"}}))
        await session.execute(registration_requests.insert().values(
            request_id=req_id, establishment_id=est_id, owner_subject=actor.subject, state="VERIFIED",
            source=source, source_ref=source_ref, evidence={"pan": pan, "source": source, "source_ref": source_ref,
                                                           "registered_on": registered_on.isoformat(), "mock": True},
            result_reason="Signed synthetic registry feed", verification_ref=source_ref))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="registration.submitted", target_type="establishment", target_id=est_id, detail=source)
    response.status_code = 201
    return envelope({"request_id": req_id, "establishment_id": est_id, "state": "VERIFIED", "source": source})


@router.post("/api/v1/integrations/mca/registrations", status_code=201)
async def mca_registration(body: McaRegistration, response: Response,
                           actor: Actor = Depends(require_stakeholder("ext.mca")), session: AsyncSession = Depends(db)) -> dict:
    return await _register(session, response, actor, "MCA_SPICE", body.cin, body.company_name, body.pan,
                           body.incorporated_on, body.address, body.office_id, body.signature, settings.mca_spice_secret)


@router.post("/api/v1/integrations/shram-suvidha/registrations", status_code=201)
async def shram_registration(body: ShramRegistration, response: Response,
                             actor: Actor = Depends(require_stakeholder("ext.shram_suvidha")),
                             session: AsyncSession = Depends(db)) -> dict:
    return await _register(session, response, actor, "SHRAM_SUVIDHA", body.lin, body.establishment_name, body.pan,
                           body.registered_on, body.address, None, body.signature, settings.shram_suvidha_secret)
