"""international-service (Phase 2, slice 8c): Certificates of Coverage for workers posted abroad and the
international worker's own view. Illustrative throughout.

* The employer's authorised signatory applies for a CoC for a member posted to a country India has a
  social-security agreement with (the catalogue here is synthetic: real partner countries, illustrative terms),
  uploads the signed application, and downloads the certificate once the International Workers cell issues it.
  An issued CoC can be extended within the agreement's limit by a new application.
* The HO International Workers Unit and employers read the agreement catalogue.
* A foreign national employed in India sees how the scheme covers them: no agreement with their country here
  means contributions on the full wages and no withdrawal before leaving service as the scheme allows."""
import base64
import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import agreements, coc_applications, establishments, members, office_staff
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "international-service"
SIGNATORY = require_stakeholder("employer.signatory")
IW_CELL = require_stakeholder("fo.iw")
MAX_UPLOAD = 2 * 1024 * 1024


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def months_between(start: date, end: date) -> int:
    """Whole months a posting spans, counting a started month (1 Jan – 31 Dec is 12)."""
    return (end.year - start.year) * 12 + end.month - start.month + (1 if end.day >= start.day - 1 else 0)


def _agreement(a: Any) -> dict[str, Any]:
    return {"country": a["country"], "code": a["code"], "in_force_from": a["in_force_from"].isoformat(),
            "max_posting_months": a["max_posting_months"], "max_extension_months": a["max_extension_months"],
            "totalisation": a["totalisation"], "note": a["note"]}


def _view(r: Any, names: dict[str, str] | None = None) -> dict[str, Any]:
    return {"application_id": r["application_id"], "kind": r["kind"], "parent_id": r["parent_id"], "uan": r["uan"],
            "account_link_id": r["account_link_id"], "establishment_id": r["establishment_id"],
            "legal_name": (names or {}).get(r["establishment_id"]), "country": r["country"], "host_employer": r["host_employer"],
            "posting_from": r["posting_from"].isoformat(), "posting_to": r["posting_to"].isoformat(), "state": r["state"],
            "signed_upload": r["signed_upload"], "certificate_no": r["certificate_no"], "decision_reason": r["decision_reason"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None}


async def _names(session: AsyncSession) -> dict[str, str]:
    return dict((await session.execute(select(establishments.c.establishment_id, establishments.c.legal_name))).all())


async def _office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


async def _own(session: AsyncSession, application_id: str, actor: Actor, lock: bool = False) -> dict[str, Any]:
    q = select(coc_applications).where(coc_applications.c.application_id == application_id,
                                       coc_applications.c.establishment_id == (actor.establishment_id or "-"))
    row = (await session.execute(q)).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Application not found")
    return dict(row)


async def posting_problems(session: AsyncSession, account_link_id: str, country: str, start: date, end: date,
                           limit_months: int, exclude: str | None = None) -> list[str]:
    problems = []
    if end <= start:
        problems.append("The posting must end after it starts.")
    elif months_between(start, end) > limit_months:
        problems.append(f"The agreement allows a posting of at most {limit_months} months (illustrative).")
    overlapping = (await session.execute(select(coc_applications.c.application_id).where(
        coc_applications.c.account_link_id == account_link_id, coc_applications.c.country == country,
        coc_applications.c.state.in_(("AWAITING_SIGNED_UPLOAD", "SUBMITTED", "ISSUED")),
        coc_applications.c.posting_from <= end, coc_applications.c.posting_to >= start,
        coc_applications.c.application_id != (exclude or "-")))).scalars().first()
    if overlapping:
        problems.append(f"Certificate of Coverage application {overlapping} already covers part of this period.")
    return problems


# ── agreements ─────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/international/agreements")
async def list_agreements(actor: Actor = Depends(require_stakeholder("ho.iwu", "employer.signatory", "fo.iw")),
                          session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(agreements).order_by(agreements.c.country))).mappings().all()
    return envelope({"agreements": [_agreement(a) for a in rows],
                     "note": "Synthetic catalogue: India's agreement partners with illustrative terms, not the agreements' text."})


