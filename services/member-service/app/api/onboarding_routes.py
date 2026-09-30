"""Phase 2, slice 2: employer registration of new joinees, Form 11, member KYC with employer approval, bulk
uploads, missing details, the active-members export, the UAN card and account readiness."""
import csv
import io
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.onboarding import decide_kyc, register, seed_kyc
from app.infra.db import sessions
from app.infra.tables import employments, kyc_requests, kyc_uploads, members
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")
MEMBER = require_stakeholder("member")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _establishment(actor: Actor, *grants: str) -> str:
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment selected")
    held = actor.claims.get("grants") or []
    if grants and not any(g in held for g in grants):
        require_grant(actor, grants[0])
    return actor.establishment_id


async def _establishment_name(session: AsyncSession, establishment_id: str) -> str:
    return (await session.execute(select(employments.c.establishment_name).where(
        employments.c.establishment_id == establishment_id).limit(1))).scalar_one_or_none() or establishment_id


async def _employee(session: AsyncSession, establishment_id: str, uan: str, active: bool = True) -> dict[str, Any]:
    q = select(members, employments.c.account_link_id, employments.c.date_of_joining, employments.c.date_of_exit, employments.c.form11).join(
        employments, employments.c.member_id == members.c.member_id).where(members.c.uan == uan, employments.c.establishment_id == establishment_id)
    if active:
        q = q.where(employments.c.date_of_exit.is_(None))
    row = (await session.execute(q)).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "No such employee of this establishment")
    return dict(row)


# ── registration and Form 11 ────────────────────────────────────────────────────────────────────

