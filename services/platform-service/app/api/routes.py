"""platform-service: policy administration (rule sets).

A drafter (ho.acc_hq) copies a rule set, changes it, sets an effective date and submits it once every check
passes. The CPFC (ho.cpfc) sees exactly what changed and worked examples of the effect, then publishes it
with a one-time code (maker ≠ checker) or returns it. Publishing emits PolicyPublished.v1 with the whole
document; each service applies the version in force on the relevant date. Published versions never change."""
import hashlib
import json
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.policy import diff, preview
from app.infra.db import sessions
from app.infra.tables import rule_sets
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import baseline, policy_rules, validate

router = APIRouter()
PRODUCER = "platform-service"
DRAFTERS = require_stakeholder("ho.acc_hq")
APPROVERS = require_stakeholder("ho.cpfc")
READERS = require_stakeholder("ho.acc_hq", "ho.cpfc", "ho.pension", "ho.audit")
VERSION_NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,58}$")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class DraftInput(BaseModel):
    base_version_id: str
    rule_version: str
    effective_from: date
    change_note: str = Field(min_length=10, max_length=2000)
    document: dict[str, Any]


class DraftEdit(BaseModel):
    rule_version: str | None = None
    effective_from: date | None = None
    change_note: str | None = Field(default=None, min_length=10, max_length=2000)
    document: dict[str, Any] | None = None


class Decision(BaseModel):
    decision: str                      # APPROVE | RETURN
    note: str = Field(min_length=10, max_length=2000)


def today() -> date:
    return datetime.now(UTC).date()


def sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def published(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(rule_sets).where(rule_sets.c.status == "PUBLISHED")
                                  .order_by(rule_sets.c.effective_from))).mappings().all()
    return [dict(r) for r in rows]


def standing(row: dict[str, Any], live: list[dict[str, Any]], on: date) -> str:
    """IN_FORCE / SCHEDULED / SUPERSEDED for published versions; the workflow status otherwise."""
    if row["status"] != "PUBLISHED":
        return row["status"]
    if any(r["effective_from"] == row["effective_from"] and later_published(r, row) for r in live):
        return "SUPERSEDED"                                     # a same-day correction replaced it
    in_force = max((r for r in live if r["effective_from"] <= on), key=published_order, default=None)
    if row["effective_from"] > on:
        return "SCHEDULED"
    return "IN_FORCE" if in_force and in_force["version_id"] == row["version_id"] else "SUPERSEDED"


def published_order(r: dict[str, Any]) -> tuple:
    return (r["effective_from"], r["decided_at"] or datetime.min.replace(tzinfo=UTC))


