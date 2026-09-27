"""employer-service routes (Journey A1, A2, A9; contracts/openapi/employer-service.yaml)."""
import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules import GRANTS_BY_KIND, RuleError, check_grants, mock_registry_check
from app.infra.db import sessions
from app.infra.tables import directory, establishments, grants, registration_requests
from epfo_auth import Actor, require_actor, require_grant, require_step_up, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "employer-service"


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6).upper()}"


def _rule_problem(e: RuleError) -> Problem:
    return Problem(422, f"/problems/{e.code}", e.message, e.fix)


def _establishment_of(actor: Actor) -> str:
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment selected",
                      "Your account has no active permission at any establishment.")
    return actor.establishment_id


async def _load_establishment(session: AsyncSession, establishment_id: str) -> dict[str, Any]:
    row = (await session.execute(select(establishments).where(establishments.c.establishment_id == establishment_id))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Establishment not found")
    return dict(row)


def _grant_view(row: Any) -> dict[str, Any]:
    return {"grant_id": row["grant_id"], "username": row["username"], "kind": row["kind"], "grants": row["grants"],
            "status": row["status"], "granted_by": row["granted_by"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None}


# ── Registration and verification (Journey A1) ──────────────────────────────────────────────

class RegistrationRequest(BaseModel):
    legal_name: str = Field(min_length=3, max_length=200)
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    gstin: str | None = None
    office_id: str = "RO-DEMO-01"
    pincode: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


@router.post("/api/v1/employers/registration-requests", status_code=201)
async def create_registration(body: RegistrationRequest, actor: Actor = Depends(require_stakeholder("employer.owner")),
                              session: AsyncSession = Depends(db)) -> dict:
    est_id, req_id = _new_id("EST"), _new_id("REQ")
    async with session.begin():
        await session.execute(establishments.insert().values(
            establishment_id=est_id, registration_number=f"DEMO/{est_id[-5:]}/000", legal_name=body.legal_name,
            office_id=body.office_id, pincode=body.pincode, pan=body.pan, gstin=body.gstin, status="REGISTERED"))
        await session.execute(registration_requests.insert().values(
            request_id=req_id, establishment_id=est_id, owner_subject=actor.subject, state="SUBMITTED"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="registration.submitted", target_type="establishment", target_id=est_id)
    return envelope({"request_id": req_id, "establishment_id": est_id, "state": "SUBMITTED",
                     "next_step": "Submit verification evidence (PAN, GSTIN) to complete registration."})


async def _own_request(session: AsyncSession, actor: Actor, req_id: str) -> dict[str, Any]:
    row = (await session.execute(select(registration_requests).where(registration_requests.c.request_id == req_id))).mappings().first()
    if not row or row["owner_subject"] != actor.subject:  # same answer whether it exists or not
        raise Problem(404, "/problems/not-found", "Registration request not found")
    return dict(row)


@router.get("/api/v1/employers/registration-requests/{reqId}")
async def get_registration(reqId: str, actor: Actor = Depends(require_stakeholder("employer.owner")),
                           session: AsyncSession = Depends(db)) -> dict:
    req = await _own_request(session, actor, reqId)
    est = await _load_establishment(session, req["establishment_id"])
    return envelope({"request_id": req["request_id"], "establishment_id": req["establishment_id"], "state": req["state"],
                     "result_reason": req["result_reason"], "verification_ref": req["verification_ref"],
                     "establishment": {"legal_name": est["legal_name"], "status": est["status"]}})


class Evidence(BaseModel):
    pan: str
    gstin: str | None = None
    note: str | None = Field(default=None, max_length=300)


@router.post("/api/v1/employers/registration-requests/{reqId}/verification-evidence")
async def submit_evidence(reqId: str, body: Evidence, actor: Actor = Depends(require_stakeholder("employer.owner")),
                          session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        req = await _own_request(session, actor, reqId)
        if req["state"] not in ("SUBMITTED", "REJECTED"):
            raise Problem(409, "/problems/invalid-state", "Evidence already accepted",
                          f"This request is {req['state']}; nothing more is needed.")
        est = await _load_establishment(session, req["establishment_id"])
        ok, reason = mock_registry_check(est, body.model_dump())
        ref = _new_id("MOCKVER")
        state = "VERIFIED" if ok else "REJECTED"
        await session.execute(update(registration_requests).where(registration_requests.c.request_id == reqId).values(
            state=state, evidence={"pan": body.pan, "gstin": body.gstin, "mock": True}, result_reason=reason,
            verification_ref=ref, updated_at=_now()))
        if ok:
            await session.execute(update(establishments).where(establishments.c.establishment_id == est["establishment_id"])
                                  .values(status="VERIFIED", verified_at=_now(), version=establishments.c.version + 1))
            await add_event(session, producer=PRODUCER, event_type="EmployerVerified.v1", aggregate_type="establishment",
                            aggregate_id=est["establishment_id"],
                            payload={"establishment_id": est["establishment_id"], "verification_ref": ref})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"verification.{state.lower()}", target_type="establishment", target_id=est["establishment_id"],
                    detail=reason)
    return envelope({"request_id": reqId, "state": state, "result_reason": reason, "verification_ref": ref, "mock": True,
                     "fix": None if ok else "Correct the PAN / GSTIN to match the establishment record and submit again."})


# ── Establishment profile and configuration ──────────────────────────────────────────────────

async def _require_member_of(session: AsyncSession, actor: Actor, establishment_id: str) -> None:
    """Defence in depth: the caller must still hold an active grant here (init.md §6.6 point 7)."""
    active = (await session.execute(select(func.count()).select_from(grants).where(and_(
        grants.c.subject == actor.subject, grants.c.establishment_id == establishment_id, grants.c.status == "ACTIVE")))).scalar()
    if not active:
        raise Problem(403, "/problems/forbidden", "Not allowed")


@router.get("/api/v1/employers/me")
async def get_me(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    est = await _load_establishment(session, est_id)
    req = (await session.execute(select(registration_requests).where(
        registration_requests.c.establishment_id == est_id).order_by(registration_requests.c.created_at.desc()))).mappings().first()
    return envelope({k: est[k] for k in ("establishment_id", "registration_number", "legal_name", "office_id", "status")}
                    | {"verified_at": est["verified_at"].isoformat() if est["verified_at"] else None,
                       "registration_request_id": req["request_id"] if req else None,
                       "your_permissions": actor.claims.get("grants", [])})


@router.get("/api/v1/employers/me/configuration")
async def get_configuration(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    est = await _load_establishment(session, est_id)
    return envelope({"establishment_id": est_id, "coverage_type": "Statutory (demo)", "exemption_status": "UN_EXEMPTED",
                     "jurisdiction_office": est["office_id"], "schemes": ["EPF", "EPS", "EDLI"], "sub_codes": [],
                     "source": "seeded synthetic configuration"})


# ── Operators and signatories (Journey A2, A9) ───────────────────────────────────────────────

async def _list(session: AsyncSession, est_id: str, kind: str) -> list[dict]:
    rows = (await session.execute(select(grants).where(and_(grants.c.establishment_id == est_id, grants.c.kind == kind))
                                  .order_by(grants.c.created_at))).mappings().all()
    return [_grant_view(r) for r in rows]


@router.get("/api/v1/employers/me/operators")
async def list_operators(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    return envelope(await _list(session, est_id, "OPERATOR"))


@router.get("/api/v1/employers/me/signatories")
async def list_signatories(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    return envelope(await _list(session, est_id, "SIGNATORY"))


class GrantRequest(BaseModel):
    username: str
    grants: list[str]
    dsc_reference: str | None = None  # demo evidence for a signatory


async def _add_grant(session: AsyncSession, actor: Actor, kind: str, body: GrantRequest, manage_grant: str,
                     step_action: str) -> dict:
    est_id = _establishment_of(actor)
    require_grant(actor, manage_grant)
    require_step_up(actor, step_action, est_id)
    try:
        chosen = check_grants(kind, body.grants)
    except RuleError as e:
        raise _rule_problem(e) from None
    async with session.begin():
        person = (await session.execute(select(directory).where(directory.c.username == body.username))).mappings().first()
        if not person:
            raise Problem(422, "/problems/unknown-user", "No such user",
                          "Use the username of an existing demo user (see the persona list).")
        if person["subject"] == actor.subject:
            raise Problem(422, "/problems/self-grant", "You cannot grant permissions to yourself")
        dup = (await session.execute(select(grants.c.grant_id).where(and_(
            grants.c.establishment_id == est_id, grants.c.subject == person["subject"], grants.c.kind == kind,
            grants.c.status == "ACTIVE")))).first()
        if dup:
            raise Problem(409, "/problems/already-granted", f"{body.username} already has an active {kind.lower()} grant",
                          "Revoke it first to change the permissions.")
        if kind == "OPERATOR" and (await session.execute(select(grants.c.grant_id).where(and_(
                grants.c.establishment_id == est_id, grants.c.subject == person["subject"], grants.c.kind == "SIGNATORY",
                grants.c.status == "ACTIVE")))).first():
            raise Problem(409, "/problems/separation-of-duties", "A signatory cannot also be the payroll preparer",
                          "Use a different person as operator (maker and checker must differ).")
        grant_id = _new_id("GR")
        await session.execute(grants.insert().values(
            grant_id=grant_id, establishment_id=est_id, subject=person["subject"], username=body.username, kind=kind,
            grants=chosen, status="ACTIVE", granted_by=actor.subject))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"{kind.lower()}.granted", target_type="grant", target_id=grant_id, detail=",".join(chosen))
        row = (await session.execute(select(grants).where(grants.c.grant_id == grant_id))).mappings().one()
    return envelope(_grant_view(row))


@router.post("/api/v1/employers/me/operators/invitations", status_code=201)
async def invite_operator(body: GrantRequest, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    return await _add_grant(session, actor, "OPERATOR", body, "operators.manage", "invite-operator")


@router.post("/api/v1/employers/me/signatories/authorisations", status_code=201)
async def authorise_signatory(body: GrantRequest, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    return await _add_grant(session, actor, "SIGNATORY", body, "signatories.manage", "authorise-signatory")


class Revocation(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


async def _revoke(session: AsyncSession, actor: Actor, kind: str, grant_id: str, reason: str, manage_grant: str,
                  step_action: str, event_type: str, subject_field: str) -> dict:
    est_id = _establishment_of(actor)
    require_grant(actor, manage_grant)
    require_step_up(actor, step_action, grant_id)
    async with session.begin():
        row = (await session.execute(select(grants).where(and_(
            grants.c.grant_id == grant_id, grants.c.establishment_id == est_id, grants.c.kind == kind)))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Grant not found")
        if row["status"] != "ACTIVE":
            raise Problem(409, "/problems/already-revoked", "Already revoked")
        await session.execute(update(grants).where(grants.c.grant_id == grant_id).values(
            status="REVOKED", revoked_by=actor.subject, revocation_reason=reason, revoked_at=_now()))
        await add_event(session, producer=PRODUCER, event_type=event_type, aggregate_type="establishment",
                        aggregate_id=est_id, payload={"establishment_id": est_id, subject_field: row["subject"],
                                                      "grant_id": grant_id, "scope": "grant", "revoked_by": actor.subject})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"{kind.lower()}.revoked", target_type="grant", target_id=grant_id, detail=reason)
        row = (await session.execute(select(grants).where(grants.c.grant_id == grant_id))).mappings().one()
    # `revocation` is read by the gateway, which writes its revocation set before answering (init.md §6.6)
    return envelope(_grant_view(row) | {"revocation": {"subject": row["subject"], "establishment_id": est_id,
                                                        "grant_id": grant_id, "scope": "grant"}})


@router.post("/api/v1/employers/me/operators/{operatorId}/revocations")
async def revoke_operator(operatorId: str, body: Revocation, actor: Actor = Depends(require_actor),
                          session: AsyncSession = Depends(db)) -> dict:
    return await _revoke(session, actor, "OPERATOR", operatorId, body.reason, "operators.manage", "revoke-operator",
                         "EmployerOperatorRevoked.v1", "operator_subject")


@router.post("/api/v1/employers/me/signatories/{signatoryId}/revocations")
async def revoke_signatory(signatoryId: str, body: Revocation, actor: Actor = Depends(require_actor),
                           session: AsyncSession = Depends(db)) -> dict:
    return await _revoke(session, actor, "SIGNATORY", signatoryId, body.reason, "signatories.manage", "revoke-signatory",
                         "SignatoryRevoked.v1", "signatory_subject")


# ── Public establishment search ──────────────────────────────────────────────────────────────

@router.get("/api/v1/public/establishments")
async def search_establishments(query: str = Query(min_length=3, max_length=60), page: int = Query(default=1, ge=1, le=5),
                                mode: Literal["any", "name", "code", "registration", "pincode", "industry"] = "any",
                                match: Literal["contains", "starts_with"] = "contains",
                                office_id: str | None = Query(default=None, max_length=40),
                                city: str | None = Query(default=None, max_length=80),
                                district: str | None = Query(default=None, max_length=80),
                                establishment_type: str | None = Query(default=None, max_length=80),
                                exemption_status: Literal["EXEMPT", "NOT_EXEMPT"] | None = None,
                                status: Literal["REGISTERED", "VERIFIED"] | None = None,
                                actor: Actor = Depends(require_actor),
                                session: AsyncSession = Depends(db)) -> dict:
    term = query.strip().lower()
    if len(term) < 3:
        raise Problem(400, "/problems/invalid-query", "Enter at least three characters")
    if mode == "pincode" and (len(term) != 6 or not term.isdigit()):
        raise Problem(400, "/problems/invalid-query", "Enter an exact six digit pincode")
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    name_filter = func.lower(establishments.c.legal_name).like(
        f"{'' if match == 'starts_with' else '%'}{escaped}%", escape="\\")
    industry_filter = func.lower(establishments.c.industry_group).like(f"%{escaped}%", escape="\\")
    exact_code = func.lower(establishments.c.establishment_id) == term
    exact_registration = func.lower(establishments.c.registration_number) == term
    exact_pincode = establishments.c.pincode == term
    by_mode = {"name": name_filter, "code": exact_code, "registration": exact_registration,
               "pincode": exact_pincode, "industry": industry_filter}
    search_filter = by_mode[mode] if mode != "any" else or_(
        name_filter, industry_filter, exact_code, exact_registration,
        exact_pincode if term.isdigit() and len(term) == 6 else False)
    statement = select(establishments).where(search_filter, establishments.c.status.in_(("REGISTERED", "VERIFIED")))
    if office_id:
        statement = statement.where(establishments.c.office_id == office_id.strip())
    if city:
        statement = statement.where(func.lower(establishments.c.city) == city.strip().lower())
    if district:
        statement = statement.where(func.lower(establishments.c.district) == district.strip().lower())
    if establishment_type:
        statement = statement.where(func.lower(establishments.c.establishment_type) == establishment_type.strip().lower())
    if exemption_status:
        statement = statement.where(establishments.c.exemption_status == exemption_status)
    if status:
        statement = statement.where(establishments.c.status == status)
    rows = (await session.execute(statement
        .order_by(establishments.c.legal_name, establishments.c.establishment_id)
        .limit(20).offset((page - 1) * 20))).mappings().all()
    return envelope([{"establishment_id": r["establishment_id"], "legal_name": r["legal_name"],
                      "registration_number": r["registration_number"], "office_id": r["office_id"],
                      "pincode": r["pincode"], "city": r["city"], "district": r["district"],
                      "establishment_type": r["establishment_type"],
                      "industry_group": r["industry_group"], "exemption_status": r["exemption_status"],
                      "status": r["status"]} for r in rows])


@router.get("/api/v1/public/establishments/{estId}")
async def public_establishment(estId: str, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    est = await _load_establishment(session, estId)
    if est["status"] not in ("REGISTERED", "VERIFIED"):
        raise Problem(404, "/problems/not-found", "Establishment not found")
    return envelope({"establishment_id": est["establishment_id"], "legal_name": est["legal_name"],
                     "registration_number": est["registration_number"], "office_id": est["office_id"],
                     "pincode": est["pincode"], "city": est["city"], "district": est["district"],
                     "establishment_type": est["establishment_type"], "industry_group": est["industry_group"],
                     "coverage_date": est["coverage_date"].isoformat() if est["coverage_date"] else None,
                     "verified_at": est["verified_at"].isoformat() if est["verified_at"] else None,
                     "coverage_status": est["status"],
                     "exemption_status": est["exemption_status"] or "NOT_MODELLED"})


# ── Internal: grant resolution for the gateway (not public; architecture §3 step 2) ─────────

@router.get("/internal/actors/{subject}/grants", include_in_schema=False)
async def actor_grants(subject: str, actor: Actor = Depends(require_stakeholder("system.gateway")),
                       session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(grants).where(and_(grants.c.subject == subject, grants.c.status == "ACTIVE"))
                                  )).mappings().all()
    by_est: dict[str, set[str]] = {}
    for r in rows:
        by_est.setdefault(r["establishment_id"], set()).update(r["grants"])
    return envelope({"subject": subject, "establishments": [
        {"establishment_id": est, "grants": sorted(g)} for est, g in sorted(by_est.items())]})