# ── Certificates of Coverage (employer) ─────────────────────────────────────────────────────────

class CocInput(BaseModel):
    uan: str = Field(pattern=r"^[0-9]{12}$")
    account_link_id: str = Field(min_length=3, max_length=40)
    country: str = Field(min_length=2, max_length=60)
    host_employer: str = Field(min_length=3, max_length=200)
    posting_from: date
    posting_to: date


@router.post("/api/v1/international/coc-applications", status_code=201)
async def apply(body: CocInput, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        m = (await session.execute(select(members).where(members.c.account_link_id == body.account_link_id,
                                                         members.c.uan == body.uan))).mappings().first()
        if not m or m["establishment_id"] != actor.establishment_id:
            raise Problem(404, "/problems/not-found", "No such member ID in your establishment")
        a = (await session.execute(select(agreements).where(agreements.c.country == body.country))).mappings().first()
        problems = []
        if m["date_of_exit"]:
            problems.append("The member has left your establishment; a CoC is for a worker you post abroad.")
        if m["international_worker"]:
            problems.append("A Certificate of Coverage is for workers posted from India; this member is an international worker.")
        if not a:
            problems.append(f"India has no social-security agreement with {body.country} in this catalogue; no CoC can be issued.")
        elif body.posting_from < a["in_force_from"]:
            problems.append(f"The agreement with {body.country} is in force from {a['in_force_from'].isoformat()}.")
        if body.posting_from < datetime.now(UTC).date() - timedelta(days=90):
            problems.append("Apply before the posting starts (at most 90 days late, illustrative).")
        if a:
            problems += await posting_problems(session, body.account_link_id, body.country, body.posting_from, body.posting_to,
                                               a["max_posting_months"])
        if problems:
            raise Problem(422, "/problems/coc-invalid", "The application cannot be made", " ".join(problems), errors=problems)
        office = (await session.execute(select(establishments.c.office_id).where(
            establishments.c.establishment_id == m["establishment_id"]))).scalar_one_or_none() or "-"
        application_id = f"COC-{secrets.token_hex(4).upper()}"
        await session.execute(insert(coc_applications).values(
            application_id=application_id, kind="NEW", establishment_id=m["establishment_id"], office_id=office, uan=body.uan,
            account_link_id=body.account_link_id, country=body.country, host_employer=body.host_employer.strip(),
            posting_from=body.posting_from, posting_to=body.posting_to, state="AWAITING_SIGNED_UPLOAD", created_by=actor.subject))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="coc.apply",
                    target_type="coc_application", target_id=application_id, detail=body.country)
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == application_id))).mappings().one()
    return envelope({**_view(row), "next_step": "Print, sign and upload the application (PDF)."})


@router.get("/api/v1/international/coc-applications")
async def my_applications(actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(coc_applications).where(coc_applications.c.establishment_id == (actor.establishment_id or "-"))
                                  .order_by(coc_applications.c.created_at.desc()))).mappings().all()
    names = await _names(session)
    return envelope([_view(r, names) for r in rows])


@router.get("/api/v1/international/coc-applications/{id}")
async def one_application(id: str, actor: Actor = Depends(require_stakeholder("employer.signatory", "fo.iw")),
                          session: AsyncSession = Depends(db)) -> dict:
    if actor.stakeholder == "fo.iw":
        office = await _office(session, actor)
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == id,
                                                                    coc_applications.c.office_id == office))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Application not found")
    else:
        row = await _own(session, id, actor)
    return envelope(_view(row, await _names(session)))


class SignedUpload(BaseModel):
    filename: str = Field(min_length=5, max_length=200, pattern=r"(?i)^[^/\\]+\.pdf$")
    content_base64: str = Field(min_length=8, max_length=3_000_000)


