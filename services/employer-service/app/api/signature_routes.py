"""Phase 2, slice 6b: an authorised signatory's DSC or Aadhaar e-sign registration (mock), the scanned request
letter that backs it, and the PF office's approval — the *Authorized eSign List*; a revocation is backed by a
signed revoke letter the office accepts. Nothing real is verified: the certificate and Aadhaar checks are mocks."""
import base64
import hashlib
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.establishment_routes import _office
from app.api.routes import _establishment_of, _require_member_of, db
from app.infra.tables import establishments, grants, signature_registrations
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
OWNER = require_stakeholder("employer.owner")
EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _view(r: Any, username: str | None = None) -> dict[str, Any]:
    return {"reg_id": r["reg_id"], "signatory_id": r["grant_id"], "username": username, "purpose": r["purpose"], "method": r["method"],
            "details": r["details"], "letter": r["letter"], "state": r["state"], "decision_note": r["decision_note"],
            "created_at": _iso(r["created_at"]), "decided_at": _iso(r["decided_at"])}


async def _signatory(session: AsyncSession, actor: Actor, grant_id: str) -> dict[str, Any]:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    row = (await session.execute(select(grants).where(grants.c.grant_id == grant_id, grants.c.establishment_id == est_id,
                                                      grants.c.kind == "SIGNATORY"))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Signatory not found")
    return dict(row)


async def _register(session: AsyncSession, actor: Actor, grant_id: str, method: str, details: dict[str, Any]) -> dict[str, Any]:
    require_grant(actor, "signatories.manage")
    s = await _signatory(session, actor, grant_id)
    if s["status"] != "ACTIVE":
        raise Problem(409, "/problems/invalid-state", "The signatory is revoked")
    require_step_up(actor, "register-signature", grant_id)
    if (await session.execute(select(signature_registrations.c.reg_id).where(
            signature_registrations.c.grant_id == grant_id, signature_registrations.c.purpose == "REGISTER",
            signature_registrations.c.state.in_(("LETTER_PENDING", "PENDING_OFFICE", "APPROVED"))))).first():
        raise Problem(409, "/problems/already-registered", "This signatory already has a registration in progress or approved")
    row = {"reg_id": f"SIG-{secrets.token_hex(4).upper()}", "establishment_id": s["establishment_id"], "grant_id": grant_id, "purpose": "REGISTER",
           "method": method, "details": details, "letter": None, "state": "LETTER_PENDING", "decision_note": None,
           "created_at": datetime.now(UTC), "decided_at": None}
    await session.execute(insert(signature_registrations).values(**row))
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"signatory.{method.lower()}_registered",
                target_type="grant", target_id=grant_id, detail=row["reg_id"])
    return _view(row, s["username"])


class DscInput(BaseModel):
    certificate_serial: str = Field(pattern=r"^[0-9A-Fa-f]{8,40}$")
    issuer: str = Field(min_length=3, max_length=80)
    holder_name: str = Field(min_length=2, max_length=120)
    valid_to: date


@router.post("/api/v1/employers/me/signatories/{signatoryId}/dsc-registrations", status_code=201)
async def register_dsc(signatoryId: str, body: DscInput, actor: Actor = Depends(OWNER), session: AsyncSession = Depends(db)) -> dict:
    if body.valid_to <= date.today():
        raise Problem(422, "/problems/certificate-expired", "The DSC has expired", "Register a class 3 DSC that is still valid (mock check).")
    async with session.begin():
        view = await _register(session, actor, signatoryId, "DSC", {
            "certificate_serial": "…" + body.certificate_serial[-6:].upper(), "issuer": body.issuer, "holder_name": body.holder_name.upper(),
            "valid_to": body.valid_to.isoformat(), "check": "mock: class 3 certificate, chain and expiry"})
    return envelope({**view, "next_step": "Upload the signed request letter (PDF) for the PF office."})


class EsignInput(BaseModel):
    holder_name: str = Field(min_length=2, max_length=120)
    aadhaar_last4: str = Field(pattern=r"^[0-9]{4}$")


