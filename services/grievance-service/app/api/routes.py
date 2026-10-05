"""grievance-service: grievances, replies, escalation and resolution (Journey C, init.md §7 "Grievance").

Who may read a grievance: the complainant; officers of its regional office (fo.pro) while it is with
the RO; the zone (zo.acc) for grievances of offices in its zone. Anyone else gets 404, so another
office cannot even learn that the grievance exists."""
import base64
import binascii
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import complainants, grievance_documents, grievance_entries, grievances, office_staff
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on

router = APIRouter()
PRODUCER = "grievance-service"
# Categories, service levels per tier and the reopen window come from the rule set in force (Policy administration).
NEXT_TIER = {"RO": "ZO", "ZO": "HO"}
NEXT_TIER_REVERSE = {v: k for k, v in NEXT_TIER.items()}
DOCUMENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
MAX_DOCUMENT_BYTES = 256 * 1024
MEMBER = require_stakeholder("member")
OFFICER = require_stakeholder("fo.pro", "zo.acc")
READERS = require_stakeholder("member", "fo.pro", "zo.acc")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class GrievanceInput(BaseModel):
    category: str
    subject: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    linked_claim_id: str | None = Field(default=None, max_length=40)


class MessageInput(BaseModel):
    body: str = Field(min_length=2, max_length=4000)


class EvidenceInput(BaseModel):
    evidence_refs: list[str] = Field(min_length=1, max_length=10)   # e.g. claim IDs, case IDs, journal IDs
    note: str = Field(min_length=2, max_length=1000)