@router.post("/api/v1/international/coc-applications/{id}/signed-uploads")
async def upload_signed(id: str, body: SignedUpload, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except ValueError:
        raise Problem(422, "/problems/validation", "The file could not be read") from None
    if not content.startswith(b"%PDF") or len(content) > MAX_UPLOAD:
        raise Problem(422, "/problems/validation", "Upload the signed application as a PDF of at most 2 MB")
    async with session.begin():
        row = await _own(session, id, actor)
        if row["state"] not in ("AWAITING_SIGNED_UPLOAD", "SUBMITTED"):
            raise Problem(409, "/problems/invalid-state", "This application is already decided", f"Current status: {row['state']}.")
        doc = {"filename": body.filename, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        await session.execute(update(coc_applications).where(coc_applications.c.application_id == id).values(
            signed_upload=doc, state="SUBMITTED"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="coc.signed_upload",
                    target_type="coc_application", target_id=id, detail=doc["sha256"][:16])
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == id))).mappings().one()
    return envelope({**_view(row), "next_step": "The International Workers cell verifies the application and issues the certificate."})


class Extension(BaseModel):
    posting_to: date


@router.post("/api/v1/international/coc-applications/{id}/extensions", status_code=201)
async def extend(id: str, body: Extension, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        parent = await _own(session, id, actor)
        if parent["state"] != "ISSUED":
            raise Problem(409, "/problems/invalid-state", "Only an issued certificate can be extended", f"Current status: {parent['state']}.")
        a = (await session.execute(select(agreements).where(agreements.c.country == parent["country"]))).mappings().one()
        start = parent["posting_to"] + timedelta(days=1)
        problems = []
        if not a["max_extension_months"]:
            problems.append(f"The agreement with {parent['country']} allows no extension here (illustrative); the worker joins the host country's scheme.")
        elif months_between(parent["posting_from"], body.posting_to) > a["max_posting_months"] + a["max_extension_months"]:
            problems.append(f"With the extension the posting may last at most {a['max_posting_months'] + a['max_extension_months']} months (illustrative).")
        problems += await posting_problems(session, parent["account_link_id"], parent["country"], start, body.posting_to,
                                           a["max_posting_months"] + a["max_extension_months"])
        if problems:
            raise Problem(422, "/problems/coc-invalid", "The extension cannot be applied for", " ".join(problems), errors=problems)
        application_id = f"COC-{secrets.token_hex(4).upper()}"
        await session.execute(insert(coc_applications).values(
            application_id=application_id, kind="EXTENSION", parent_id=id, establishment_id=parent["establishment_id"],
            office_id=parent["office_id"], uan=parent["uan"], account_link_id=parent["account_link_id"], country=parent["country"],
            host_employer=parent["host_employer"], posting_from=start, posting_to=body.posting_to, state="AWAITING_SIGNED_UPLOAD",
            created_by=actor.subject))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="coc.extension",
                    target_type="coc_application", target_id=application_id, detail=id)
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == application_id))).mappings().one()
    return envelope({**_view(row), "next_step": "Upload the signed extension application (PDF)."})


