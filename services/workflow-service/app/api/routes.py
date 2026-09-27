"""workflow-service: officer work queue and the claim approval chain (Journey B4–B5).

A case follows `chain` (from the claim_settlement band in config/demo-rules.yaml):
  step 0            fo.da_accounts records a recommendation      POST …/recommendations
  step 1            first checker (fo.ss or fo.ao) decides        POST …/decisions        (step-up)
  step 2 and later  next checker (fo.apfc or fo.oic) decides      POST …/second-approvals (step-up)
Each officer must be posted to the case's office, hold the role whose turn it is, and be a different
person from everyone who already acted in this round. RETURN sends the case back to step 0 and voids
the round's approvals."""
import os
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import case_actions, cases, office_staff, offices
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "workflow-service"
RULES_PATH = Path(os.getenv("RULES_FILE", "/srv/demo-rules.yaml"))
SLA_DAYS = 20     # illustrative service standard for claim settlement
FIRST_CHECKERS, SECOND_CHECKERS = ("fo.ss", "fo.ao"), ("fo.apfc", "fo.oic")
OFFICERS = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic", "fo.cash", "fo.pro",
                               "do.incharge", "do.staff")


@lru_cache(maxsize=1)
def ruleset() -> dict[str, Any]:
    path = RULES_PATH if RULES_PATH.exists() else Path(__file__).resolve().parents[4] / "config" / "demo-rules.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def approval_chain(amount_paise: int) -> list[str]:
    for band in ruleset()["claims"]["approval_bands"]:
        if band["upto_paise"] is None or amount_paise <= band["upto_paise"]:
            return list(band["chain"])
    raise ValueError("no approval band")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class Recommendation(BaseModel):
    checks: list[str] = Field(default_factory=list)   # e.g. ["KYC verified", "Balance sufficient"]
    note: str = Field(min_length=3, max_length=1000)


class Decision(BaseModel):
    decision: str                                      # APPROVE | REJECT | RETURN
    reason: str | None = Field(default=None, max_length=1000)


class Assignment(BaseModel):
    assignee_username: str


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────

async def posting(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office", "Ask HR to record your posting.")
    return dict(row)


async def load_case(session: AsyncSession, case_id: str, office_id: str, lock: bool = False) -> dict[str, Any]:
    q = select(cases).where(cases.c.case_id == case_id)
    if lock and session.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    row = (await session.execute(q)).mappings().first()
    if not row or row["office_id"] != office_id:
        raise Problem(404, "/problems/not-found", "Case not found")   # outside your jurisdiction looks the same
    return dict(row)


def next_action(case: dict[str, Any]) -> str | None:
    if case["state"] == "IN_REVIEW":
        return "recommend" if case["step"] == 0 else "decide" if case["step"] == 1 else "second-approve"
    return {"AWAITING_PAYMENT": "instruct-payment", "PAYMENT_RETURNED": "reissue"}.get(case["state"])


async def history(session: AsyncSession, case_id: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(case_actions).where(case_actions.c.case_id == case_id)
                                  .order_by(case_actions.c.id))).mappings().all()
    return [{"at": r["at"].isoformat() if r["at"] else None, "round": r["round"], "officer_role": r["officer_role"],
             "officer_subject": r["officer_subject"], "action": r["action"], "approval_level": r["approval_level"],
             "reason": r["reason"], "checks": r["checks"]} for r in rows]


def case_json(case: dict[str, Any]) -> dict[str, Any]:
    return {"case_id": case["case_id"], "claim_id": case["claim_id"], "kind": case["kind"], "office_id": case["office_id"],
            "form_type": case["form_type"], "account_link_id": case["account_link_id"],
            "amount_paise": case["amount_paise"], "rule_version": case["rule_version"], "chain": case["chain"],
            "step": case["step"], "round": case["round"], "state": case["state"], "current_role": case["current_role"],
            "assignee_subject": case["assignee_subject"], "version": case["version"],
            "sla_due_at": case["sla_due_at"].isoformat() if case["sla_due_at"] else None,
            "next_action": next_action(case)}


