"""Tier-2 process engine (ADR-0005). Executes the YAML definitions in config/processes.

Each operation in a definition becomes a route. The engine enforces, generically:

* who may act     `roles`, a `chain` taken step by step, or `roles_by` a field of the case (e.g. major → APFC);
* where           `scope`: office (posting and jurisdiction), establishment (the employer of the subject),
                  or self (the member the process is about);
* when            `from` states; the result is `to`, or `outcomes` chosen by a form field;
* how             `form` rules, `step_up` bound to the subject or to the case version, one action per officer
                  per round (maker ≠ checker), `requires_last_finding`;
* lists           GET operations with `lists` return the open cases in given states within the caller's scope;
                  GET operations with `reads` return one case the caller may see (e.g. a member's own transfer);
* documents       `produces_document` (a signed document kept on the case) and `requires_viewed` (the officer
                  must have opened it first); `ledger_lock` on a definition locks the member's ledger while open;
* accounts, dates form rules `account` (a member account of the actor or of the subject, exited or not, at the
                  caller's establishment, not yet transferred) and `date` (not in the future, not before joining),
                  checked against the member-account projection kept here.

Each state change emits ProcessTransitioned.v1; the owning service reacts and publishes its own domain events."""
import os
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.locks_routes import acquire, add_document, ensure_unlocked, ensure_viewed
from app.infra.db import sessions
from app.infra.tables import case_actions, cases, member_accounts, office_staff, subject_offices
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
        states = set(d.get("terminal_states", []))
        for op in d["operations"]:
            where = f"{d['process']}.{op['name']}"
            if not (op.get("roles") or op.get("chain") or op.get("roles_by")):
                raise ValueError(f"{where}: no roles, chain or roles_by")
            if op.get("lists"):
                continue
            if op.get("reads"):
                if not op.get("case_from"):
                    raise ValueError(f"{where}: reads needs case_from")
                continue
            if not (op.get("starts") or op.get("case_from")):
                raise ValueError(f"{where}: needs starts or case_from")
            if op.get("outcomes"):
                states |= set(op["outcomes"]["map"].values())
            elif "to" in op:
                states.add(op["to"])
            else:
                raise ValueError(f"{where}: needs to or outcomes")
        for op in d["operations"]:
            for field, rule in (op.get("form") or {}).items():
                if any(not isinstance(v, str) for v in rule.get("enum", [])):   # YAML reads YES/NO/ON as booleans
                    raise ValueError(f"{d['process']}.{op['name']}: quote the enum values of {field}")
            for state in _as_list(op.get("from")):
                if state not in states:
                    raise ValueError(f"{d['process']}.{op['name']}: from-state {state} is never reached")
    return loaded


def _as_list(value: Any) -> list[Any]:
    return [] if value is None else value if isinstance(value, list) else [value]