class DocumentInput(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str
    content_base64: str


class EscalationInput(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class ResolutionInput(BaseModel):
    resolution: str = Field(min_length=10, max_length=4000)


class ReopenInput(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


# ── access ──────────────────────────────────────────────────────────────────────────────────────

async def posting(session: AsyncSession, actor: Actor) -> dict[str, Any] | None:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    return dict(row) if row else None


async def load(session: AsyncSession, grievance_id: str, actor: Actor, lock: bool = False) -> dict[str, Any]:
    """The grievance if this actor may see it; otherwise 404 (never 403, which would confirm it exists)."""
    q = select(grievances).where(grievances.c.grievance_id == grievance_id)
    if lock and session.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    g = (await session.execute(q)).mappings().first()
    if g:
        if actor.stakeholder == "member" and g["complainant_subject"] == actor.subject:
            return dict(g)
        staff = await posting(session, actor)
        if staff and staff["stakeholder"] == actor.stakeholder:
            if actor.stakeholder == "fo.pro" and staff["office_id"] == g["office_id"]:
                return dict(g)
            if actor.stakeholder == "zo.acc" and staff["office_id"] == g["zone_id"]:
                return dict(g)
    raise Problem(404, "/problems/not-found", "Grievance not found")


def handler_tier(actor: Actor) -> str:
    return {"fo.pro": "RO", "zo.acc": "ZO"}.get(actor.stakeholder, "")


def require_handler(g: dict[str, Any], actor: Actor) -> None:
    if handler_tier(actor) != g["tier"]:
        raise Problem(403, "/problems/not-your-tier", "This grievance is handled at another tier",
                      f"It is currently with the {g['tier']} tier.")


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────

async def entry(session: AsyncSession, g: dict[str, Any], kind: str, role: str, body: str, state: str | None = None,
                refs: list[str] | None = None) -> None:
    await session.execute(insert(grievance_entries).values(grievance_id=g["grievance_id"], kind=kind, author_role=role,
                                                           state=state, body=body, evidence_refs=refs))


async def move(session: AsyncSession, g: dict[str, Any], to: str, role: str, note: str, **values: Any) -> dict[str, Any]:
    result = await session.execute(update(grievances).where(
        grievances.c.grievance_id == g["grievance_id"], grievances.c.version == g["version"]).values(
        state=to, version=g["version"] + 1, **values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This grievance changed meanwhile", "Reload and try again.")
    await entry(session, g, "STATUS", role, note, state=to)
    return {**g, **values, "state": to, "version": g["version"] + 1}


async def notify(session: AsyncSession, g: dict[str, Any], template: str, correlation_id: str, **params: Any) -> None:
    await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=g["grievance_id"], correlation_id=correlation_id, payload={
                        "recipient_subject": g["complainant_subject"], "template": template,
                        "reference_id": g["grievance_id"], "params": params})


async def view(session: AsyncSession, g: dict[str, Any]) -> dict[str, Any]:
    entries = (await session.execute(select(grievance_entries).where(
        grievance_entries.c.grievance_id == g["grievance_id"]).order_by(grievance_entries.c.id))).mappings().all()
    docs = (await session.execute(select(grievance_documents.c.document_id, grievance_documents.c.filename,
                                         grievance_documents.c.content_type, grievance_documents.c.size_bytes,
                                         grievance_documents.c.sha256, grievance_documents.c.uploaded_at).where(
        grievance_documents.c.grievance_id == g["grievance_id"]))).mappings().all()
    return {
        "grievance_id": g["grievance_id"], "category": g["category"], "subject": g["subject_line"],
        "description": g["description"], "linked_claim_id": g["linked_claim_id"], "office_id": g["office_id"],
        "tier": g["tier"], "state": g["state"], "version": g["version"],
        "sla_due_at": g["sla_due_at"].isoformat() if g["sla_due_at"] else None,
        "resolution": g["resolution"], "resolved_at": g["resolved_at"].isoformat() if g["resolved_at"] else None,
        "entries": [{"at": e["at"].isoformat() if e["at"] else None, "kind": e["kind"], "by": e["author_role"],
                     "state": e["state"], "body": e["body"], "evidence_refs": e["evidence_refs"]} for e in entries],
        "documents": [{**dict(d), "uploaded_at": d["uploaded_at"].isoformat() if d["uploaded_at"] else None} for d in docs],
    }


async def settings(session: AsyncSession) -> dict[str, Any]:
    return (await rules_on(session, datetime.now(UTC).date()))["grievances"]


async def sla(session: AsyncSession, tier: str) -> datetime:
    return datetime.now(UTC) + timedelta(days=(await settings(session))["sla_days"][tier])


# ── member ──────────────────────────────────────────────────────────────────────────────────────

@router.post("/api/v1/members/me/grievances", status_code=201)
async def register(body: GrievanceInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        categories = (await settings(session))["categories"]
        if body.category not in categories:
            raise Problem(422, "/problems/validation", "Unknown category", "Choose one of: " + ", ".join(categories))
        home = (await session.execute(select(complainants).where(complainants.c.subject == actor.subject))).mappings().first()
        if not home:
            raise Problem(422, "/problems/no-home-office", "We could not find your regional office",
                          "Link your UAN to an establishment first.")
        gid = f"GRV-{secrets.token_hex(4).upper()}"
        await session.execute(insert(grievances).values(
            grievance_id=gid, complainant_subject=actor.subject, category=body.category, subject_line=body.subject,
            description=body.description, linked_claim_id=body.linked_claim_id, office_id=home["office_id"],
            zone_id=home["zone_id"], tier="RO", state="REGISTERED", version=1, sla_due_at=await sla(session, "RO")))
        g = dict((await session.execute(select(grievances).where(grievances.c.grievance_id == gid))).mappings().one())
        await entry(session, g, "STATUS", "member", "Grievance registered.", state="REGISTERED")
        await add_event(session, producer=PRODUCER, event_type="GrievanceRegistered.v1", aggregate_type="grievance",
                        aggregate_id=gid, correlation_id=actor.correlation_id, payload={
                            "grievance_id": gid, "category": body.category, "office_id": home["office_id"],
                            "linked_claim_id": body.linked_claim_id or ""})
        g = await move(session, g, "ROUTED", "system", f"Sent to your regional office {home['office_id']}.")
        await notify(session, g, "GRIEVANCE_REGISTERED", actor.correlation_id, office_id=home["office_id"])
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.register",
                    target_type="grievance", target_id=gid, detail=body.category)
        result = await view(session, g)
    return envelope(result)


@router.get("/api/v1/members/me/grievances")
async def my_grievances(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(grievances).where(grievances.c.complainant_subject == actor.subject)
                                  .order_by(grievances.c.created_at.desc()))).mappings().all()
    return envelope([{"grievance_id": r["grievance_id"], "category": r["category"], "subject": r["subject_line"],
                      "state": r["state"], "tier": r["tier"], "linked_claim_id": r["linked_claim_id"],
                      "resolution": r["resolution"],                     # the member's own answer (P2.24 review)
                      "sla_due_at": r["sla_due_at"].isoformat() if r["sla_due_at"] else None,
                      "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows])


@router.get("/api/v1/grievances/{grievance_id}")
async def get_grievance(grievance_id: str, actor: Actor = Depends(READERS), session: AsyncSession = Depends(db)) -> dict:
    return envelope(await view(session, await load(session, grievance_id, actor)))


@router.post("/api/v1/grievances/{grievance_id}/documents", status_code=201)
async def add_document(grievance_id: str, body: DocumentInput, actor: Actor = Depends(MEMBER),
                       session: AsyncSession = Depends(db)) -> dict:
    if body.content_type not in DOCUMENT_TYPES:
        raise Problem(415, "/problems/unsupported-document", "This file type is not accepted",
                      "Upload a PDF, PNG, JPEG or plain-text file.")
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise Problem(422, "/problems/validation", "The file could not be read", "Send the file as base64.") from None
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise Problem(413, "/problems/document-too-large", "The file is empty or too large", "Keep it under 256 KB.")
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        if g["state"] in ("RESOLVED", "CLOSED"):
            raise Problem(409, "/problems/invalid-state", "This grievance is closed to new documents")
        doc_id = f"DOC-{secrets.token_hex(4).upper()}"
        digest = hashlib.sha256(content).hexdigest()
        await session.execute(insert(grievance_documents).values(
            document_id=doc_id, grievance_id=grievance_id, filename=body.filename, content_type=body.content_type,
            size_bytes=len(content), sha256=digest, content=content))
        await entry(session, g, "DOCUMENT", "member", f"Document attached: {body.filename}", refs=[doc_id])
    return envelope({"document_id": doc_id, "sha256": digest, "size_bytes": len(content)})


@router.post("/api/v1/grievances/{grievance_id}/messages", status_code=201)
async def message(grievance_id: str, body: MessageInput, actor: Actor = Depends(READERS),
                  session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        if g["state"] == "CLOSED":
            raise Problem(409, "/problems/invalid-state", "This grievance is closed")
        if actor.stakeholder == "member":
            await entry(session, g, "MESSAGE", "member", body.body)
        else:
            require_handler(g, actor)
            await entry(session, g, "MESSAGE", actor.stakeholder, body.body)
            # The handling officer's first reply takes the grievance up (ROUTED / ESCALATED / REOPEN_REQUESTED → IN_PROGRESS).
            if g["state"] in ("ROUTED", "ESCALATED", "REOPEN_REQUESTED"):
                g = await move(session, g, "IN_PROGRESS", actor.stakeholder, f"Taken up at the {g['tier']} tier.")
            await notify(session, g, "GRIEVANCE_REPLY", actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.message",
                    target_type="grievance", target_id=grievance_id)
        result = await view(session, g)
    return envelope(result)


@router.post("/api/v1/grievances/{grievance_id}/evidence-links", status_code=201)
async def link_evidence(grievance_id: str, body: EvidenceInput, actor: Actor = Depends(require_stakeholder("fo.pro")),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        require_handler(g, actor)
        await entry(session, g, "EVIDENCE", actor.stakeholder, body.note, refs=body.evidence_refs)
        result = await view(session, g)
    return envelope(result)


@router.post("/api/v1/grievances/{grievance_id}/escalations")
async def escalate(grievance_id: str, body: EscalationInput,
                   actor: Actor = Depends(require_stakeholder("member", "fo.pro", "zo.acc")),
                   session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        if actor.stakeholder != "member":
            require_handler(g, actor)
        if g["state"] not in ("ROUTED", "IN_PROGRESS"):
            raise Problem(409, "/problems/invalid-state", "Only an open grievance can be escalated",
                          f"Current status: {g['state']}.")
        to_tier = NEXT_TIER.get(g["tier"])
        if not to_tier:
            raise Problem(409, "/problems/top-tier", "Head Office is the top tier", "This grievance cannot go higher.")
        g = await move(session, g, "ESCALATED", actor.stakeholder, f"Escalated from {g['tier']} to {to_tier}: {body.reason}",
                       tier=to_tier, sla_due_at=await sla(session, to_tier))
        await add_event(session, producer=PRODUCER, event_type="GrievanceEscalated.v1", aggregate_type="grievance",
                        aggregate_id=grievance_id, correlation_id=actor.correlation_id, payload={
                            "grievance_id": grievance_id, "from_tier": NEXT_TIER_REVERSE[to_tier], "to_tier": to_tier,
                            "office_id": g["zone_id"] if to_tier == "ZO" else "HO"})
        await notify(session, g, "GRIEVANCE_ESCALATED", actor.correlation_id, tier=to_tier)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.escalate",
                    target_type="grievance", target_id=grievance_id, detail=to_tier)
        result = await view(session, g)
    return envelope(result)


@router.post("/api/v1/grievances/{grievance_id}/resolution")
async def resolve(grievance_id: str, body: ResolutionInput, actor: Actor = Depends(OFFICER),
                  session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        require_handler(g, actor)
        require_step_up(actor, "resolve-grievance", grievance_id, g["version"])
        if g["state"] != "IN_PROGRESS":
            raise Problem(409, "/problems/invalid-state", "Take the grievance up before resolving it",
                          f"Current status: {g['state']}.")
        now = datetime.now(UTC)
        due = g["sla_due_at"] if g["sla_due_at"].tzinfo else g["sla_due_at"].replace(tzinfo=UTC)
        g = await move(session, g, "RESOLVED", actor.stakeholder, f"Resolved: {body.resolution}",
                       resolution=body.resolution, resolved_at=now)
        await add_event(session, producer=PRODUCER, event_type="GrievanceResolved.v1", aggregate_type="grievance",
                        aggregate_id=grievance_id, correlation_id=actor.correlation_id, payload={
                            "grievance_id": grievance_id, "office_id": g["office_id"], "tier": g["tier"],
                            "within_sla": now <= due})
        await notify(session, g, "GRIEVANCE_RESOLVED", actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="grievance.resolve",
                    target_type="grievance", target_id=grievance_id)
        result = await view(session, g)
    return envelope(result)


@router.post("/api/v1/grievances/{grievance_id}/reopen-requests")
async def reopen(grievance_id: str, body: ReopenInput, actor: Actor = Depends(MEMBER),
                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        g = await load(session, grievance_id, actor, lock=True)
        if g["state"] != "RESOLVED":
            raise Problem(409, "/problems/invalid-state", "Only a resolved grievance can be reopened")
        resolved = g["resolved_at"] if g["resolved_at"].tzinfo else g["resolved_at"].replace(tzinfo=UTC)
        window = (await settings(session))["reopen_window_days"]
        if datetime.now(UTC) > resolved + timedelta(days=window):
            raise Problem(409, "/problems/reopen-window-closed", "The reopen window has passed",
                          f"A grievance can be reopened within {window} days; please file a new one.")
        g = await move(session, g, "REOPEN_REQUESTED", "member", f"Reopen requested: {body.reason}", sla_due_at=await sla(session, g["tier"]))
        result = await view(session, g)
    return envelope(result)