class Registration(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    gender: str = Field(pattern="^(MALE|FEMALE|TRANSGENDER)$")
    aadhaar: str = Field(pattern=r"^[0-9]{12}$")
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    date_of_joining: date
    existing_uan: str | None = Field(default=None, pattern=r"^[0-9]{12}$")


def _check_dates(body: Registration) -> None:
    today = datetime.now(UTC).date()
    if body.date_of_joining > today:
        raise Problem(422, "/problems/validation", "The date of joining cannot be in the future")
    age = body.date_of_joining.year - body.date_of_birth.year - ((body.date_of_joining.month, body.date_of_joining.day) < (body.date_of_birth.month, body.date_of_birth.day))
    if age < 14:
        raise Problem(422, "/problems/validation", "The joinee must be at least 14 years old on the date of joining")


@router.post("/api/v1/employers/me/members", status_code=201)
async def register_joinee(body: Registration, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = _establishment(actor, "ecr.prepare", "establishment.manage")
    _check_dates(body)
    async with session.begin():
        result = await register(session, establishment_id=est, establishment_name=await _establishment_name(session, est),
                                name=body.name.strip(), date_of_birth=body.date_of_birth, gender=body.gender, aadhaar=body.aadhaar,
                                mobile=body.mobile, date_of_joining=body.date_of_joining, existing_uan=body.existing_uan,
                                actor_subject=actor.subject, correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.registered",
                    target_type="member_account", target_id=result["account_link_id"], detail=result["uan"])
    return envelope({**result, "next_step": "File the joinee's Form 11 declaration; the member then activates the UAN."})


class BulkFile(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


@router.post("/api/v1/employers/me/members/bulk-registrations")
async def bulk_register(body: BulkFile, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """One joinee per line: name, date of birth, gender, Aadhaar, mobile, date of joining[, existing UAN]."""
    est = _establishment(actor, "ecr.prepare", "establishment.manage")
    results = []
    for n, row in enumerate(csv.reader(io.StringIO(body.content.strip())), start=1):
        if not row or row[0].strip().lower() == "name":
            continue
        try:
            reg = Registration(name=row[0].strip(), date_of_birth=row[1].strip(), gender=row[2].strip().upper(), aadhaar=row[3].strip(),
                               mobile=row[4].strip(), date_of_joining=row[5].strip(), existing_uan=(row[6].strip() or None) if len(row) > 6 else None)
            _check_dates(reg)
            async with session.begin():
                r = await register(session, establishment_id=est, establishment_name=await _establishment_name(session, est),
                                   name=reg.name, date_of_birth=reg.date_of_birth, gender=reg.gender, aadhaar=reg.aadhaar, mobile=reg.mobile,
                                   date_of_joining=reg.date_of_joining, existing_uan=reg.existing_uan, actor_subject=actor.subject,
                                   correlation_id=actor.correlation_id)
            results.append({"line": n, "status": "REGISTERED", "uan": r["uan"], "account_link_id": r["account_link_id"], "new_uan": r["new_uan"]})
        except Problem as p:
            results.append({"line": n, "status": "ERROR", "error": p.detail or p.title})
        except (ValueError, IndexError) as e:
            results.append({"line": n, "status": "ERROR", "error": f"Could not read the line: {str(e)[:160]}"})
    return envelope({"lines": len(results), "registered": sum(r["status"] == "REGISTERED" for r in results), "results": results})


class Form11(BaseModel):
    previous_pf_member: bool
    previous_eps_member: bool
    previous_uan: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    international_worker: bool = False
    country_of_origin: str | None = Field(default=None, max_length=60)
    declared_on: date


@router.post("/api/v1/employers/me/members/{uan}/declarations")
async def form11(uan: str, body: Form11, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = _establishment(actor, "ecr.prepare", "establishment.manage")
    if body.international_worker and not body.country_of_origin:
        raise Problem(422, "/problems/validation", "Country of origin is required for an international worker")
    async with session.begin():
        emp = await _employee(session, est, uan)
        if body.previous_pf_member and body.previous_uan and body.previous_uan != uan:
            raise Problem(422, "/problems/validation", "The previous UAN differs from the UAN this member ID is under",
                          "Register the joinee against the previous UAN instead.")
        await session.execute(update(employments).where(employments.c.account_link_id == emp["account_link_id"])
                              .values(form11={**body.model_dump(mode="json"), "recorded_by": actor.subject}))
    return envelope({"uan": uan, "account_link_id": emp["account_link_id"], "form11": body.model_dump(mode="json")})


# ── member KYC and the employer's approval ──────────────────────────────────────────────────────

async def _me(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(members).where(members.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Member not found")
    return dict(row)


def _request_view(r: Any) -> dict[str, Any]:
    return {"request_id": r["request_id"], "kyc_type": r["kyc_type"], "masked_value": r["masked_value"], "details": r["details"],
            "source": r["source"], "state": r["state"], "verification": r["verification"], "decision_note": r["decision_note"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None}


@router.get("/api/v1/members/me/kyc")
async def my_kyc(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    m = await _me(session, actor)
    kyc = m["kyc"] or {}
    requests = (await session.execute(select(kyc_requests).where(kyc_requests.c.member_id == m["member_id"])
                                      .order_by(kyc_requests.c.created_at.desc()))).mappings().all()
    return envelope({"aadhaar": kyc.get("aadhaar"), "pan": kyc.get("pan"), "bank": kyc.get("bank"),
                     "pan_masked": kyc.get("pan_masked"), "bank_ifsc": m["bank_ifsc"], "bank_account_last4": m["bank_account_last4"],
                     "requests": [_request_view(r) for r in requests]})


class PanInput(BaseModel):
    number: str = Field(pattern=r"^[A-Za-z]{5}[0-9]{4}[A-Za-z]$")


class BankInput(BaseModel):
    ifsc: str = Field(pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
    account_number: str = Field(pattern=r"^[0-9]{9,18}$")


@router.post("/api/v1/members/me/kyc/bank-accounts", status_code=201)
async def seed_bank(body: BankInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        m = await _me(session, actor)
        require_step_up(actor, "seed-kyc", m["member_id"])
        r = await seed_kyc(session, m, "BANK", body.model_dump(), "MEMBER", actor.subject)
    return envelope({k: v for k, v in r.items() if k not in ("member_id",)})


@router.post("/api/v1/members/me/kyc/{kycType}", status_code=201)
async def seed_other(kycType: str, body: PanInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    if kycType.upper() != "PAN":
        raise Problem(422, "/problems/validation", "Only PAN can be added here in this demonstration",
                      "Aadhaar is verified at registration; bank accounts use …/kyc/bank-accounts.")
    async with session.begin():
        m = await _me(session, actor)
        require_step_up(actor, "seed-kyc", m["member_id"])
        r = await seed_kyc(session, m, "PAN", body.model_dump(), "MEMBER", actor.subject)
    return envelope({k: v for k, v in r.items() if k not in ("member_id",)})


@router.get("/api/v1/employers/me/kyc-approvals")
async def kyc_queue(source: str | None = Query(default=None, pattern="^(MEMBER|EMPLOYER_BULK)$"), actor: Actor = Depends(EMPLOYER),
                    session: AsyncSession = Depends(db)) -> dict:
    est = _establishment(actor, "ecr.approve")
    q = select(kyc_requests, members.c.name).join(members, members.c.member_id == kyc_requests.c.member_id).where(
        kyc_requests.c.establishment_id == est, kyc_requests.c.state == "PENDING_EMPLOYER").order_by(kyc_requests.c.created_at)
    if source:
        q = q.where(kyc_requests.c.source == source)
    rows = (await session.execute(q)).mappings().all()
    return envelope([{**_request_view(r), "uan": r["uan"], "name": r["name"]} for r in rows])


class KycDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/employers/me/kyc-approvals/{requestId}/decisions")
async def kyc_decide(requestId: str, body: KycDecision, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = _establishment(actor, "ecr.approve")
    async with session.begin():
        r = (await session.execute(select(kyc_requests).where(kyc_requests.c.request_id == requestId).with_for_update())).mappings().first()
        if not r or r["establishment_id"] != est:
            raise Problem(404, "/problems/not-found", "KYC request not found")
        if r["state"] != "PENDING_EMPLOYER":
            raise Problem(409, "/problems/invalid-state", "This KYC request is already decided", f"Status: {r['state']}.")
        require_step_up(actor, "approve-kyc", requestId)                 # DSC / e-sign in the real portal
        result = await decide_kyc(session, dict(r), body.decision == "APPROVE", body.note, actor.subject, actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"kyc.{body.decision.lower()}",
                    target_type="kyc_request", target_id=requestId, detail=r["kyc_type"])
    return envelope(_request_view(result | {"created_at": r["created_at"]}))


@router.post("/api/v1/employers/me/kyc-bulk-uploads", status_code=201)
async def kyc_bulk(body: BulkFile, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """Member › KYC BULK: one line per member — UAN, PAN or BANK, number[, IFSC]. Accepted lines wait for the
    signatory under *Approve KYC pending for Digital Signature*; the rest are listed as errors."""
    est = _establishment(actor, "ecr.prepare", "establishment.manage")
    errors, accepted, lines = [], 0, 0
    for n, row in enumerate(csv.reader(io.StringIO(body.content.strip())), start=1):
        if not row or row[0].strip().lower() == "uan":
            continue
        lines += 1
        try:
            uan, kind, number = row[0].strip(), row[1].strip().upper(), row[2].strip()
            async with session.begin():
                m = await _employee(session, est, uan)
                fields = {"number": number} if kind == "PAN" else {"ifsc": row[3].strip(), "account_number": number}
                r = await seed_kyc(session, m, kind, fields, "EMPLOYER_BULK", actor.subject, est)
            if r["state"] == "FAILED_VERIFICATION":
                errors.append({"line": n, "uan": uan, "error": r["verification"].get("reason")})
            else:
                accepted += 1
        except Problem as p:
            errors.append({"line": n, "uan": row[0].strip() if row else "", "error": p.detail or p.title})
        except (ValueError, IndexError, KeyError):
            errors.append({"line": n, "uan": row[0].strip() if row else "", "error": "Line format: UAN, PAN|BANK, number[, IFSC]"})
    upload_id = f"KYCUP-{secrets.token_hex(4).upper()}"
    async with session.begin():
        await session.execute(insert(kyc_uploads).values(upload_id=upload_id, establishment_id=est, uploaded_by=actor.subject,
                                                         rows=lines, accepted=accepted, errors=errors))
    return envelope({"upload_id": upload_id, "lines": lines, "accepted": accepted, "errors": len(errors)})


@router.get("/api/v1/employers/me/kyc-bulk-uploads/{uploadId}/errors")
async def kyc_bulk_errors(uploadId: str, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    est = _establishment(actor)
    row = (await session.execute(select(kyc_uploads).where(kyc_uploads.c.upload_id == uploadId))).mappings().first()
    if not row or row["establishment_id"] != est:
        raise Problem(404, "/problems/not-found", "Upload not found")
    return envelope({"upload_id": uploadId, "lines": row["rows"], "accepted": row["accepted"], "errors": row["errors"]})


# ── missing details and the active-members export ──────────────────────────────────────────────

class MissingDetails(BaseModel):
    father_name: str | None = Field(default=None, min_length=2, max_length=120)
    mother_name: str | None = Field(default=None, min_length=2, max_length=120)
    marital_status: str | None = Field(default=None, pattern="^(SINGLE|MARRIED|WIDOWED|DIVORCED)$")
    nationality: str | None = Field(default=None, min_length=2, max_length=60)


@router.patch("/api/v1/employers/me/members/{uan}/profile")
async def fill_missing(uan: str, body: MissingDetails, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """Member › Missing details: the employer fills details the record lacks. A detail already present is changed
    only through a Joint Declaration."""
    est = _establishment(actor, "ecr.prepare", "establishment.manage")
    given = {k: v for k, v in body.model_dump().items() if v}
    if not given:
        raise Problem(422, "/problems/validation", "Nothing to fill in")
    async with session.begin():
        m = await _employee(session, est, uan)
        require_step_up(actor, "update-member-profile", uan)
        extra = dict(m["profile_extra"] or {})
        present = [k for k in given if extra.get(k)]
        if present:
            raise Problem(409, "/problems/detail-present", "These details are already recorded",
                          f"{', '.join(present)}: change them through a Joint Declaration.", fields=present)
        extra.update({k: v.upper() if k != "marital_status" else v for k, v in given.items()})
        await session.execute(update(members).where(members.c.member_id == m["member_id"]).values(profile_extra=extra))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.missing_details",
                    target_type="member", target_id=uan, detail=",".join(sorted(given)))
    return envelope({"uan": uan, "filled": sorted(given), "profile_extra": extra})



class LocationMapping(BaseModel):
    account_link_id: str = Field(min_length=3, max_length=40)
    branch_code: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    district: str = Field(min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")


@router.post("/api/v1/employers/me/members/{uan}/location-mappings")
async def map_location(uan: str, body: LocationMapping, actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """Member › Location mapping (P2.8e): which branch of the establishment the member works at, for the branch-wise
    returns and dashboards. Only the establishment's own, active member IDs."""
    est = _establishment(actor, "ecr.prepare", "members.manage")
    async with session.begin():
        m = await _employee(session, est, uan, active=False)    # an exited member ID is refused below, with the reason
        job = (await session.execute(select(employments).where(employments.c.account_link_id == body.account_link_id,
                                                               employments.c.member_id == m["member_id"],
                                                               employments.c.establishment_id == est))).mappings().first()
        if not job:
            raise Problem(404, "/problems/not-found", "No such member ID of this member in your establishment")
        if job["date_of_exit"]:
            raise Problem(409, "/problems/member-exited", "The member has left; a location is mapped for serving members only")
        location = {"branch_code": body.branch_code, "district": body.district.strip().upper(), "pincode": body.pincode}
        await session.execute(update(employments).where(employments.c.account_link_id == body.account_link_id).values(location=location))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.location_mapping",
                    target_type="member_account", target_id=body.account_link_id, detail=body.branch_code)
    return envelope({"uan": uan, "account_link_id": body.account_link_id, "location": location,
                     "previous": job["location"]})


REQUIRED_DETAILS = ("father_name", "marital_status", "nationality")


@router.get("/api/v1/employers/me/members/active-export")
async def active_export(actor: Actor = Depends(EMPLOYER), session: AsyncSession = Depends(db)) -> dict:
    """Dashboards › Active Members details (the portal gives it as a spreadsheet; the web page downloads CSV)."""
    est = _establishment(actor)
    rows = (await session.execute(select(members, employments.c.account_link_id, employments.c.date_of_joining, employments.c.form11).join(
        employments, employments.c.member_id == members.c.member_id).where(
        employments.c.establishment_id == est, employments.c.date_of_exit.is_(None)).order_by(members.c.name))).mappings().all()
    out = []
    for r in rows:
        kyc, extra = r["kyc"] or {}, r["profile_extra"] or {}
        out.append({"uan": r["uan"], "member_id": r["account_link_id"], "name": r["name"], "date_of_birth": r["date_of_birth"].isoformat(),
                    "gender": r["gender"], "date_of_joining": r["date_of_joining"].isoformat(), "aadhaar": kyc.get("aadhaar"),
                    "pan": kyc.get("pan"), "bank": kyc.get("bank"), "form11": "FILED" if r["form11"] else "MISSING",
                    "missing_details": [k for k in REQUIRED_DETAILS if not extra.get(k)]})
    return envelope({"establishment_id": est, "generated_at": datetime.now(UTC).isoformat(), "members": out})


# ── member: UAN card and account readiness ───────────────────────────────────────────────────────

@router.get("/api/v1/members/me/uan-card")
async def uan_card(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    m = await _me(session, actor)
    kyc, extra = m["kyc"] or {}, m["profile_extra"] or {}
    return envelope({"uan": m["uan"], "name": m["name"], "father_or_spouse_name": extra.get("father_name") or extra.get("spouse_name"),
                     "date_of_birth": m["date_of_birth"].isoformat(), "gender": m["gender"],
                     "kyc": {"aadhaar": kyc.get("aadhaar"), "pan": kyc.get("pan"), "bank": kyc.get("bank")},
                     "qr_payload": f"EPFO-POC|UAN:{m['uan']}|SYNTHETIC", "issued_by": "EPFO platform POC (synthetic demonstration)"})


@router.get("/api/v1/members/me/account-status")
async def account_status(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """Pre-flight before filing: blockers per member ID, as explicit codes."""
    m = await _me(session, actor)
    kyc = m["kyc"] or {}
    jobs = (await session.execute(select(employments).where(employments.c.member_id == m["member_id"])
                                  .order_by(employments.c.date_of_joining.desc()))).mappings().all()
    pending = (await session.execute(select(kyc_requests.c.kyc_type).where(kyc_requests.c.member_id == m["member_id"],
                                                                           kyc_requests.c.state == "PENDING_EMPLOYER"))).scalars().all()
    common = []
    if kyc.get("aadhaar") != "VERIFIED":
        common.append({"code": "KYC_AADHAAR_MISSING", "blocks": ["ALL_CLAIMS"], "fix": "Aadhaar must be verified and seeded."})
    if kyc.get("bank") != "VERIFIED":
        common.append({"code": "KYC_BANK_MISSING", "blocks": ["ALL_CLAIMS"], "fix": "Add a bank account under Manage › KYC; your employer approves it."})
    if kyc.get("pan") != "VERIFIED":
        common.append({"code": "KYC_PAN_MISSING", "blocks": [], "fix": "Without a verified PAN, TDS on a taxable withdrawal is at the higher rate."})
    if m["account_state"] == "FROZEN":
        common.append({"code": "ACCOUNT_FROZEN", "blocks": ["ALL_CLAIMS"], "fix": "The account is under verification by the field office."})
    common += [{"code": f"KYC_{t}_PENDING_APPROVAL", "blocks": [], "fix": "Waiting for your employer to approve."} for t in pending]
    accounts = []
    for j in jobs:
        own = []
        if j["transferred_to"]:
            own.append({"code": "TRANSFERRED", "blocks": ["ALL_CLAIMS"], "fix": f"The balance was moved to {j['transferred_to']}."})
        elif not j["date_of_exit"]:
            own.append({"code": "EXIT_NOT_MARKED", "blocks": ["FINAL_SETTLEMENT"], "fix": "Final settlement needs a date of exit."})
        blockers = common + own
        accounts.append({"account_link_id": j["account_link_id"], "establishment_name": j["establishment_name"], "blockers": blockers,
                         "ready_for": [k for k in ("ADVANCE", "FINAL_SETTLEMENT") if not any(
                             "ALL_CLAIMS" in b["blocks"] or k in b["blocks"] for b in blockers)]})
    return envelope({"uan": m["uan"], "accounts": accounts})


# ── office: member 360 view (jurisdiction and purpose checked, audited) ──────────────────────────

OFFICE_360 = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic", "fo.pro", "fo.da_pension", "fo.apfc_pension", "zo.rpfc1")


@router.get("/api/v1/office/members/{uan}")
async def member_360(uan: str, purpose: str = Query(min_length=10, max_length=300), actor: Actor = Depends(OFFICE_360),
                     session: AsyncSession = Depends(db)) -> dict:
    from app.infra.tables import member_applications, office_staff
    async with session.begin():
        office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
        m = (await session.execute(select(members).where(members.c.uan == uan))).mappings().first()
        jobs = [dict(j) for j in (await session.execute(select(employments).where(employments.c.member_id == (m["member_id"] if m else ""))
                                                        .order_by(employments.c.date_of_joining.desc()))).mappings().all()]
        zone = office and office.startswith("ZO")
        if not m or not office or not (zone or any(j["office_id"] == office for j in jobs)):
            raise Problem(404, "/problems/not-found", "No member of your office with that UAN")   # outside jurisdiction looks the same
        apps = (await session.execute(select(member_applications).where(member_applications.c.uan == uan)
                                      .order_by(member_applications.c.updated_at.desc()))).mappings().all()
        pending_kyc = (await session.execute(select(kyc_requests).where(kyc_requests.c.member_id == m["member_id"],
                                                                        kyc_requests.c.state == "PENDING_EMPLOYER"))).mappings().all()
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.viewed_360",
                    target_type="member", target_id=uan, detail=purpose)
    kyc = m["kyc"] or {}
    from app.domain.primary import aadhaar_set
    set_uans = sorted(u["uan"] for u in await aadhaar_set(session, uan))
    return envelope({"uan": uan, "name": m["name"], "date_of_birth": m["date_of_birth"].isoformat(), "gender": m["gender"],
                     "account_state": m["account_state"], "mobile_masked": m["mobile_masked"], "email_masked": m["email_masked"],
                     "kyc": {"aadhaar": kyc.get("aadhaar"), "pan": kyc.get("pan"), "bank": kyc.get("bank"), "bank_account_last4": m["bank_account_last4"]},
                     "profile_extra": m["profile_extra"] or {},
                     "member_ids": [{"account_link_id": j["account_link_id"], "primary": j["account_link_id"] == m["primary_account_link_id"],
                                     "establishment": j["establishment_name"], "office_id": j["office_id"],
                                     "date_of_joining": j["date_of_joining"].isoformat(), "date_of_exit": j["date_of_exit"].isoformat() if j["date_of_exit"] else None,
                                     "transferred_to": j["transferred_to"]} for j in jobs],
                     "applications": [{"application_id": a["application_id"], "title": a["title"], "state": a["state"], "pending": not a["terminal"]} for a in apps],
                     "pending_kyc": [{"request_id": r["request_id"], "kyc_type": r["kyc_type"]} for r in pending_kyc],
                     "primary_member_id": m["primary_account_link_id"], "aadhaar_set_uans": set_uans,
                     "viewed_for": purpose, "note": "This view is recorded in the audit log with its purpose."})


# ── the PRO counter: identity of the person filing a paper claim (Phase 2, slice 5b) ─────────────

class IdentityCheck(BaseModel):
    uan: str = Field(pattern=r"^[0-9]{12}$")
    name: str = Field(min_length=2, max_length=200)
    date_of_birth: date
    evidence: str = Field(pattern="^(AADHAAR_OTP|AADHAAR_BIOMETRIC|DOCUMENTS_SEEN)$")


@router.post("/api/v1/office/physical-claims/{intakeId}/identity-validations", status_code=201)
async def validate_identity(intakeId: str, body: IdentityCheck, actor: Actor = Depends(require_stakeholder("fo.pro_intake", "fo.diary")),
                            session: AsyncSession = Depends(db)) -> dict:
    """The name and date of birth on the paper form are matched with the member's record; the KYC status at this
    moment is kept with the result. Aadhaar is verified by the mock; nothing is sent anywhere."""
    from app.infra.tables import office_staff
    async with session.begin():
        office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
        m = (await session.execute(select(members).where(members.c.uan == body.uan))).mappings().first()
        offices = set() if not m else set((await session.execute(select(employments.c.office_id).where(
            employments.c.member_id == m["member_id"]))).scalars())
        if not m or not office or office not in offices:
            raise Problem(404, "/problems/not-found", "No member of your office with that UAN")
        kyc = m["kyc"] or {}
        checks = {"name": " ".join(body.name.upper().split()) == " ".join(m["name"].upper().split()),
                  "date_of_birth": body.date_of_birth == m["date_of_birth"], "aadhaar_verified": kyc.get("aadhaar") == "VERIFIED"}
        result = "MATCHED" if all(checks.values()) else "MISMATCH"
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="intake.identity_validated",
                    target_type="physical_intake", target_id=intakeId, detail=f"{body.uan} {result} {body.evidence}")
    return envelope({"intake_id": intakeId, "uan": body.uan, "result": result, "checks": checks, "evidence": body.evidence,
                     "kyc_snapshot": {"aadhaar": kyc.get("aadhaar"), "pan": kyc.get("pan"), "bank": kyc.get("bank"),
                                      "bank_account_last4": m["bank_account_last4"]},
                     "checked_at": datetime.now(UTC).isoformat(),
                     "next_step": "Hand the file to the dealing assistant." if result == "MATCHED"
                     else "Do not accept the claim until the mismatch is resolved (Joint Declaration or KYC update)."})