def validate_form(form: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    clean, problems = {}, []
    for name, rule in form.items():
        value = body.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if rule.get("optional"):
                continue
            problems.append(f"{name} is required")
            continue
        if "enum" in rule and value not in rule["enum"]:
            problems.append(f"{name} must be one of {', '.join(map(str, rule['enum']))}")
        if "min_length" in rule and len(str(value).strip()) < rule["min_length"]:
            problems.append(f"{name} needs at least {rule['min_length']} characters")
        if "max_length" in rule and len(str(value).strip()) > rule["max_length"]:
            problems.append(f"{name} allows at most {rule['max_length']} characters")
        if "date" in rule:
            try:
                day = date.fromisoformat(str(value))
                if rule["date"].get("not_future") and day > datetime.now(UTC).date():
                    problems.append(f"{name} cannot be in the future")
            except ValueError:
                problems.append(f"{name} must be a date (YYYY-MM-DD)")
        clean[name] = value.strip() if isinstance(value, str) else value
    if problems:
        raise Problem(422, "/problems/validation", "Please correct the form", "; ".join(problems), errors=problems)
    return clean


async def check_accounts(session: AsyncSession, form: dict[str, Any], data: dict[str, Any], actor: Actor,
                         subject_ref: str) -> None:
    """`account` and `date … after_joining_of` rules, against the member accounts this service keeps."""
    problems = []
    for name, rule in form.items():
        want = rule.get("account")
        if want is None or name not in data:
            continue
        row = (await session.execute(select(member_accounts).where(member_accounts.c.account_link_id == data[name]))).mappings().first()
        owner_ok = row is not None and (row["member_subject"] == actor.subject if want.get("owner") == "self" else row["uan"] == subject_ref)
        if not owner_ok or (want.get("establishment") == "actor" and row["establishment_id"] != actor.establishment_id):
            problems.append(f"{name}: no such member account here")
            continue
        if "exited" in want and bool(row["date_of_exit"]) != want["exited"]:
            problems.append(f"{name}: the date of exit must be marked first" if want["exited"] else f"{name}: this account is already exited")
        if want.get("not_transferred") and row["transferred_to"]:
            problems.append(f"{name}: this account was already transferred to {row['transferred_to']}")
        if want.get("primary") and not row["is_primary"]:
            problems.append(f"{name}: transfer-in member ID must be the primary member ID")
    for name, rule in form.items():
        joined_of = (rule.get("date") or {}).get("after_joining_of")
        if joined_of and name in data and data.get(joined_of):
            row = (await session.execute(select(member_accounts.c.date_of_joining).where(
                member_accounts.c.account_link_id == data[joined_of]))).scalar_one_or_none()
            if row and date.fromisoformat(str(data[name])) < row:
                problems.append(f"{name} cannot be before the date of joining ({row.isoformat()})")
    if problems:
        raise Problem(422, "/problems/validation", "Please correct the form", "; ".join(problems), errors=problems)


def derive(definition: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for name, rule in (definition.get("derive") or {}).items():
        out[name] = next((cls for cls, values in rule["map"].items() if data.get(rule["from"]) in values), rule.get("default"))
    return out


def roles_for(op: dict[str, Any], case: dict[str, Any] | None) -> list[str]:
    """Who may perform `op` now: the chain step, the roles for a case field, or the listed roles."""
    if op.get("chain"):
        return [case["chain"][case["step"]]] if case else list(op["chain"])
    if op.get("roles_by"):
        by = op["roles_by"]
        if case is None:
            return sorted({r for rs in by["map"].values() for r in rs})
        return list(by["map"].get((case.get("data") or {}).get(by["field"]), []))
    return list(op["roles"])


def next_op(definition: dict[str, Any], state: str) -> dict[str, Any] | None:
    if state in definition.get("terminal_states", []):
        return None
    return next((op for op in definition["operations"] if not (op.get("lists") or op.get("reads"))
                 and state in _as_list(op.get("from"))), None)


def current_role(definition: dict[str, Any], case: dict[str, Any]) -> str | None:
    op = next_op(definition, case["state"])
    return "|".join(roles_for(op, case)) if op else None


def route_of(definition: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """The roles the case will pass through, for display (chain processes show their chain)."""
    if case.get("chain"):
        return case["chain"]
    return ["|".join(roles_for(op, case)) for op in definition["operations"]
            if not (op.get("lists") or op.get("reads") or op.get("starts"))]


async def posting(session: AsyncSession, actor: Actor) -> dict[str, Any] | None:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    return dict(row) if row else None


def in_jurisdiction(staff: dict[str, Any] | None, office_id: str, zone_id: str | None) -> bool:
    return bool(staff) and (staff["office_id"] in (office_id, zone_id) or staff["office_id"].startswith("HO"))


async def subject_row(session: AsyncSession, subject_ref: str) -> dict[str, Any] | None:
    row = (await session.execute(select(subject_offices).where(subject_offices.c.subject_ref == subject_ref))).mappings().first()
    return dict(row) if row else None


def in_scope(op: dict[str, Any], actor: Actor, staff: dict[str, Any] | None, subject: dict[str, Any] | None) -> bool:
    if not subject:
        return False
    scope = op.get("scope", "office")
    if scope == "self":
        return subject.get("member_subject") == actor.subject
    if scope == "establishment":
        return bool(actor.establishment_id) and subject.get("establishment_id") == actor.establishment_id
    return in_jurisdiction(staff, subject["office_id"], subject.get("zone_id"))


def bind_step_up(op: dict[str, Any], actor: Actor, case: dict[str, Any] | None, subject_ref: str) -> None:
    step = op.get("step_up")
    if not step:
        return
    action, bind = (step, "subject") if isinstance(step, str) else (step["action"], step.get("bind", "subject"))
    if bind == "case":
        require_step_up(actor, action, case["case_id"], case["version"])
    else:
        require_step_up(actor, action, subject_ref)


async def emit(session: AsyncSession, definition: dict[str, Any], case: dict[str, Any], op: dict[str, Any],
               from_state: str | None, to_state: str, data: dict[str, Any], actor: Actor) -> None:
    await add_event(session, producer=PRODUCER, event_type="ProcessTransitioned.v1", aggregate_type="process_instance",
                    aggregate_id=case["case_id"], correlation_id=actor.correlation_id, payload={
                        "process": definition["process"], "instance_id": case["case_id"], "subject_ref": case["subject_ref"],
                        "from_state": from_state, "to_state": to_state, "operation": op["name"], "title": definition["title"],
                        "terminal": to_state in definition.get("terminal_states", []),
                        "visible_to_member": bool(definition.get("visible_to_member")),
                        "actor_subject": actor.subject, "actor_role": actor.stakeholder,
                        "data": {**(case.get("data") or {}), **data}})


def build_router() -> APIRouter:
    router = APIRouter()
    for definition in definitions():
        for op in definition["operations"]:
            method, path = op["operation"].split(" ", 1)
            handler = _lister(definition, op) if op.get("lists") else _reader(definition, op) if op.get("reads") else _handler(definition, op)
            router.add_api_route("/api/v1" + path, handler,
                                 methods=[method], name=f"{definition['process']}.{op['name']}")
    return router


def _check_role(op: dict[str, Any], actor: Actor, case: dict[str, Any] | None) -> None:
    allowed = roles_for(op, case)
    if actor.stakeholder not in allowed:
        raise Problem(403, "/problems/not-your-turn" if case else "/problems/forbidden", "Not allowed at this step",
                      f"{op['name']} is done by {', '.join(allowed) or 'nobody at this step'}.")


def _handler(definition: dict[str, Any], op: dict[str, Any]):
    async def handle(request: Request, body: dict[str, Any] = Body(default_factory=dict),
                     actor: Actor = Depends(require_actor)) -> dict:
        _check_role(op, actor, None)
        data = validate_form(op.get("form", {}), body)
        async with sessions()() as session, session.begin():
            staff = await posting(session, actor)
            if op.get("scope", "office") == "office" and not staff:
                raise Problem(403, "/problems/no-posting", "You are not posted to an office")
            if op.get("starts"):
                result = await _start(session, definition, op, request, staff, data, actor)
            else:
                result = await _step(session, definition, op, request, staff, data, actor)
        return envelope(result)
    return handle


def _lister(definition: dict[str, Any], op: dict[str, Any]):
    async def handle(actor: Actor = Depends(require_actor)) -> dict:
        _check_role(op, actor, None)
        async with sessions()() as session:
            staff = await posting(session, actor)
            rows = (await session.execute(select(cases, subject_offices).join(
                subject_offices, subject_offices.c.subject_ref == cases.c.subject_ref).where(
                cases.c.process == definition["process"], cases.c.state.in_(op["lists"]["states"]))
                .order_by(cases.c.created_at))).mappings().all()
            items = [_view(dict(r), definition) for r in rows if in_scope(op, actor, staff, dict(r))]
        if op["lists"].get("summary"):
            counts: dict[str, int] = {}
            for i in items:
                counts[i["state"]] = counts.get(i["state"], 0) + 1
            return envelope({"process": definition["process"], "pending_by_state": counts, "total": len(items)})
        return envelope(items)
    return handle


def _reader(definition: dict[str, Any], op: dict[str, Any]):
    async def handle(request: Request, actor: Actor = Depends(require_actor)) -> dict:
        _check_role(op, actor, None)
        async with sessions()() as session:
            staff = await posting(session, actor)
            row = (await session.execute(select(cases).where(cases.c.case_id == request.path_params[op["case_from"].split(":", 1)[1]],
                                                             cases.c.process == definition["process"]))).mappings().first()
            subject = await subject_row(session, row["subject_ref"]) if row else None
            if not row or not in_scope(op, actor, staff, subject):
                raise Problem(404, "/problems/not-found", "Not found")
            history = (await session.execute(select(case_actions.c.action, case_actions.c.officer_role, case_actions.c.at)
                                             .where(case_actions.c.case_id == row["case_id"]).order_by(case_actions.c.id))).mappings().all()
        view = _view(dict(row), definition)
        view["history"] = [{"action": h["action"], "by": h["officer_role"],
                            "at": h["at"].isoformat() if hasattr(h["at"], "isoformat") else h["at"]} for h in history]
        return envelope(view)
    return handle


async def _open_case(session: AsyncSession, definition: dict[str, Any], subject_ref: str) -> dict[str, Any] | None:
    row = (await session.execute(select(cases).where(
        cases.c.process == definition["process"], cases.c.subject_ref == subject_ref,
        cases.c.state.notin_(definition.get("terminal_states", []) + ["CLOSED"])))).mappings().first()
    return dict(row) if row else None


def _view(case: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    op = next_op(definition, case["state"])
    return {"case_id": case["case_id"], "process": definition["process"], "title": definition["title"],
            "subject_ref": case["subject_ref"], "state": case["state"], "step": case["step"], "chain": route_of(definition, case),
            "current_role": case["current_role"], "version": case["version"], "data": case.get("data") or {},
            "next_operation": op["name"] if op and case["current_role"] else None}


async def _start(session, definition, op, request, staff, data, actor) -> dict[str, Any]:
    if op.get("subject_from") == "actor":
        row = (await session.execute(select(subject_offices).where(subject_offices.c.member_subject == actor.subject))).mappings().first()
        subject_ref = row["subject_ref"] if row else None
    else:
        subject_ref = request.path_params[definition["subject"]]
    subject = await subject_row(session, subject_ref) if subject_ref else None
    if not in_scope(op, actor, staff, subject):
        raise Problem(404, "/problems/not-found", "Not found")          # outside your jurisdiction looks the same
    await check_accounts(session, op.get("form", {}), data, actor, subject_ref)
    bind_step_up(op, actor, None, subject_ref)
    if await _open_case(session, definition, subject_ref):
        raise Problem(409, "/problems/process-open", f"A {definition['title'].lower()} is already in progress for this subject")
    case_data = {**data, **derive(definition, data)}
    queue = next((o for o in definition["operations"] if o["name"] == op.get("queue")), None)
    case = {"case_id": f"CASE-{secrets.token_hex(4).upper()}", "subject_ref": subject_ref, "state": op["to"], "step": 0,
            "chain": list(queue["chain"]) if queue and queue.get("chain") else [], "version": 1, "data": case_data, "round": 1}
    case["current_role"] = current_role(definition, case)
    due = datetime.now(UTC) + timedelta(days=definition.get("sla_days", SLA_DAYS))
    if definition.get("ledger_lock"):          # the case holds the member's ledger while it is open (P2.5c)
        await acquire(session, subject_ref, definition["ledger_lock"], subject_ref, case["case_id"], subject["office_id"], due)
    await session.execute(insert(cases).values(
        **{k: case[k] for k in ("case_id", "subject_ref", "state", "step", "chain", "version", "data", "round", "current_role")},
        claim_id=None, grievance_id=None, office_id=subject["office_id"], kind=definition["case_kind"],
        process=definition["process"], form_type="-", account_link_id="-", amount_paise=0, rule_version="-",
        sla_due_at=due))
    await session.execute(insert(case_actions).values(case_id=case["case_id"], round=1, officer_subject=actor.subject,
                                                      officer_role=actor.stakeholder, action=op["name"].upper(), checks=data,
                                                      reason=data.get("reason")))
    await emit(session, definition, case, op, None, op["to"], data, actor)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"{definition['process']}.{op['name']}",
                target_type=definition["subject"], target_id=subject_ref)
    return _view(case, definition)


async def _step(session, definition, op, request, staff, data, actor) -> dict[str, Any]:
    kind, name = op["case_from"].split(":", 1)
    if kind == "path_subject":
        case = await _open_case(session, definition, request.path_params[name])
    else:
        row = (await session.execute(select(cases).where(cases.c.case_id == request.path_params[name],
                                                         cases.c.process == definition["process"]))).mappings().first()
        case = dict(row) if row else None
    subject = await subject_row(session, case["subject_ref"]) if case else None
    if not case or not in_scope(op, actor, staff, subject):
        raise Problem(404, "/problems/not-found", "Not found")
    if case["state"] not in _as_list(op.get("from")):
        raise Problem(409, "/problems/invalid-state", f"{op['name']} is not possible now", f"State: {case['state']}.")
    _check_role(op, actor, case)
    await check_accounts(session, op.get("form", {}), data, actor, case["subject_ref"])
    if op.get("scope", "office") == "office" and not op.get("same_officer_allowed"):
        acted = (await session.execute(select(case_actions.c.officer_subject).where(
            case_actions.c.case_id == case["case_id"], case_actions.c.round == case["round"]))).scalars().all()
        if actor.subject in acted:
            raise Problem(403, "/problems/separation-of-duties", "You already acted on this case",
                          "A different officer must take each step.")
    if definition["subject"] == "uan":
        await ensure_unlocked(session, case)
    if op.get("recheck_primary") and data.get("decision", "APPROVE") == "APPROVE":   # the primary may have moved meanwhile (P2.7d)
        field = op["recheck_primary"]
        link = (case.get("data") or {}).get(field)
        if link and not (await session.execute(select(member_accounts.c.is_primary).where(member_accounts.c.account_link_id == link))).scalar_one_or_none():
            raise Problem(409, "/problems/not-primary-member-id", "The transfer-in member ID is no longer the primary member ID",
                          f"{link} is not the member's primary member ID now; reject the request so the member files it again.")
    if op.get("requires_viewed"):              # e.g. the employer-signed Form 13 must be opened first
        await ensure_viewed(session, case, op["requires_viewed"], actor)
    bind_step_up(op, actor, case, case["subject_ref"])
    if op.get("requires_last_finding"):
        last = (await session.execute(select(case_actions.c.checks).where(case_actions.c.case_id == case["case_id"])
                                      .order_by(case_actions.c.id.desc()).limit(1))).scalar_one_or_none() or {}
        if last.get("finding") != op["requires_last_finding"]:
            raise Problem(409, "/problems/finding-required", f"The verification did not find {op['requires_last_finding']}",
                          f"Last finding: {last.get('finding')}. This cannot be done here.")
    before = case["state"]
    values: dict[str, Any] = {"version": case["version"] + 1}
    if op.get("chain") and case["step"] + 1 < len(case["chain"]):
        values["step"] = case["step"] + 1                          # the chain continues with its next role
        state = before
    else:
        state = op["outcomes"]["map"][data[op["outcomes"]["field"]]] if op.get("outcomes") else op["to"]
        if op.get("chain"):
            values["step"] = case["step"] + 1
        if state in _as_list(op.get("new_round_on")):
            values["round"] = case["round"] + 1                    # sent back: earlier steps are redone by anyone
    values["state"] = state
    updated = {**case, **values}
    values["current_role"] = (case["chain"][values["step"]] if op.get("chain") and state == before
                              else current_role(definition, updated))
    result = await session.execute(update(cases).where(cases.c.case_id == case["case_id"], cases.c.version == case["version"]).values(**values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This case changed meanwhile")
    await session.execute(insert(case_actions).values(case_id=case["case_id"], round=case["round"], officer_subject=actor.subject,
                                                      officer_role=actor.stakeholder, action=op["name"].upper(),
                                                      approval_level=case["step"], checks=data,
                                                      reason=data.get("note") or data.get("reason")))
    updated.update(values)
    doc = op.get("produces_document")
    if doc and state in _as_list(doc.get("on_states")):
        await add_document(session, updated, doc, actor, data)
    if state != before:
        await emit(session, definition, updated, op, before, state, data, actor)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"{definition['process']}.{op['name']}",
                target_type="case", target_id=case["case_id"], detail=state)
    return _view(updated, definition)


def _describe(definition: dict[str, Any], op: dict[str, Any], case: dict[str, Any] | None = None) -> dict[str, Any]:
    method, path = op["operation"].split(" ", 1)
    if case:
        path = path.replace("{" + definition["subject"] + "}", case["subject_ref"])
        path = re.sub(r"\{[A-Za-z]+Id\}", case["case_id"], path)          # {caseId}, {jdId}, {transferId}, …
    step = op.get("step_up")
    step_up = None if not step else {"action": step, "bind": "subject"} if isinstance(step, str) else step
    return {"process": definition["process"], "title": definition["title"], "name": op["name"], "method": method,
            "path": "/api/v1" + path, "form": op.get("form", {}), "step_up": step_up, "subject": definition["subject"],
            "subject_from": op.get("subject_from", "path")}


def startable(role: str) -> list[dict[str, Any]]:
    """Processes this role may start, described well enough for the generic web screen to render the form."""
    return [_describe(d, op) for d in definitions() for op in d["operations"]
            if op.get("starts") and role in roles_for(op, None) and op.get("scope", "office") == "office"]


def next_operation(case: dict[str, Any]) -> dict[str, Any] | None:
    definition = next((d for d in definitions() if d["process"] == case["process"]), None)
    op = next_op(definition, case["state"]) if definition and case["current_role"] else None
    return _describe(definition, op, case) if op else None


def _next(definition: dict[str, Any], state: str) -> tuple[str | None, str | None]:
    """Name of the next operation from `state` (used by the work queue)."""
    op = next_op(definition, state)
    return (op["name"], roles_for(op, None)[0]) if op else (None, None)
