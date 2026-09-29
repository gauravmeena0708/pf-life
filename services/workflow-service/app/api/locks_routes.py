"""Phase 2, slice 5c: locks on a member's ledger and the signed documents an officer must open before acting.

A claim or transfer case holds a lock on the member's ledger while it is open; the lock goes with the case when
the case finishes. A lock whose owner is gone (a batch or process that died — the "concurrent claims already under
processing" message the field sees) or that has expired is orphaned: officers' decisions on that member are refused
until an OIC releases it with a reason (LockReleased.v1)."""
import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import case_documents, cases, document_views, ledger_locks, member_accounts, office_staff, subject_offices
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "workflow-service"
FINISHED = {"CLOSED", "REJECTED"}          # claim cases; engine cases use their definition's terminal states


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _finished(case: dict[str, Any]) -> bool:
    if case["state"] in FINISHED:
        return True
    if case.get("process"):
        from app.engine.engine import definitions
        definition = next((d for d in definitions() if d["process"] == case["process"]), None)
        return bool(definition) and case["state"] in definition.get("terminal_states", [])
    return False


async def acquire(session: AsyncSession, uan: str, scope: str, resource_key: str, owner_ref: str, office_id: str,
                  expires_at: datetime) -> None:
    await session.execute(insert(ledger_locks).values(
        lock_id=f"LCK-{secrets.token_hex(4).upper()}", uan=uan, lock_scope=scope, resource_key=resource_key, owner_ref=owner_ref,
        office_id=office_id, acquired_at=datetime.now(UTC), expires_at=expires_at))


async def uan_of(session: AsyncSession, case: dict[str, Any]) -> str | None:
    if case.get("claim_id"):
        return (await session.execute(select(member_accounts.c.uan).where(
            member_accounts.c.account_link_id == case["account_link_id"]))).scalar_one_or_none()
    subject = case.get("subject_ref") or ""
    return subject if subject.isdigit() and len(subject) == 12 else None


async def _locks(session: AsyncSession, uan: str) -> list[dict[str, Any]]:
    """The member's unreleased locks, each marked held / orphaned. A lock whose case has finished is released now."""
    rows = [dict(r) for r in (await session.execute(select(ledger_locks).where(
        ledger_locks.c.uan == uan, ledger_locks.c.released_at.is_(None)).order_by(ledger_locks.c.acquired_at))).mappings().all()]
    owners = {c["case_id"]: dict(c) for c in (await session.execute(select(cases).where(
        cases.c.case_id.in_([r["owner_ref"] for r in rows])))).mappings().all()} if rows else {}
    now, out = datetime.now(UTC), []
    for r in rows:
        owner = owners.get(r["owner_ref"])
        if owner and _finished(owner):
            await session.execute(update(ledger_locks).where(ledger_locks.c.lock_id == r["lock_id"]).values(
                released_at=now, released_by="system", release_reason=f"Case {owner['case_id']} finished ({owner['state']})."))
            continue
        why = None if owner and _aware(r["expires_at"]) > now else (
            "its owner is no longer running" if not owner else "it has expired while the case is still open")
        out.append({**r, "status": "ORPHANED" if why else "HELD", "orphaned_because": why,
                    "owner": {"case_id": owner["case_id"], "state": owner["state"], "kind": owner["kind"]} if owner else None})
    return out


async def ensure_unlocked(session: AsyncSession, case: dict[str, Any]) -> None:
    """Refuse a decision while an orphaned lock of another owner sits on the member's ledger."""
    uan = await uan_of(session, case)
    if not uan:
        return
    stale = [x for x in await _locks(session, uan) if x["status"] == "ORPHANED" and x["owner_ref"] != case["case_id"]]
    if stale:
        x = stale[0]
        raise Problem(409, "/problems/ledger-locked", "Unable to lock the member's ledger",
                      f"Lock {x['lock_id']} ({x['lock_scope'].replace('_', ' ').lower()}, held by {x['owner_ref']}) is orphaned: "
                      f"{x['orphaned_because']}. The officer in charge can release it after checking.", lock_id=x["lock_id"])