@router.post("/api/v1/employers/me/signatories/{signatoryId}/esign-registrations", status_code=201)
async def register_esign(signatoryId: str, body: EsignInput, actor: Actor = Depends(OWNER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        view = await _register(session, actor, signatoryId, "ESIGN", {
            "holder_name": body.holder_name.upper(), "aadhaar": "XXXX-XXXX-" + body.aadhaar_last4, "check": "mock Aadhaar OTP (the one-time code)"})
    return envelope({**view, "next_step": "Upload the signed request letter (PDF) for the PF office."})


class Letter(BaseModel):
    filename: str = Field(min_length=3, max_length=120)
    content_base64: str = Field(min_length=4, max_length=1_400_000)


def _letter(body: Letter) -> dict[str, Any]:
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except ValueError as exc:
        raise Problem(422, "/problems/validation", "The file is not valid base64") from exc
    if not content.startswith(b"%PDF") or len(content) > 1_000_000:
        raise Problem(422, "/problems/validation", "Upload the scanned letter as a PDF of at most 1 MB")
    return {"filename": re.sub(r"[^A-Za-z0-9._-]", "_", body.filename), "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "uploaded_at": datetime.now(UTC).isoformat()}


@router.post("/api/v1/employers/me/signatories/{signatoryId}/request-letters", status_code=201)
async def request_letter(signatoryId: str, body: Letter, actor: Actor = Depends(OWNER), session: AsyncSession = Depends(db)) -> dict:
    require_grant(actor, "signatories.manage")
    async with session.begin():
        s = await _signatory(session, actor, signatoryId)
        reg = (await session.execute(select(signature_registrations).where(
            signature_registrations.c.grant_id == signatoryId, signature_registrations.c.purpose == "REGISTER",
            signature_registrations.c.state == "LETTER_PENDING"))).mappings().first()
        if not reg:
            raise Problem(409, "/problems/invalid-state", "Register the DSC or e-sign first")
        letter = _letter(body)
        await session.execute(update(signature_registrations).where(signature_registrations.c.reg_id == reg["reg_id"]).values(
            letter=letter, state="PENDING_OFFICE"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="signatory.request_letter",
                    target_type="grant", target_id=signatoryId, detail=letter["sha256"][:16])
    return envelope(_view({**dict(reg), "letter": letter, "state": "PENDING_OFFICE"}, s["username"]))


@router.post("/api/v1/employers/me/signatories/{signatoryId}/revoke-letters", status_code=201)
async def revoke_letter(signatoryId: str, body: Letter, actor: Actor = Depends(OWNER), session: AsyncSession = Depends(db)) -> dict:
    """After revoking a signatory, the signed revoke letter goes to the PF office (Signatory Revoke Request)."""
    require_grant(actor, "signatories.manage")
    async with session.begin():
        s = await _signatory(session, actor, signatoryId)
        if s["status"] != "REVOKED":
            raise Problem(409, "/problems/invalid-state", "Revoke the signatory first", "The revoke letter backs a revocation already made.")
        if (await session.execute(select(signature_registrations.c.reg_id).where(
                signature_registrations.c.grant_id == signatoryId, signature_registrations.c.purpose == "REVOKE",
                signature_registrations.c.state.in_(("PENDING_OFFICE", "APPROVED"))))).first():
            raise Problem(409, "/problems/already-sent", "A revoke letter is already with the office")
        row = {"reg_id": f"SIG-{secrets.token_hex(4).upper()}", "establishment_id": s["establishment_id"], "grant_id": signatoryId,
               "purpose": "REVOKE", "method": None, "details": {"reason": s["revocation_reason"]}, "letter": _letter(body),
               "state": "PENDING_OFFICE", "decision_note": None, "created_at": datetime.now(UTC), "decided_at": None}
        await session.execute(insert(signature_registrations).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="signatory.revoke_letter",
                    target_type="grant", target_id=signatoryId, detail=row["reg_id"])
    return envelope(_view(row, s["username"]))


@router.get("/api/v1/employers/me/signature-registrations")
async def esign_list(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """The Authorized eSign List: each signatory's registration and revoke requests with their status."""
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    rows = (await session.execute(select(signature_registrations, grants.c.username).join(
        grants, grants.c.grant_id == signature_registrations.c.grant_id).where(signature_registrations.c.establishment_id == est_id)
        .order_by(signature_registrations.c.created_at.desc()))).mappings().all()
    return envelope([_view(r, r["username"]) for r in rows])


@router.get("/api/v1/office/signature-registrations")
async def office_list(state: str = Query(default="PENDING_OFFICE", pattern="^(PENDING_OFFICE|APPROVED|REJECTED|REVOKED)$"),
                      actor: Actor = Depends(require_stakeholder("fo.apfc")), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    rows = (await session.execute(select(signature_registrations, grants.c.username, establishments.c.legal_name).join(
        grants, grants.c.grant_id == signature_registrations.c.grant_id).join(
        establishments, establishments.c.establishment_id == signature_registrations.c.establishment_id).where(
        establishments.c.office_id == office, signature_registrations.c.state == state).order_by(signature_registrations.c.created_at))).mappings().all()
    return envelope([{**_view(r, r["username"]), "establishment_id": r["establishment_id"], "legal_name": r["legal_name"]} for r in rows])


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/establishments/{estId}/signature-registrations/{regId}/decisions")
async def decide(estId: str, regId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc")),
                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        r = (await session.execute(select(signature_registrations).where(signature_registrations.c.reg_id == regId,
                                                                         signature_registrations.c.establishment_id == estId))).mappings().first()
        est = (await session.execute(select(establishments.c.office_id).where(establishments.c.establishment_id == estId))).scalar_one_or_none()
        if not r or est != office:
            raise Problem(404, "/problems/not-found", "Registration not found")
        if r["state"] != "PENDING_OFFICE":
            raise Problem(409, "/problems/invalid-state", "Not waiting for the office", f"State: {r['state']}.")
        require_step_up(actor, "decide-signature-registration", regId)
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        now = datetime.now(UTC)
        await session.execute(update(signature_registrations).where(signature_registrations.c.reg_id == regId).values(
            state=state, decided_by=actor.subject, decision_note=body.note, decided_at=now))
        if r["purpose"] == "REVOKE" and state == "APPROVED":           # the signatory's registration ends with the revocation
            await session.execute(update(signature_registrations).where(
                signature_registrations.c.grant_id == r["grant_id"], signature_registrations.c.purpose == "REGISTER",
                signature_registrations.c.state.in_(("APPROVED", "LETTER_PENDING", "PENDING_OFFICE"))).values(state="REVOKED", decided_at=now))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"signature_registration.{state.lower()}",
                    target_type="establishment", target_id=estId, detail=f"{regId} {r['purpose']}: {body.note}")
    return envelope(_view({**dict(r), "state": state, "decision_note": body.note, "decided_at": now}))
