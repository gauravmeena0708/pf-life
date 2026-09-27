"""Tier-2 process engine (ADR-0005). Executes the YAML definitions in config/processes.

For every operation in a definition the engine registers a route and enforces, generically:
form rules, allowed roles, office jurisdiction, the approval chain in order, one action per officer per
round (maker ≠ checker), step-up bound to the subject, and state preconditions. Each state change emits
ProcessTransitioned.v1; the owning service reacts to it and publishes its own domain events."""
import os
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import case_actions, cases, office_staff, subject_offices
from epfo_auth import Actor, require_actor, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

PROCESSES_DIR = Path(os.getenv("PROCESSES_DIR", "/srv/processes"))
PRODUCER = "workflow-service"
SLA_DAYS = 10


@lru_cache(maxsize=1)
def definitions() -> tuple[dict[str, Any], ...]:
    folder = PROCESSES_DIR if PROCESSES_DIR.exists() else Path(__file__).resolve().parents[4] / "config" / "processes"
    loaded = tuple(yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.yaml")))
    for d in loaded:                     # fail at startup, not on the first request, if a definition is inconsistent
        names = {op["name"] for op in d["operations"]}
        for op in d["operations"]:
            if op.get("queue") and op["queue"] not in names:
                raise ValueError(f"{d['process']}: operation {op['name']} queues unknown operation {op['queue']}")
            if not (op.get("roles") or op.get("chain")):
                raise ValueError(f"{d['process']}: operation {op['name']} has no roles or chain")
    return loaded


def operations() -> list[str]:
    """Catalogue operations served by the engine (used by the gateway route builder and the docs)."""
    return [op["operation"] for d in definitions() for op in d["operations"]]


def validate_form(form: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    clean, problems = {}, []
    for name, rule in form.items():
        value = body.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{name} is required")
            continue
        if "enum" in rule and value not in rule["enum"]:
            problems.append(f"{name} must be one of {', '.join(map(str, rule['enum']))}")
        if "min_length" in rule and len(str(value).strip()) < rule["min_length"]:
            problems.append(f"{name} needs at least {rule['min_length']} characters")
        clean[name] = value.strip() if isinstance(value, str) else value
    if problems:
        raise Problem(422, "/problems/validation", "Please correct the form", "; ".join(problems), errors=problems)
    return clean


async def posting(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return dict(row)


def in_jurisdiction(staff: dict[str, Any], office: dict[str, Any]) -> bool:
    return staff["office_id"] in (office["office_id"], office.get("zone_id")) or staff["office_id"].startswith("HO")


async def emit(session: AsyncSession, definition: dict[str, Any], case: dict[str, Any], op: dict[str, Any],
               from_state: str | None, to_state: str, data: dict[str, Any], actor: Actor) -> None:
    await add_event(session, producer=PRODUCER, event_type="ProcessTransitioned.v1", aggregate_type="process_instance",
                    aggregate_id=case["case_id"], correlation_id=actor.correlation_id, payload={
                        "process": definition["process"], "instance_id": case["case_id"], "subject_ref": case["subject_ref"],
                        "from_state": from_state, "to_state": to_state, "operation": op["name"], "data": data})


def _next(definition: dict[str, Any], state: str) -> tuple[str | None, str | None]:
    """The operation available from `state` and the role that performs it."""
    for op in definition["operations"]:
        if op.get("from") == state:
            return op["name"], (op.get("chain") or op["roles"])[0]
    return None, None


def build_router() -> APIRouter:
    router = APIRouter()
    for definition in definitions():
        for op in definition["operations"]:
            router.add_api_route("/api/v1" + op["operation"].split(" ", 1)[1], _handler(definition, op),
                                 methods=[op["operation"].split(" ", 1)[0]], name=f"{definition['process']}.{op['name']}")
    return router


def _handler(definition: dict[str, Any], op: dict[str, Any]):
    async def handle(request: Request, body: dict[str, Any] = Body(default_factory=dict),
                     actor: Actor = Depends(require_actor)) -> dict:
        allowed = op.get("chain") or op["roles"]
        if actor.stakeholder not in allowed:
            raise Problem(403, "/problems/forbidden", "Not allowed", f"{op['name']} is done by {', '.join(allowed)}.")
        data = validate_form(op.get("form", {}), body)
        async with sessions()() as session, session.begin():
            staff = await posting(session, actor)
            if op.get("starts"):
                result = await _start(session, definition, op, request.path_params[definition["subject"]], staff, data, actor)
            elif op.get("chain"):
                result = await _chain_step(session, definition, op, request.path_params["caseId"], staff, data, actor)
            else:
                result = await _subject_step(session, definition, op, request.path_params[definition["subject"]], staff, data, actor)
        return envelope(result)
    return handle


async def _open_case(session: AsyncSession, definition: dict[str, Any], subject_ref: str) -> dict[str, Any] | None:
    row = (await session.execute(select(cases).where(cases.c.process == definition["process"], cases.c.subject_ref == subject_ref,
                                                     cases.c.state != "CLOSED"))).mappings().first()
    return dict(row) if row else None


def _view(case: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    nxt, role = _next(definition, case["state"])
    return {"case_id": case["case_id"], "process": definition["process"], "subject_ref": case["subject_ref"],
            "state": case["state"], "step": case["step"], "chain": case["chain"], "current_role": case["current_role"],
            "version": case["version"], "next_operation": nxt if case["current_role"] else None}


async def _start(session, definition, op, subject_ref, staff, data, actor) -> dict[str, Any]:
    office = (await session.execute(select(subject_offices).where(subject_offices.c.subject_ref == subject_ref))).mappings().first()
    if not office or not in_jurisdiction(staff, dict(office)):
        raise Problem(404, "/problems/not-found", "Not found")          # outside your jurisdiction looks the same
    require_step_up(actor, op["step_up"], subject_ref)
    if await _open_case(session, definition, subject_ref):
        raise Problem(409, "/problems/process-open", f"A {definition['title'].lower()} is already in progress for this subject")
    queue = next(o for o in definition["operations"] if o["name"] == op["queue"])
    case = {"case_id": f"CASE-{secrets.token_hex(4).upper()}", "subject_ref": subject_ref, "state": op["to"], "step": 0,
            "chain": list(queue["chain"]), "current_role": queue["chain"][0], "version": 1}
    await session.execute(insert(cases).values(
        **case, claim_id=None, grievance_id=None, office_id=office["office_id"], kind=definition["case_kind"],
        process=definition["process"], form_type="-", account_link_id="-", amount_paise=0, rule_version="-", round=1,
        sla_due_at=datetime.now(UTC) + timedelta(days=SLA_DAYS)))
    await session.execute(insert(case_actions).values(case_id=case["case_id"], round=1, officer_subject=actor.subject,
                                                      officer_role=actor.stakeholder, action=op["name"].upper(), checks=data,
                                                      reason=data.get("reason")))
    await emit(session, definition, case, op, None, op["to"], data, actor)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"{definition['process']}.{op['name']}",
                target_type=definition["subject"], target_id=subject_ref, detail=data.get("order_ref"))
    return _view(case, definition)


async def _chain_step(session, definition, op, case_id, staff, data, actor) -> dict[str, Any]:
    row = (await session.execute(select(cases).where(cases.c.case_id == case_id, cases.c.process == definition["process"]))).mappings().first()
    if not row or row["office_id"] != staff["office_id"]:
        raise Problem(404, "/problems/not-found", "Case not found")
    case = dict(row)
    if case["state"] != op["from"]:
        raise Problem(409, "/problems/invalid-state", "This case is not at this step", f"State: {case['state']}.")
    if case["chain"][case["step"]] != actor.stakeholder:
        raise Problem(403, "/problems/not-your-turn", "This case is waiting for another role", f"It is with {case['chain'][case['step']]}.")
    acted = (await session.execute(select(case_actions.c.officer_subject).where(
        case_actions.c.case_id == case_id, case_actions.c.round == case["round"]))).scalars().all()
    if actor.subject in acted:
        raise Problem(403, "/problems/separation-of-duties", "You already acted on this case",
                      "A different officer must take each step.")
    last = case["step"] + 1 >= len(case["chain"])
    values: dict[str, Any] = {"step": case["step"] + 1, "version": case["version"] + 1}
    if last:
        values["state"] = op["to"]
        values["current_role"] = _next(definition, op["to"])[1]
    else:
        values["current_role"] = case["chain"][case["step"] + 1]
    result = await session.execute(update(cases).where(cases.c.case_id == case_id, cases.c.version == case["version"]).values(**values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This case changed meanwhile")
    await session.execute(insert(case_actions).values(case_id=case_id, round=case["round"], officer_subject=actor.subject,
                                                      officer_role=actor.stakeholder, action=op["name"].upper(),
                                                      approval_level=case["step"], checks=data, reason=data.get("note")))
    case.update(values)
    if last:
        await emit(session, definition, case, op, op["from"], op["to"], data, actor)
    return _view(case, definition)


async def _subject_step(session, definition, op, subject_ref, staff, data, actor) -> dict[str, Any]:
    case = await _open_case(session, definition, subject_ref)
    if not case or case["office_id"] != staff["office_id"] and not staff["office_id"].startswith("HO"):
        raise Problem(404, "/problems/not-found", "No open process for this subject")
    require_step_up(actor, op["step_up"], subject_ref)
    if case["state"] != op["from"]:
        raise Problem(409, "/problems/invalid-state", f"{op['name']} needs state {op['from']}", f"State: {case['state']}.")
    if op.get("requires_last_finding"):
        last = (await session.execute(select(case_actions.c.checks).where(case_actions.c.case_id == case["case_id"])
                                      .order_by(case_actions.c.id.desc()).limit(1))).scalar_one_or_none() or {}
        if last.get("finding") != op["requires_last_finding"]:
            raise Problem(409, "/problems/finding-required", f"The verification did not find {op['requires_last_finding']}",
                          f"Last finding: {last.get('finding')}. This cannot be done here.")
    result = await session.execute(update(cases).where(cases.c.case_id == case["case_id"], cases.c.version == case["version"]).values(
        state="CLOSED" if op["to"] == "ACTIVE" else op["to"], current_role=None, version=case["version"] + 1))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This case changed meanwhile")
    await session.execute(insert(case_actions).values(case_id=case["case_id"], round=case["round"], officer_subject=actor.subject,
                                                      officer_role=actor.stakeholder, action=op["name"].upper(), checks=data,
                                                      reason=data.get("reason")))
    await emit(session, definition, case, op, op["from"], op["to"], data, actor)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"{definition['process']}.{op['name']}",
                target_type=definition["subject"], target_id=subject_ref)
    case.update(state=op["to"], current_role=None, version=case["version"] + 1)
    return _view(case, definition)


def _describe(definition: dict[str, Any], op: dict[str, Any], **params: str) -> dict[str, Any]:
    method, path = op["operation"].split(" ", 1)
    for key, value in params.items():
        path = path.replace("{" + key + "}", value)
    return {"process": definition["process"], "title": definition["title"], "name": op["name"], "method": method,
            "path": "/api/v1" + path, "form": op.get("form", {}), "step_up": op.get("step_up"),
            "subject": definition["subject"]}


def startable(role: str) -> list[dict[str, Any]]:
    """Processes this role may start, described well enough for the generic web screen to render the form."""
    return [_describe(d, op) for d in definitions() for op in d["operations"] if op.get("starts") and role in op["roles"]]


def next_operation(case: dict[str, Any]) -> dict[str, Any] | None:
    definition = next((d for d in definitions() if d["process"] == case["process"]), None)
    name = _next(definition, case["state"])[0] if definition and case["current_role"] else None
    op = next((o for o in definition["operations"] if o["name"] == name), None) if name else None
    return _describe(definition, op, caseId=case["case_id"], **{definition["subject"]: case["subject_ref"]}) if op else None