@router.get("/api/v1/international/coc-applications/{id}/certificate")
async def certificate(id: str, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    row = await _own(session, id, actor)
    if row["state"] != "ISSUED":
        raise Problem(409, "/problems/invalid-state", "No certificate has been issued", f"Current status: {row['state']}.")
    m = (await session.execute(select(members).where(members.c.account_link_id == row["account_link_id"]))).mappings().one()
    names = await _names(session)
    text = (f"Certificate of Coverage {row['certificate_no']} (SYNTHETIC DEMONSTRATION). {m['name']} (UAN {row['uan']}), employed by "
            f"{names.get(row['establishment_id'], row['establishment_id'])}, posted to {row['host_employer']} in {row['country']} from "
            f"{row['posting_from'].isoformat()} to {row['posting_to'].isoformat()}, remains covered by the Indian scheme and is exempt from "
            f"the host country's social-security contributions for this period (illustrative).")
    seal = hashlib.sha256(f"{row['certificate_no']}|{row['uan']}|{row['posting_from']}|{row['posting_to']}".encode()).hexdigest()[:20]
    return envelope({"certificate_no": row["certificate_no"], "application_id": id, "name": m["name"], "uan": row["uan"],
                     "country": row["country"], "host_employer": row["host_employer"], "posting_from": row["posting_from"].isoformat(),
                     "posting_to": row["posting_to"].isoformat(), "issued_at": row["decided_at"].isoformat() if row["decided_at"] else None,
                     "issued_by_office": row["office_id"], "verification_code": seal, "text": text})


# ── the International Workers cell ──────────────────────────────────────────────────────────────

@router.get("/api/v1/office/international/coc-applications")
async def office_queue(actor: Actor = Depends(IW_CELL), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    rows = (await session.execute(select(coc_applications).where(coc_applications.c.office_id == office)
                                  .order_by(coc_applications.c.created_at.desc()))).mappings().all()
    names = await _names(session)
    return envelope([_view(r, names) for r in rows])


class CocDecision(BaseModel):
    decision: str = Field(pattern="^(ISSUE|REJECT)$")
    reason: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/office/international/coc-applications/{id}/decisions")
async def decide(id: str, body: CocDecision, actor: Actor = Depends(IW_CELL), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == id,
                                                                    coc_applications.c.office_id == office))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Application not found")
        if row["state"] != "SUBMITTED":
            raise Problem(409, "/problems/invalid-state", "Only a signed, submitted application can be decided",
                          f"Current status: {row['state']}.")
        require_step_up(actor, "decide-coc", id)
        values: dict[str, Any] = {"decision_reason": body.reason, "decided_by": actor.subject, "decided_at": datetime.now(UTC)}
        if body.decision == "ISSUE":
            code = (await session.execute(select(agreements.c.code).where(agreements.c.country == row["country"]))).scalar_one()
            values.update(state="ISSUED", certificate_no=f"IN-COC-{code}-{secrets.token_hex(3).upper()}")
        else:
            values.update(state="REJECTED")
        await session.execute(update(coc_applications).where(coc_applications.c.application_id == id).values(**values))
        if body.decision == "ISSUE":
            await add_event(session, producer=PRODUCER, event_type="CertificateOfCoverageIssued.v1", aggregate_type="coc_application",
                            aggregate_id=id, correlation_id=actor.correlation_id, payload={
                                "application_id": id, "certificate_no": values["certificate_no"], "uan": row["uan"],
                                "account_link_id": row["account_link_id"], "country": row["country"],
                                "posting_from": row["posting_from"].isoformat(), "posting_to": row["posting_to"].isoformat()})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="coc.decision",
                    target_type="coc_application", target_id=id, detail=body.decision)
        row = (await session.execute(select(coc_applications).where(coc_applications.c.application_id == id))).mappings().one()
    return envelope(_view(row, await _names(session)))


# ── the international worker ───────────────────────────────────────────────────────────────────

@router.get("/api/v1/members/me/international")
async def my_international(actor: Actor = Depends(require_stakeholder("intl_worker")), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(members).where(members.c.subject == actor.subject)
                                  .order_by(members.c.date_of_joining.desc()))).mappings().all()
    if not rows:
        raise Problem(404, "/problems/not-found", "No international-worker record found")
    m = rows[0]
    a = (await session.execute(select(agreements).where(agreements.c.country == (m["nationality"] or "-")))).mappings().first()
    names = await _names(session)
    if a:
        coverage = (f"India has a social-security agreement with {a['country']} (illustrative terms): if your home scheme issued you a "
                    f"Certificate of Coverage, you are exempt here for the posting; otherwise you contribute"
                    f"{', and periods of coverage in both countries can be totalised' if a['totalisation'] else ''}.")
    else:
        coverage = ("No social-security agreement with your country in this catalogue: you contribute on your full wages (no wage "
                    "ceiling) from the first day, and the PF is paid when you leave service as the scheme allows (illustrative).")
    return envelope({"uan": m["uan"], "name": m["name"], "international_worker": m["international_worker"],
                     "nationality": m["nationality"], "passport_masked": m["passport_masked"],
                     "employment": [{"account_link_id": r["account_link_id"], "establishment": names.get(r["establishment_id"], r["establishment_id"]),
                                     "date_of_joining": r["date_of_joining"].isoformat(),
                                     "date_of_exit": r["date_of_exit"].isoformat() if r["date_of_exit"] else None} for r in rows],
                     "agreement": _agreement(a) if a else None, "coverage": coverage})