async def act(session: AsyncSession, case: dict[str, Any], actor: Actor, action: str, level: int | None,
              reason: str | None, checks: list[str] | None, **values: Any) -> dict[str, Any]:
    result = await session.execute(update(cases).where(cases.c.case_id == case["case_id"],
                                                       cases.c.version == case["version"]).values(
        version=case["version"] + 1, updated_at=datetime.now(UTC), **values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This case changed meanwhile", "Reload the case and try again.")
    await session.execute(insert(case_actions).values(
        case_id=case["case_id"], round=case["round"], officer_subject=actor.subject, officer_role=actor.stakeholder,
        action=action, approval_level=level, reason=reason, checks=checks))
    return {**case, **values, "version": case["version"] + 1}


async def emit_decision(session: AsyncSession, case: dict[str, Any], actor: Actor, decision: str, level: int,
                        final: bool, next_role: str | None, reason: str | None) -> None:
    await add_event(session, producer=PRODUCER, event_type="CaseDecisionSubmitted.v1", aggregate_type="case",
                    aggregate_id=case["case_id"], correlation_id=actor.correlation_id, payload={
                        "case_id": case["case_id"], "claim_id": case["claim_id"], "decision": decision,
                        "officer_subject": actor.subject, "officer_role": actor.stakeholder, "approval_level": level,
                        "final": final, "next_role": next_role, "reason": reason})


async def checker_turn(session: AsyncSession, case_id: str, actor: Actor, allowed_roles: tuple[str, ...],
                       step_rule: str) -> tuple[dict[str, Any], dict[str, Any]]:
    staff = await posting(session, actor)
    case = await load_case(session, case_id, staff["office_id"], lock=True)
    if case["state"] != "IN_REVIEW" or not (case["step"] == 1 if step_rule == "first" else case["step"] >= 2):
        raise Problem(409, "/problems/invalid-state", "This case is not waiting for this kind of decision",
                      f"Case state {case['state']}, step {case['step']}: the next action is {next_action(case)}.")
    if actor.stakeholder not in allowed_roles or case["chain"][case["step"]] != actor.stakeholder:
        raise Problem(403, "/problems/not-your-turn", "This case is waiting for another role",
                      f"The case is with {case['chain'][case['step']]}.")
    if case["assignee_subject"] and case["assignee_subject"] != actor.subject:
        raise Problem(403, "/problems/assigned-elsewhere", "This case is assigned to another officer")
    acted = (await session.execute(select(case_actions.c.officer_subject).where(
        case_actions.c.case_id == case_id, case_actions.c.round == case["round"]))).scalars().all()
    if actor.subject in acted:
        raise Problem(403, "/problems/separation-of-duties", "You already acted on this case in this round",
                      "A different officer must take each step (recommender ≠ approver).")
    return staff, case


async def decide(case_id: str, body: Decision, actor: Actor, session: AsyncSession, step_rule: str) -> dict:
    if body.decision not in ("APPROVE", "REJECT", "RETURN"):
        raise Problem(422, "/problems/validation", "decision must be APPROVE, REJECT or RETURN")
    if body.decision != "APPROVE" and not (body.reason and body.reason.strip()):
        raise Problem(422, "/problems/reason-required", "Give a reason", "A rejection or return needs a reason the member can read.")
    roles = FIRST_CHECKERS if step_rule == "first" else SECOND_CHECKERS
    async with session.begin():
        _, case = await checker_turn(session, case_id, actor, roles, step_rule)
        require_step_up(actor, "decide-case", case_id, case["version"], case["amount_paise"])
        level = case["step"]
        if body.decision == "RETURN":
            case = await act(session, case, actor, "RETURN", level, body.reason, None, step=0, round=case["round"] + 1,
                             current_role=case["chain"][0], assignee_subject=None)
            await emit_decision(session, case, actor, "RETURN", level, False, case["chain"][0], body.reason)
        elif body.decision == "REJECT":
            case = await act(session, case, actor, "REJECT", level, body.reason, None, state="REJECTED", current_role=None,
                             assignee_subject=None)
            await emit_decision(session, case, actor, "REJECT", level, True, None, body.reason)
        elif level + 1 < len(case["chain"]):
            nxt = case["chain"][level + 1]
            case = await act(session, case, actor, "APPROVE", level, body.reason, None, step=level + 1, current_role=nxt,
                             assignee_subject=None)
            await emit_decision(session, case, actor, "APPROVE", level, False, nxt, body.reason)
        else:
            case = await act(session, case, actor, "APPROVE", level, body.reason, None, state="AWAITING_PAYMENT",
                             current_role="fo.cash", assignee_subject=None)
            await emit_decision(session, case, actor, "APPROVE", level, True, "fo.cash", body.reason)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"case.{body.decision.lower()}", target_type="case", target_id=case_id, detail=body.reason)
        return envelope(case_json(case))


# ── routes ──────────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/office/work-queue")
async def work_queue(actor: Actor = Depends(OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    rows = (await session.execute(select(cases).where(and_(
        cases.c.office_id == staff["office_id"], cases.c.current_role == actor.stakeholder,
        cases.c.state.in_(("IN_REVIEW", "AWAITING_PAYMENT", "PAYMENT_RETURNED")),
        or_(cases.c.assignee_subject.is_(None), cases.c.assignee_subject == actor.subject))).order_by(cases.c.created_at))).mappings().all()
    return envelope({"office_id": staff["office_id"], "role": actor.stakeholder, "items": [case_json(dict(r)) for r in rows]})


@router.get("/api/v1/office/cases/{case_id}")
async def get_case(case_id: str, actor: Actor = Depends(OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    case = await load_case(session, case_id, staff["office_id"])
    return envelope({**case_json(case), "history": await history(session, case_id),
                     "your_turn": case["current_role"] == actor.stakeholder})


@router.post("/api/v1/office/cases/{case_id}/recommendations")
async def recommend(case_id: str, body: Recommendation, actor: Actor = Depends(require_stakeholder("fo.da_accounts")),
                    session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await posting(session, actor)
        case = await load_case(session, case_id, staff["office_id"], lock=True)
        if case["state"] != "IN_REVIEW" or case["step"] != 0:
            raise Problem(409, "/problems/invalid-state", "This case is not waiting for a recommendation",
                          f"The next action is {next_action(case)}.")
        if case["assignee_subject"] and case["assignee_subject"] != actor.subject:
            raise Problem(403, "/problems/assigned-elsewhere", "This case is assigned to another officer")
        nxt = case["chain"][1]
        case = await act(session, case, actor, "RECOMMEND", 0, body.note, body.checks, step=1, current_role=nxt,
                         assignee_subject=None)
        await emit_decision(session, case, actor, "RECOMMEND", 0, False, nxt, body.note)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="case.recommend",
                    target_type="case", target_id=case_id)
        return envelope(case_json(case))


@router.post("/api/v1/office/cases/{case_id}/decisions")
async def first_decision(case_id: str, body: Decision, actor: Actor = Depends(require_stakeholder(*FIRST_CHECKERS)),
                         session: AsyncSession = Depends(db)) -> dict:
    return await decide(case_id, body, actor, session, "first")


@router.post("/api/v1/office/cases/{case_id}/second-approvals")
async def second_approval(case_id: str, body: Decision, actor: Actor = Depends(require_stakeholder(*SECOND_CHECKERS)),
                          session: AsyncSession = Depends(db)) -> dict:
    return await decide(case_id, body, actor, session, "second")


@router.post("/api/v1/office/cases/{case_id}/assignments")
async def assign(case_id: str, body: Assignment, actor: Actor = Depends(require_stakeholder("fo.pro")),
                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await posting(session, actor)
        case = await load_case(session, case_id, staff["office_id"], lock=True)
        target = (await session.execute(select(office_staff).where(
            office_staff.c.username == body.assignee_username))).mappings().first()
        if not target or target["office_id"] != case["office_id"] or target["stakeholder"] != case["current_role"]:
            raise Problem(422, "/problems/invalid-assignee", "Choose an officer of this office who holds the current role",
                          f"The case is waiting for {case['current_role']} in {case['office_id']}.")
        case = await act(session, case, actor, "ASSIGN", None, f"assigned to {body.assignee_username}", None,
                         assignee_subject=target["subject"])
        return envelope(case_json(case))


@router.get("/api/v1/public/offices")
async def public_offices(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(offices).order_by(offices.c.office_id))).mappings().all()
    return envelope([dict(r) for r in rows])


@router.get("/api/v1/hrm/me")
async def hrm_me(actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    office = (await session.execute(select(offices).where(offices.c.office_id == staff["office_id"]))).mappings().first()
    return envelope({"subject": staff["subject"], "username": staff["username"], "role": staff["stakeholder"],
                     "office": dict(office) if office else {"office_id": staff["office_id"]}})


# ── case creation from events (used by app/infra/messaging.py) ─────────────────────────────────

async def open_case(session: AsyncSession, payload: dict[str, Any], state: str) -> None:
    if (await session.execute(select(cases.c.case_id).where(cases.c.claim_id == payload["claim_id"]))).first():
        return
    chain = approval_chain(int(payload["amount_paise"]))
    await session.execute(insert(cases).values(
        case_id=f"CASE-{secrets.token_hex(4).upper()}", claim_id=payload["claim_id"], office_id=payload["office_id"],
        kind="CLAIM_SETTLEMENT", form_type=payload["form_type"], account_link_id=payload["account_link_id"],
        amount_paise=payload["amount_paise"], rule_version=payload["rule_version"], chain=chain, step=0, round=1,
        state=state, current_role=chain[0] if state == "IN_REVIEW" else None, version=1,
        sla_due_at=datetime.now(UTC) + timedelta(days=SLA_DAYS)))