def later_published(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a["version_id"] != b["version_id"] and published_order(a) > published_order(b)


def summary(row: dict[str, Any], live: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version_id": row["version_id"], "rule_version": row["rule_version"],
            "effective_from": row["effective_from"].isoformat(), "status": standing(row, live, today()),
            "change_note": row["change_note"], "base_version_id": row["base_version_id"], "version": row["version"],
            "drafted_by": row["drafted_by"], "decided_by": row["decided_by"],
            "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None}


async def load(session: AsyncSession, version_id: str) -> dict[str, Any]:
    row = (await session.execute(select(rule_sets).where(rule_sets.c.version_id == version_id))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Rule set not found")
    return dict(row)


SECTIONS = ("interest", "tds", "pension", "death_claims", "late_payment", "vishwas", "higher_pension", "international_workers", "vigilance", "inoperative_accounts", "voluntary_coverage", "oversight_periods", "investment_pattern", "dr_and_training", "exempted_establishments", "pmvbry", "notifications", "compliance_proceedings")


def complete(document: dict[str, Any]) -> dict[str, Any]:
    """A version published before a section existed used the baseline's; show and copy it explicitly."""
    return {**{k: baseline()[k] for k in SECTIONS if k not in document}, **document}


def stamp(document: dict[str, Any], rule_version: str, effective_from: date) -> dict[str, Any]:
    return {**complete(document), "ILLUSTRATIVE_ONLY": True, "rule_version": rule_version, "effective_from": effective_from.isoformat()}


async def check_names(session: AsyncSession, rule_version: str, effective_from: date, own_id: str | None) -> None:
    if not VERSION_NAME.match(rule_version):
        raise Problem(422, "/problems/validation", "Invalid version name", "Use lower-case letters, digits, dots and hyphens.")
    clash = (await session.execute(select(rule_sets.c.version_id).where(rule_sets.c.rule_version == rule_version))).scalar_one_or_none()
    if clash and clash != own_id:
        raise Problem(409, "/problems/duplicate-version", "That version name is already used")
    if effective_from < today():
        raise Problem(422, "/problems/backdated", "A rule set cannot take effect in the past",
                      "Decisions already made keep the rules they were made under; choose today or a later date.")


async def refuse_if_overridden(session: AsyncSession, row: dict[str, Any]) -> None:
    """A version already scheduled for a later date may have been copied from older rules; from its date it would
    silently undo this change. Refuse unless each later version already carries the change, so the drafter first
    amends the scheduled version (a same-day correction) or prepares one combined version."""
    base = complete((await load(session, row["base_version_id"]))["document"] if row["base_version_id"] else row["document"])
    changes = [c for c in diff(base, row["document"]) if c["path"] not in ("rule_version", "effective_from")]
    live = await published(session)
    effective = {}                                              # the version that counts on each later date
    for r in live:
        if r["effective_from"] > row["effective_from"] and (r["effective_from"] not in effective
                                                            or later_published(r, effective[r["effective_from"]])):
            effective[r["effective_from"]] = r
    for later in sorted(effective.values(), key=published_order):
        if any(value_at(later["document"], c["path"]) != c["after"] for c in changes):
            raise Problem(409, "/problems/later-version-scheduled", "A later version is already scheduled",
                          f"{later['rule_version']} takes effect on {later['effective_from'].isoformat()} and does not contain this "
                          "change, so it would undo it from that date. Amend that version first (same date), put both changes "
                          "into one version, or choose a date after it.", scheduled_version=later["rule_version"])


def value_at(document: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(document, dict):
            return None
        document = document.get(key)
    return document


# ── routes ──────────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/ho/config/rule-sets")
async def list_rule_sets(actor: Actor = Depends(READERS), session: AsyncSession = Depends(db)) -> dict:
    rows = [dict(r) for r in (await session.execute(select(rule_sets).order_by(rule_sets.c.effective_from.desc(),
                                                                                rule_sets.c.created_at.desc()))).mappings().all()]
    live = [r for r in rows if r["status"] == "PUBLISHED"]
    return envelope({"today": today().isoformat(), "items": [summary(r, live) for r in rows]})


@router.get("/api/v1/ho/config/rule-sets/{version_id}")
async def get_rule_set(version_id: str, actor: Actor = Depends(READERS), session: AsyncSession = Depends(db)) -> dict:
    row = await load(session, version_id)
    base = complete((await load(session, row["base_version_id"]))["document"] if row["base_version_id"] else row["document"])
    live = await published(session)
    checks = validate(row["document"])
    # Worked examples only make sense for a rule set that passes its checks (a draft may be half-edited).
    return envelope({**summary(row, live), "document": complete(row["document"]), "checks": checks,
                     "changes": diff(base, complete(row["document"])), "preview": None if checks else preview(base, row["document"]),
                     "decision_note": row["decision_note"]})


@router.post("/api/v1/ho/config/rule-sets", status_code=201)
async def create_draft(body: DraftInput, actor: Actor = Depends(DRAFTERS), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        base = await load(session, body.base_version_id)
        await check_names(session, body.rule_version, body.effective_from, None)
        version_id = f"POL-{secrets.token_hex(4).upper()}"
        await session.execute(insert(rule_sets).values(
            version_id=version_id, rule_version=body.rule_version, effective_from=body.effective_from, status="DRAFT",
            document=stamp(body.document, body.rule_version, body.effective_from), base_version_id=base["version_id"],
            change_note=body.change_note, drafted_by=actor.subject, version=1))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="policy.draft",
                    target_type="rule_set", target_id=version_id, detail=body.rule_version)
    return await get_rule_set(version_id, actor, session)


@router.put("/api/v1/ho/config/rule-sets/{version_id}")
async def edit_draft(version_id: str, body: DraftEdit, actor: Actor = Depends(DRAFTERS),
                     if_match: str | None = Header(default=None, alias="If-Match"), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        row = await load(session, version_id)
        if row["status"] != "DRAFT":
            raise Problem(409, "/problems/invalid-state", "Only a draft can be edited", f"Status: {row['status']}.")
        if if_match is None or if_match.strip('"') != str(row["version"]):
            raise Problem(412, "/problems/version-mismatch", "This draft changed meanwhile", "Reload it and apply your change again.")
        name = body.rule_version or row["rule_version"]
        effective = body.effective_from or row["effective_from"]
        await check_names(session, name, effective, version_id)
        document = stamp(body.document if body.document is not None else row["document"], name, effective)
        await session.execute(update(rule_sets).where(rule_sets.c.version_id == version_id).values(
            rule_version=name, effective_from=effective, document=document, change_note=body.change_note or row["change_note"],
            version=row["version"] + 1))
    return await get_rule_set(version_id, actor, session)


@router.post("/api/v1/ho/config/rule-sets/{version_id}/submissions")
async def submit(version_id: str, actor: Actor = Depends(DRAFTERS), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        row = await load(session, version_id)
        if row["status"] != "DRAFT":
            raise Problem(409, "/problems/invalid-state", "Only a draft can be submitted", f"Status: {row['status']}.")
        problems = validate(row["document"])
        if problems:
            raise Problem(422, "/problems/policy-checks-failed", "The rule set does not pass its checks",
                          "Fix every item listed in 'problems' before submitting.", problems=problems)
        await check_names(session, row["rule_version"], row["effective_from"], version_id)
        await refuse_if_overridden(session, row)
        await session.execute(update(rule_sets).where(rule_sets.c.version_id == version_id).values(
            status="SUBMITTED", submitted_by=actor.subject, submitted_at=datetime.now(UTC), version=row["version"] + 1))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="policy.submit",
                    target_type="rule_set", target_id=version_id)
    return await get_rule_set(version_id, actor, session)


@router.post("/api/v1/ho/config/rule-sets/{version_id}/decisions")
async def decide(version_id: str, body: Decision, actor: Actor = Depends(APPROVERS), session: AsyncSession = Depends(db)) -> dict:
    if body.decision not in ("APPROVE", "RETURN"):
        raise Problem(422, "/problems/validation", "decision must be APPROVE or RETURN")
    async with session.begin():
        row = await load(session, version_id)
        require_step_up(actor, "publish-policy", version_id, row["version"])
        if row["status"] != "SUBMITTED":
            raise Problem(409, "/problems/invalid-state", "Only a submitted rule set can be decided", f"Status: {row['status']}.")
        if actor.subject in (row["drafted_by"], row["submitted_by"]):
            raise Problem(403, "/problems/separation-of-duties", "You cannot approve a rule set you drafted or submitted")
        if body.decision == "RETURN":
            await session.execute(update(rule_sets).where(rule_sets.c.version_id == version_id).values(
                status="DRAFT", decided_by=actor.subject, decision_note=body.note, decided_at=datetime.now(UTC),
                version=row["version"] + 1))
        else:
            problems = validate(row["document"])                 # checked again: the rules may have tightened meanwhile
            if problems:
                raise Problem(422, "/problems/policy-checks-failed", "The rule set does not pass its checks", problems=problems)
            if row["effective_from"] < today():
                raise Problem(422, "/problems/backdated", "The effective date has passed",
                              "Return it so the drafter can choose a new date.")
            await refuse_if_overridden(session, row)
            await session.execute(update(rule_sets).where(rule_sets.c.version_id == version_id).values(
                status="PUBLISHED", decided_by=actor.subject, decision_note=body.note, decided_at=datetime.now(UTC),
                version=row["version"] + 1))
            await session.execute(insert(policy_rules).values(rule_version=row["rule_version"],
                                                           effective_from=row["effective_from"], document=row["document"]))
            await add_event(session, producer=PRODUCER, event_type="PolicyPublished.v1", aggregate_type="rule_set",
                            aggregate_id=version_id, correlation_id=actor.correlation_id, payload={
                                "version_id": version_id, "rule_version": row["rule_version"],
                                "effective_from": row["effective_from"].isoformat(), "document_sha256": sha256(row["document"]),
                                "approved_by_role": actor.stakeholder, "document": row["document"]})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"policy.{body.decision.lower()}", target_type="rule_set", target_id=version_id, detail=body.note)
    return await get_rule_set(version_id, actor, session)


@router.get("/api/v1/public/policy/current")
async def current_policy(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    live = await published(session)
    in_force = max((r for r in live if r["effective_from"] <= today()), key=lambda r: r["effective_from"], default=None)
    doc = in_force["document"] if in_force else baseline()
    scheduled = [{"rule_version": r["rule_version"], "effective_from": r["effective_from"].isoformat()}
                 for r in live if r["effective_from"] > today()]
    return envelope({"rule_version": doc["rule_version"], "effective_from": doc["effective_from"],
                     "illustrative_only": True, "contribution": doc["contribution"],
                     "claim_types": {k: {f: v[f] for f in ("form_type", "label", "plain_rule") if f in v}
                                     for k, v in doc["claims"]["types"].items() if not v.get("retired")},
                     "grievance_categories": doc["grievances"]["categories"],
                     "scheduled": scheduled})
