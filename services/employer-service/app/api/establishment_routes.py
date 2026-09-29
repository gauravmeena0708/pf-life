"""Phase 2, slice 6a: the establishment's own record — KYC (mock registries), bank accounts, exemption, branches
(sub-codes, Form 2A), Form 5A ownership return, contractors of a principal employer — and changes to it, which the
establishment asks for and the office decides. The office's OLRE scrutiny of a new registration: documents, notes
and the compliance e-file (DA Compliance), then the circle officer's coverage decision (APFC)."""
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _establishment_of, _load_establishment, _require_member_of, db
from app.domain.rules import GSTIN_RE, PAN_RE
from app.infra.tables import (branches, change_requests, contractors, establishments, office_staff, ownership_declarations,
                              registration_requests, registration_scrutiny)
from epfo_auth import Actor, require_actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")
OWNER_OR_SIGNATORY = require_stakeholder("employer.owner", "employer.signatory")


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _mask(value: str | None) -> str | None:
    return None if not value else "*" * max(0, len(value) - 4) + value[-4:]


async def _mine(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    est_id = _establishment_of(actor)
    await _require_member_of(session, actor, est_id)
    return await _load_establishment(session, est_id)


def _manager(actor: Actor) -> None:
    """The owner acts with the establishment.manage grant; a signatory signs with DSC / e-sign (mock)."""
    if actor.stakeholder == "employer.owner":
        require_grant(actor, "establishment.manage")
    elif actor.stakeholder != "employer.signatory":
        raise Problem(403, "/problems/forbidden", "Not allowed", "The owner or an authorised signatory does this.")


# ── KYC, bank accounts, exemption ─────────────────────────────────────────────────────────────────

KYC_FORMATS = {"PAN": PAN_RE, "GSTIN": GSTIN_RE, "TAN": re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$"),
               "CIN": re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$"), "LIN": re.compile(r"^[0-9]{10}$")}


def _kyc_view(est: dict[str, Any]) -> dict[str, Any]:
    kyc = est["kyc"] or {"PAN": {"value": est["pan"], "status": "VERIFIED"}}
    return {t: {"value": _mask((kyc.get(t) or {}).get("value")), "status": (kyc.get(t) or {}).get("status", "NOT_SEEDED"),
                "reference": (kyc.get(t) or {}).get("reference")} for t in KYC_FORMATS}


@router.get("/api/v1/employers/me/kyc")
async def kyc(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    return envelope({"establishment_id": est["establishment_id"], "kyc": _kyc_view(est),
                     "note": "Verified against mock registries (Income Tax, GSTN, MCA, Shram Suvidha); nothing is sent anywhere."})


class KycInput(BaseModel):
    value: str = Field(min_length=5, max_length=30)


@router.post("/api/v1/employers/me/kyc/{kycType}", status_code=201)
async def seed_kyc(kycType: str, body: KycInput, actor: Actor = Depends(OWNER_OR_SIGNATORY),
                   session: AsyncSession = Depends(db)) -> dict:
    kind, value = kycType.upper(), body.value.strip().upper()
    if kind not in KYC_FORMATS:
        raise Problem(404, "/problems/not-found", "Unknown KYC type", "One of: " + ", ".join(KYC_FORMATS))
    _manager(actor)
    async with session.begin():
        est = await _mine(session, actor)
        require_step_up(actor, "seed-establishment-kyc", f"{est['establishment_id']}:{kind}")
        if not KYC_FORMATS[kind].match(value):
            raise Problem(422, "/problems/validation", f"{kind} format is not valid")
        if kind == "PAN" and value != est["pan"]:
            status, why = "REJECTED", "PAN does not match the establishment record (mock registry)."
        elif kind == "GSTIN" and value[2:12] != est["pan"]:
            status, why = "REJECTED", "GSTIN does not contain the establishment PAN (mock GSTN)."
        elif "00000" in value:                                     # the mock registry has no such number
            status, why = "REJECTED", f"{kind} not found in the mock registry."
        else:
            status, why = "VERIFIED", f"{kind} verified against the mock registry."
        ref = _id("MOCKKYC")
        kyc_all = dict(est["kyc"] or {})
        kyc_all[kind] = {"value": value if status == "VERIFIED" else (kyc_all.get(kind) or {}).get("value"),
                         "status": status if status == "VERIFIED" else (kyc_all.get(kind) or {}).get("status", "NOT_SEEDED"), "reference": ref}
        await session.execute(update(establishments).where(establishments.c.establishment_id == est["establishment_id"]).values(kyc=kyc_all))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"establishment.kyc_{status.lower()}",
                    target_type="establishment", target_id=est["establishment_id"], detail=f"{kind} {ref}")
    return envelope({"kyc_type": kind, "result": status, "reason": why, "reference": ref, "mock": True})


@router.get("/api/v1/employers/me/bank-accounts")
async def bank_accounts(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    return envelope(est["bank_accounts"] or [])


@router.get("/api/v1/employers/me/exemption")
async def exemption(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    status = est["exemption_status"] or "NOT_EXEMPT"
    return envelope({"establishment_id": est["establishment_id"], "exemption_status": status, "exempted": status != "NOT_EXEMPT",
                     "pf_trust": None, "relaxations": [],
                     "note": "Not exempted: EPF, EPS and EDLI are all administered by EPFO." if status == "NOT_EXEMPT" else "Exempted (synthetic)."})


# ── branches (sub-codes, Form 2A) ─────────────────────────────────────────────────────────────────

class Address(BaseModel):
    line: str = Field(min_length=3, max_length=200)
    city: str = Field(min_length=2, max_length=80)
    district: str = Field(min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^[0-9]{6}$")


class BranchInput(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    kind: str = Field(default="BRANCH", pattern="^(BRANCH|DEPARTMENT)$")
    address: Address


def _branch_view(b: Any) -> dict[str, Any]:
    return {"branch_id": b["branch_id"], "sub_code": b["sub_code"], "name": b["name"], "kind": b["kind"], "address": b["address"],
            "created_at": _iso(b["created_at"])}


@router.get("/api/v1/employers/me/branches")
async def list_branches(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    rows = (await session.execute(select(branches).where(branches.c.establishment_id == est["establishment_id"])
                                  .order_by(branches.c.sub_code))).mappings().all()
    return envelope([_branch_view(r) for r in rows])


@router.post("/api/v1/employers/me/branches", status_code=201)
async def add_branch(body: BranchInput, actor: Actor = Depends(OWNER_OR_SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    _manager(actor)
    async with session.begin():
        est = await _mine(session, actor)
        n = (await session.execute(select(func.count()).select_from(branches).where(branches.c.establishment_id == est["establishment_id"]))).scalar_one()
        row = {"branch_id": _id("BR"), "establishment_id": est["establishment_id"], "sub_code": f"{est['registration_number']}/{n + 1:03d}",
               "name": body.name, "kind": body.kind, "address": body.address.model_dump(), "created_by": actor.subject, "created_at": datetime.now(UTC)}
        await session.execute(insert(branches).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="establishment.branch_added",
                    target_type="establishment", target_id=est["establishment_id"], detail=row["sub_code"])
    return envelope(_branch_view(row))


# ── Form 5A ───────────────────────────────────────────────────────────────────────────────────────

class Person(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    designation: str = Field(min_length=2, max_length=80)
    role: str = Field(pattern="^(PROPRIETOR|PARTNER|DIRECTOR|MANAGER|OCCUPIER)$")
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    share_pct: float = Field(default=0, ge=0, le=100)


class Form5A(BaseModel):
    nature_of_business: str = Field(min_length=3, max_length=200)
    persons: list[Person] = Field(min_length=1, max_length=50)


def _form5a_view(d: Any) -> dict[str, Any]:
    return {"declaration_id": d["declaration_id"], "version": d["version"], "nature_of_business": d["nature_of_business"],
            "persons": [{**p, "pan": _mask(p["pan"])} for p in d["persons"]], "signed": "DSC / e-sign (mock)", "created_at": _iso(d["created_at"])}


@router.get("/api/v1/employers/me/ownership-declaration")
async def get_form5a(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    rows = (await session.execute(select(ownership_declarations).where(ownership_declarations.c.establishment_id == est["establishment_id"])
                                  .order_by(ownership_declarations.c.version.desc()))).mappings().all()
    if not rows:
        return envelope({"filed": False, "note": "Form 5A has not been filed. The owner or a signatory files it, signed with DSC / e-sign."})
    return envelope({"filed": True, **_form5a_view(rows[0]), "earlier_versions": len(rows) - 1})


@router.put("/api/v1/employers/me/ownership-declaration")
async def put_form5a(body: Form5A, actor: Actor = Depends(OWNER_OR_SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    _manager(actor)
    if sum(p.share_pct for p in body.persons) > 100:
        raise Problem(422, "/problems/validation", "Shares add up to more than 100%")
    async with session.begin():
        est = await _mine(session, actor)
        require_step_up(actor, "sign-form-5a", est["establishment_id"])             # DSC / e-sign in the real portal
        version = 1 + ((await session.execute(select(func.max(ownership_declarations.c.version)).where(
            ownership_declarations.c.establishment_id == est["establishment_id"]))).scalar_one() or 0)
        row = {"declaration_id": _id("F5A"), "establishment_id": est["establishment_id"], "version": version,
               "nature_of_business": body.nature_of_business, "persons": [p.model_dump() for p in body.persons],
               "signed_by": actor.subject, "created_at": datetime.now(UTC)}
        await session.execute(insert(ownership_declarations).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="establishment.form5a_filed",
                    target_type="establishment", target_id=est["establishment_id"], detail=f"version {version}")
    return envelope({"filed": True, **_form5a_view(row)})


# ── contractors of a principal employer ───────────────────────────────────────────────────────────

class ContractorInput(BaseModel):
    registration_number: str = Field(min_length=5, max_length=40)
    name: str = Field(min_length=3, max_length=200)
    work_order_ref: str = Field(min_length=3, max_length=80)
    valid_from: date
    valid_to: date | None = None


def _contractor_view(c: Any) -> dict[str, Any]:
    return {"contractor_id": c["contractor_id"], "registration_number": c["contractor_registration_number"], "name": c["contractor_name"],
            "registered_with_epfo": c["contractor_establishment_id"] is not None, "work_order_ref": c["work_order_ref"],
            "valid_from": _iso(c["valid_from"]), "valid_to": _iso(c["valid_to"])}


@router.get("/api/v1/employers/me/contractors")
async def list_contractors(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    rows = (await session.execute(select(contractors).where(contractors.c.principal_establishment_id == est["establishment_id"])
                                  .order_by(contractors.c.created_at))).mappings().all()
    return envelope([_contractor_view(r) for r in rows])


@router.post("/api/v1/employers/me/contractors", status_code=201)
async def link_contractor(body: ContractorInput, actor: Actor = Depends(require_stakeholder("employer.owner")),
                          session: AsyncSession = Depends(db)) -> dict:
    require_grant(actor, "establishment.manage")
    if body.valid_to and body.valid_to < body.valid_from:
        raise Problem(422, "/problems/validation", "The work order ends before it starts")
    async with session.begin():
        est = await _mine(session, actor)
        other = (await session.execute(select(establishments.c.establishment_id).where(
            establishments.c.registration_number == body.registration_number))).scalar_one_or_none()
        if other == est["establishment_id"]:
            raise Problem(422, "/problems/validation", "An establishment cannot be its own contractor")
        row = {"contractor_id": _id("CTR"), "principal_establishment_id": est["establishment_id"],
               "contractor_registration_number": body.registration_number, "contractor_name": body.name,
               "contractor_establishment_id": other, "work_order_ref": body.work_order_ref, "valid_from": body.valid_from,
               "valid_to": body.valid_to, "linked_by": actor.subject}
        await session.execute(insert(contractors).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="establishment.contractor_linked",
                    target_type="establishment", target_id=est["establishment_id"], detail=body.registration_number)
    return envelope(_contractor_view(row))


# ── changes asked for by the establishment, decided by the office ─────────────────────────────────

class ProfileChange(BaseModel):
    address: Address | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    reason: str = Field(min_length=10, max_length=500)


CONFIG_FIELDS = {"establishment_type": {"PRIVATE_COMPANY", "PUBLIC_COMPANY", "PARTNERSHIP", "PROPRIETORSHIP", "TRUST", "SOCIETY", "LLP"},
                 "industry_group": None}


class ConfigChange(BaseModel):
    field: str = Field(pattern="^(establishment_type|industry_group)$")
    value: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=10, max_length=500)


def _request_view(r: Any) -> dict[str, Any]:
    return {"request_id": r["request_id"], "establishment_id": r["establishment_id"], "kind": r["kind"], "changes": r["changes"],
            "reason": r["reason"], "state": r["state"], "decision_note": r["decision_note"], "created_at": _iso(r["created_at"]),
            "decided_at": _iso(r["decided_at"])}


async def _open_request(session: AsyncSession, actor: Actor, kind: str, changes: dict[str, Any], reason: str) -> dict[str, Any]:
    est = await _mine(session, actor)
    require_step_up(actor, "request-establishment-change", est["establishment_id"])
    if (await session.execute(select(change_requests.c.request_id).where(change_requests.c.establishment_id == est["establishment_id"],
                                                                          change_requests.c.kind == kind, change_requests.c.state == "PENDING"))).first():
        raise Problem(409, "/problems/request-open", "A change of this kind is already with the office")
    row = {"request_id": _id("CHG"), "establishment_id": est["establishment_id"], "kind": kind, "changes": changes, "reason": reason,
           "state": "PENDING", "requested_by": actor.subject, "decision_note": None, "created_at": datetime.now(UTC), "decided_at": None}
    await session.execute(insert(change_requests).values(**row))
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"establishment.change_requested",
                target_type="establishment", target_id=est["establishment_id"], detail=f"{kind} {row['request_id']}")
    return _request_view(row)


@router.patch("/api/v1/employers/me")
async def request_profile_change(body: ProfileChange, actor: Actor = Depends(OWNER_OR_SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    """Address / contact: not edited directly — a change request the office approves."""
    _manager(actor)
    async with session.begin():
        est = await _mine(session, actor)
        now = dict(est["address"] or {})
        wanted = {**({"line": body.address.line, "city": body.address.city, "district": body.address.district,
                      "pincode": body.address.pincode} if body.address else {}),
                  **({"email": body.email} if body.email else {}), **({"phone": body.phone} if body.phone else {})}
        changes = {k: {"from": now.get(k), "to": v} for k, v in wanted.items() if now.get(k) != v}
        if not changes:
            raise Problem(422, "/problems/no-change", "Nothing would change")
        view = await _open_request(session, actor, "PROFILE", changes, body.reason)
    return envelope(view)


@router.post("/api/v1/employers/me/configuration/change-requests", status_code=201)
async def request_config_change(body: ConfigChange, actor: Actor = Depends(OWNER_OR_SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    _manager(actor)
    allowed = CONFIG_FIELDS[body.field]
    if allowed is not None and body.value not in allowed:
        raise Problem(422, "/problems/validation", f"Choose one of: {', '.join(sorted(allowed))}")
    async with session.begin():
        est = await _mine(session, actor)
        if est[body.field] == body.value:
            raise Problem(422, "/problems/no-change", "Nothing would change")
        view = await _open_request(session, actor, "CONFIGURATION", {body.field: {"from": est[body.field], "to": body.value}}, body.reason)
    return envelope(view)


@router.get("/api/v1/employers/me/change-requests")
async def my_change_requests(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = await _mine(session, actor)
    rows = (await session.execute(select(change_requests).where(change_requests.c.establishment_id == est["establishment_id"])
                                  .order_by(change_requests.c.created_at.desc()))).mappings().all()
    return envelope([_request_view(r) for r in rows])


async def _office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


@router.get("/api/v1/office/establishment-change-requests")
async def office_change_requests(state: str = Query(default="PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
                                 actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    rows = (await session.execute(select(change_requests, establishments.c.legal_name).join(
        establishments, establishments.c.establishment_id == change_requests.c.establishment_id).where(
        establishments.c.office_id == office, change_requests.c.state == state).order_by(change_requests.c.created_at))).mappings().all()
    return envelope([{**_request_view(r), "legal_name": r["legal_name"]} for r in rows])


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/establishments/{estId}/change-requests/{requestId}/decisions")
async def decide_change(estId: str, requestId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        r = (await session.execute(select(change_requests).where(change_requests.c.request_id == requestId,
                                                                 change_requests.c.establishment_id == estId))).mappings().first()
        est = (await session.execute(select(establishments).where(establishments.c.establishment_id == estId))).mappings().first()
        if not r or not est or est["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Change request not found")
        if r["state"] != "PENDING":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {r['state']}.")
        require_step_up(actor, "decide-establishment-change", requestId)
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        if state == "APPROVED":
            changes = {k: v["to"] for k, v in r["changes"].items()}
            values: dict[str, Any] = {k: v for k, v in changes.items() if k in CONFIG_FIELDS}
            contact = {k: v for k, v in changes.items() if k not in CONFIG_FIELDS}
            if contact:
                values["address"] = {**(est["address"] or {}), **contact}
                if "pincode" in contact:
                    values.update(pincode=contact["pincode"], city=contact.get("city", est["city"]), district=contact.get("district", est["district"]))
            await session.execute(update(establishments).where(establishments.c.establishment_id == estId).values(
                **values, version=establishments.c.version + 1))
        await session.execute(update(change_requests).where(change_requests.c.request_id == requestId).values(
            state=state, decided_by=actor.subject, decision_note=body.note, decided_at=datetime.now(UTC)))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"establishment.change_{state.lower()}",
                    target_type="establishment", target_id=estId, detail=f"{requestId}: {body.note}")
        row = {**dict(r), "state": state, "decision_note": body.note, "decided_at": datetime.now(UTC)}
    return envelope(_request_view(row))


# ── OLRE: the office's scrutiny of a new registration and the coverage decision ────────────────────

OLRE = require_stakeholder("fo.da_compliance", "fo.apfc")


async def _registration(session: AsyncSession, actor: Actor, req_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    office = await _office(session, actor)
    req = (await session.execute(select(registration_requests).where(registration_requests.c.request_id == req_id))).mappings().first()
    est = (await session.execute(select(establishments).where(establishments.c.establishment_id == req["establishment_id"]))).mappings().first() if req else None
    if not req or not est or est["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Registration not found")
    return dict(req), dict(est)


async def _olre_view(session: AsyncSession, req: dict[str, Any], est: dict[str, Any]) -> dict[str, Any]:
    scrutiny = (await session.execute(select(registration_scrutiny).where(registration_scrutiny.c.request_id == req["request_id"]))).mappings().first()
    stage = "COVERAGE_DECIDED" if est["coverage"] else "SCRUTINISED" if scrutiny else "AWAITING_SCRUTINY" if req["state"] == "VERIFIED" else req["state"]
    return {"request_id": req["request_id"], "establishment_id": est["establishment_id"], "legal_name": est["legal_name"],
            "registration_number": est["registration_number"], "registration_state": req["state"], "stage": stage,
            "efile_no": scrutiny["efile_no"] if scrutiny else None, "notes": scrutiny["notes"] if scrutiny else [],
            "coverage": est["coverage"], "submitted_at": _iso(req["created_at"])}


@router.get("/api/v1/office/establishment-registrations")
async def olre_list(actor: Actor = Depends(OLRE), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    rows = (await session.execute(select(registration_requests, establishments).join(
        establishments, establishments.c.establishment_id == registration_requests.c.establishment_id).where(
        establishments.c.office_id == office, registration_requests.c.state == "VERIFIED")
        .order_by(registration_requests.c.created_at.desc()))).mappings().all()
    out = []
    for r in rows:
        req = {k: r[k] for k in ("request_id", "state", "created_at")} | {"establishment_id": r["establishment_id"]}
        est = {k: r[k] for k in ("establishment_id", "legal_name", "registration_number", "coverage")}
        out.append(await _olre_view(session, req, est))
    return envelope(out)


@router.get("/api/v1/office/establishment-registrations/{reqId}/documents")
async def olre_documents(reqId: str, actor: Actor = Depends(OLRE), session: AsyncSession = Depends(db)) -> dict:
    req, est = await _registration(session, actor, reqId)
    evidence = req["evidence"] or {}
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="olre.documents_viewed",
                target_type="registration", target_id=reqId)
    await session.commit()
    return envelope({"request_id": reqId, "establishment": {"legal_name": est["legal_name"], "pan": _mask(est["pan"]), "gstin": _mask(est["gstin"]),
                                                            "office_id": est["office_id"], "pincode": est["pincode"]},
                     "documents": [{"type": "PAN", "verified_by": "mock Income Tax registry", "reference": req["verification_ref"]},
                                   *([{"type": "GSTIN", "verified_by": "mock GSTN", "reference": req["verification_ref"]}] if evidence.get("gstin") else []),
                                   {"type": "Registration application (Form 5A particulars)", "verified_by": "not yet scrutinised", "reference": reqId}],
                     "mock_verification": req["result_reason"], "note": "Synthetic documents; nothing real is stored."})


class Scrutiny(BaseModel):
    checks: list[str] = Field(min_length=1)
    note: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/office/establishment-registrations/{reqId}/scrutiny-notes", status_code=201)
async def olre_scrutiny(reqId: str, body: Scrutiny, actor: Actor = Depends(require_stakeholder("fo.da_compliance")),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        req, est = await _registration(session, actor, reqId)
        if req["state"] != "VERIFIED":
            raise Problem(409, "/problems/invalid-state", "The registration is not verified yet", f"State: {req['state']}.")
        note = {"by_role": actor.stakeholder, "checks": body.checks, "note": body.note, "at": datetime.now(UTC).isoformat()}
        existing = (await session.execute(select(registration_scrutiny).where(registration_scrutiny.c.request_id == reqId))).mappings().first()
        if existing:
            await session.execute(update(registration_scrutiny).where(registration_scrutiny.c.request_id == reqId).values(notes=[*existing["notes"], note]))
        else:
            n = (await session.execute(select(func.count()).select_from(registration_scrutiny))).scalar_one()
            await session.execute(insert(registration_scrutiny).values(
                request_id=reqId, efile_no=f"EFILE/{est['office_id']}/COMP/{datetime.now(UTC).year}/{n + 1:05d}", notes=[note],
                scrutinised_by=actor.subject))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="olre.scrutinised",
                    target_type="registration", target_id=reqId)
        view = await _olre_view(session, req, est)
    return envelope(view)


class Coverage(BaseModel):
    decision: str = Field(pattern="^(COVER|NOT_COVERED)$")
    coverage_date: date | None = None
    coverage_type: str = Field(default="STATUTORY", pattern="^(STATUTORY|VOLUNTARY)$")
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/establishment-registrations/{reqId}/coverage-decisions")
async def olre_coverage(reqId: str, body: Coverage, actor: Actor = Depends(require_stakeholder("fo.apfc")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        req, est = await _registration(session, actor, reqId)
        if not (await session.execute(select(registration_scrutiny.c.efile_no).where(registration_scrutiny.c.request_id == reqId))).first():
            raise Problem(409, "/problems/scrutiny-pending", "The DA (Compliance) has not scrutinised this registration yet")
        if est["coverage"]:
            raise Problem(409, "/problems/already-decided", "Coverage is already decided")
        if body.decision == "COVER" and (not body.coverage_date or body.coverage_date > date.today()):
            raise Problem(422, "/problems/validation", "Give a coverage date, not in the future")
        require_step_up(actor, "decide-coverage", reqId)
        coverage = {"decision": body.decision, "coverage_date": _iso(body.coverage_date), "coverage_type": body.coverage_type,
                    "reason": body.reason, "decided_by_role": actor.stakeholder, "at": datetime.now(UTC).isoformat()}
        values: dict[str, Any] = {"coverage": coverage}
        if body.decision == "COVER":
            values["coverage_date"] = body.coverage_date
        await session.execute(update(establishments).where(establishments.c.establishment_id == est["establishment_id"]).values(**values))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"olre.{body.decision.lower()}",
                    target_type="establishment", target_id=est["establishment_id"], detail=body.reason)
        view = await _olre_view(session, req, {**est, "coverage": coverage})
    return envelope(view)