def _lock_view(x: dict[str, Any]) -> dict[str, Any]:
    iso = lambda v: _aware(v).isoformat() if v else None  # noqa: E731
    return {"lock_id": x["lock_id"], "uan": x["uan"], "lock_scope": x["lock_scope"], "resource_key": x["resource_key"],
            "owner_ref": x["owner_ref"], "owner": x.get("owner"), "status": x.get("status", "RELEASED"),
            "orphaned_because": x.get("orphaned_because"), "acquired_at": iso(x["acquired_at"]), "expires_at": iso(x["expires_at"]),
            "released_at": iso(x.get("released_at")), "released_by": x.get("released_by"), "release_reason": x.get("release_reason")}


async def _posting(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return dict(row)


LOCK_READERS = require_stakeholder("fo.oic", "fo.apfc", "fo.da_accounts", "fo.ss", "fo.ao")


@router.get("/api/v1/office/members/{uan}/locks")
async def member_locks(uan: str, actor: Actor = Depends(LOCK_READERS), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await _posting(session, actor)
        subject = (await session.execute(select(subject_offices).where(subject_offices.c.subject_ref == uan))).mappings().first()
        if not subject or staff["office_id"] not in (subject["office_id"], subject["zone_id"]):
            raise Problem(404, "/problems/not-found", "No member of your office with that UAN")
        held = await _locks(session, uan)
        released = (await session.execute(select(ledger_locks).where(ledger_locks.c.uan == uan, ledger_locks.c.released_at.is_not(None))
                                          .order_by(ledger_locks.c.released_at.desc()).limit(10))).mappings().all()
    return envelope({"uan": uan, "active": [_lock_view(x) for x in held], "recently_released": [_lock_view(dict(x)) for x in released]})


class Release(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/system/locks/{lockId}/release")
async def release(lockId: str, body: Release, actor: Actor = Depends(require_stakeholder("fo.oic")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await _posting(session, actor)
        row = (await session.execute(select(ledger_locks).where(ledger_locks.c.lock_id == lockId))).mappings().first()
        if not row or row["office_id"] != staff["office_id"]:
            raise Problem(404, "/problems/not-found", "Lock not found")
        if row["released_at"]:
            raise Problem(409, "/problems/already-released", "This lock is already released")
        current = next((x for x in await _locks(session, row["uan"]) if x["lock_id"] == lockId), None)
        if current is None:
            raise Problem(409, "/problems/already-released", "This lock went with its finished case")
        if current["status"] != "ORPHANED":
            raise Problem(409, "/problems/lock-in-use", "This lock is held by a case that is still running",
                          f"Case {current['owner_ref']} is {current['owner']['state']}; the lock goes when the case finishes.")
        require_step_up(actor, "release-lock", lockId)
        now = datetime.now(UTC)
        await session.execute(update(ledger_locks).where(ledger_locks.c.lock_id == lockId).values(
            released_at=now, released_by=actor.subject, release_reason=body.reason))
        await add_event(session, producer=PRODUCER, event_type="LockReleased.v1", aggregate_type="ledger_lock", aggregate_id=lockId,
                        correlation_id=actor.correlation_id, payload={"lock_id": lockId, "lock_scope": row["lock_scope"],
                                                                      "resource_key": row["resource_key"], "released_by": actor.subject,
                                                                      "reason": body.reason})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="lock.released",
                    target_type="ledger_lock", target_id=lockId, detail=body.reason)
    return envelope(_lock_view({**dict(row), "released_at": now, "released_by": actor.subject, "release_reason": body.reason}))


# ── signed documents on a case ────────────────────────────────────────────────────────────────────

async def add_document(session: AsyncSession, case: dict[str, Any], spec: dict[str, Any], actor: Actor, data: dict[str, Any]) -> None:
    content = {"document": spec["title"], "case_id": case["case_id"], "subject": case["subject_ref"],
               "signed_by_role": actor.stakeholder, "establishment_id": actor.establishment_id,
               "declaration": spec.get("declaration", ""), "fields": {k: v for k, v in (case.get("data") or {}).items()},
               "signer_note": data.get("note"), "signature": "DSC (mock) — synthetic demonstration, not a real signature"}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
    await session.execute(insert(case_documents).values(
        doc_id=f"DOC-{secrets.token_hex(4).upper()}", case_id=case["case_id"], doc_type=spec["type"], title=spec["title"],
        signed_by_role=actor.stakeholder, signed_by=actor.subject, sha256=digest, content=content))


async def ensure_viewed(session: AsyncSession, case: dict[str, Any], doc_type: str, actor: Actor) -> None:
    doc = (await session.execute(select(case_documents.c.doc_id, case_documents.c.title).where(
        case_documents.c.case_id == case["case_id"], case_documents.c.doc_type == doc_type)
        .order_by(case_documents.c.created_at.desc()))).first()
    if not doc:
        raise Problem(409, "/problems/document-missing", "The signed document is not on the case")
    seen = (await session.execute(select(document_views.c.id).where(document_views.c.doc_id == doc[0],
                                                                    document_views.c.viewer == actor.subject))).first()
    if not seen:
        raise Problem(409, "/problems/attestation-not-viewed", f"View the {doc[1].lower()} first",
                      "Open the signed document on the case; the action is enabled after you have seen it.", doc_id=doc[0])


async def documents_of(session: AsyncSession, case_id: str, viewer: str) -> list[dict[str, Any]]:
    docs = (await session.execute(select(case_documents).where(case_documents.c.case_id == case_id)
                                  .order_by(case_documents.c.created_at))).mappings().all()
    seen = set((await session.execute(select(document_views.c.doc_id).where(document_views.c.viewer == viewer))).scalars())
    return [{"doc_id": d["doc_id"], "doc_type": d["doc_type"], "title": d["title"], "signed_by_role": d["signed_by_role"],
             "sha256": d["sha256"], "viewed_by_you": d["doc_id"] in seen} for d in docs]


@router.post("/api/v1/office/cases/{caseId}/documents/{docId}/attestation-views", status_code=201)
async def view_document(caseId: str, docId: str, actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic")),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await _posting(session, actor)
        case = (await session.execute(select(cases).where(cases.c.case_id == caseId))).mappings().first()
        doc = (await session.execute(select(case_documents).where(case_documents.c.doc_id == docId,
                                                                  case_documents.c.case_id == caseId))).mappings().first()
        if not case or case["office_id"] != staff["office_id"] or not doc:
            raise Problem(404, "/problems/not-found", "Document not found")
        await session.execute(insert(document_views).values(doc_id=docId, viewer=actor.subject, viewer_role=actor.stakeholder))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="case.document_viewed",
                    target_type="case", target_id=caseId, detail=docId)
    return envelope({"doc_id": docId, "doc_type": doc["doc_type"], "title": doc["title"], "sha256": doc["sha256"],
                     "content": doc["content"], "viewed_by": actor.stakeholder, "viewed_at": datetime.now(UTC).isoformat()})


# ── the employer's pending approvals (Phase 2, slice 6b) ─────────────────────────────────────────

@router.get("/api/v1/employers/me/pending-approvals")
async def pending_approvals(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.operator", "employer.signatory")),
                            session: AsyncSession = Depends(db)) -> dict:
    """What waits for the establishment's authorised signatory (DSC / e-sign): Joint Declarations, Form 13 transfers
    to attest, exits marked by an operator — every engine step the signatory takes, in one list."""
    from app.engine.engine import _describe, definitions, next_op, roles_for
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment selected")
    rows = (await session.execute(select(cases, subject_offices.c.establishment_id).join(
        subject_offices, subject_offices.c.subject_ref == cases.c.subject_ref).where(
        cases.c.process.is_not(None), subject_offices.c.establishment_id == actor.establishment_id)
        .order_by(cases.c.created_at))).mappings().all()
    items = []
    for r in rows:
        definition = next((d for d in definitions() if d["process"] == r["process"]), None)
        op = next_op(definition, r["state"]) if definition else None
        if not op or op.get("scope") != "establishment" or "employer.signatory" not in roles_for(op, dict(r)):
            continue
        items.append({"case_id": r["case_id"], "title": definition["title"], "subject_ref": r["subject_ref"], "state": r["state"],
                      "action": op["name"], "operation": _describe(definition, op, dict(r)), "since": _aware(r["created_at"]).isoformat()
                      if r["created_at"] else None})
    return envelope({"establishment_id": actor.establishment_id, "items": items,
                     "note": "Member KYC approvals are listed separately (Member › Approve KYC)."})
