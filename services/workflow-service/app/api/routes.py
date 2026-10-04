"""workflow-service: officer work queue and the claim approval chain (Journey B4–B5).

A case follows `chain` (from the approval matrix of the claim's rule version, set in Policy administration):
  step 0            fo.da_accounts records a recommendation      POST …/recommendations
  step 1            first checker (fo.ss or fo.ao) decides        POST …/decisions        (step-up)
  step 2 and later  next checker (fo.apfc or fo.oic) decides      POST …/second-approvals (step-up)
Each officer must be posted to the case's office, hold the role whose turn it is, and be a different
person from everyone who already acted in this round. RETURN sends the case back to step 0 and voids
the round's approvals."""
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.api.locks_routes import acquire, documents_of, ensure_unlocked
from app.infra.tables import case_actions, cases, claim_dockets, member_accounts, office_staff, offices
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import approval_chain, rules_by_version, rules_on

router = APIRouter()
PRODUCER = "workflow-service"
FIRST_CHECKERS, SECOND_CHECKERS = ("fo.ss", "fo.ao"), ("fo.apfc", "fo.oic")
OFFICERS = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic", "fo.cash", "fo.pro",
                               "do.incharge", "do.staff", "zo.acc", "zo.rpfc1")
GRIEVANCE_HANDLER = {"RO": "fo.pro", "ZO": "zo.acc", "HO": "ho.customer_service"}


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class Recommendation(BaseModel):
    checks: list[str] = Field(default_factory=list)   # e.g. ["KYC verified", "Balance sufficient"]
    note: str = Field(min_length=3, max_length=1000)
    recommendation: str = Field(default="APPROVE", pattern="^(APPROVE|REJECT)$")   # "Recommend to Approve / to Reject"
    account_status: str = Field(pattern="^(OPERATIVE|INOPERATIVE|DORMANT)$")     # set by the initiator (CITES manuals)
    reason_code: str | None = Field(default=None, max_length=40)                 # P2.23b: why rejection is recommended


class StopInput(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class Decision(BaseModel):
    decision: str                                      # APPROVE | REJECT | RETURN
    reason: str | None = Field(default=None, max_length=1000)
    reason_code: str | None = Field(default=None, max_length=40)       # P2.23b: the rule set's rejection reason


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
    if case.get("process"):
        from app.engine.engine import _next, definitions
        definition = next(d for d in definitions() if d["process"] == case["process"])
        return _next(definition, case["state"])[0] if case["current_role"] else None
    if case["state"] == "IN_REVIEW":
        return "recommend" if case["step"] == 0 else "decide" if case["step"] == 1 else "second-approve"
    return {"AWAITING_PAYMENT": "instruct-payment", "PAYMENT_RETURNED": "reissue", "OPEN": "handle-grievance",
            "REDISBURSEMENT_REVIEW": "approve-redisbursement"}.get(case["state"])


async def history(session: AsyncSession, case_id: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(case_actions).where(case_actions.c.case_id == case_id)
                                  .order_by(case_actions.c.id))).mappings().all()
    return [{"at": r["at"].isoformat() if r["at"] else None, "round": r["round"], "officer_role": r["officer_role"],
             "officer_subject": r["officer_subject"], "action": r["action"], "approval_level": r["approval_level"],
             "reason": r["reason"], "checks": r["checks"]} for r in rows]


def case_json(case: dict[str, Any]) -> dict[str, Any]:
    return {"case_id": case["case_id"], "claim_id": case["claim_id"], "grievance_id": case.get("grievance_id"),
            "kind": case["kind"], "office_id": case["office_id"], "advisory_signal_id": case.get("advisory_signal_id"),
            "process": case.get("process"), "subject_ref": case.get("subject_ref"), "data": case.get("data") or {},
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
                        final: bool, next_role: str | None, reason: str | None, recommendation: str | None = None,
                        reason_code: str | None = None) -> None:
    await add_event(session, producer=PRODUCER, event_type="CaseDecisionSubmitted.v1", aggregate_type="case",
                    aggregate_id=case["case_id"], correlation_id=actor.correlation_id, payload={
                        "case_id": case["case_id"], "claim_id": case["claim_id"], "decision": decision,
                        "officer_subject": actor.subject, "officer_role": actor.stakeholder, "approval_level": level,
                        "final": final, "next_role": next_role, "reason": reason, "recommendation": recommendation,
                        **({"reason_code": reason_code} if reason_code else {})})


async def rejection_code(session: AsyncSession, *codes: str | None) -> str:
    """P2.23b: a claim is rejected for one of the rule set's reasons, each with what the member does about it. The first
    code given is used; none given is OTHER (the officer's note then says what to do)."""
    from epfo_persistence.policy import section
    known = section(await rules_on(session, datetime.now(UTC).date()), "claims").get("rejection_reasons") or {"OTHER": {}}
    code = next((c for c in codes if c), "OTHER")
    if code not in known:
        raise Problem(422, "/problems/validation", "Unknown rejection reason", "Choose one of: " + ", ".join(known))
    return code


DECISIONS = ("RECOMMEND", "APPROVE", "REJECT", "RETURN", "RECOMMEND_REJECT")


async def last_decision(session: AsyncSession, case_id: str) -> int:
    """The id of the last decision on the case (0 before any): a docket counts only if made after it."""
    return (await session.execute(select(func.coalesce(func.max(case_actions.c.id), 0)).where(
        case_actions.c.case_id == case_id, case_actions.c.action.in_(DECISIONS)))).scalar_one()


async def require_docket(session: AsyncSession, case: dict[str, Any], actor: Actor) -> None:
    """CITES manuals: each officer generates the Claim Approval Docket again before acting on the claim."""
    since = await last_decision(session, case["case_id"])
    if not (await session.execute(select(claim_dockets.c.cad_id).where(
            claim_dockets.c.claim_id == case["claim_id"], claim_dockets.c.officer_role == actor.stakeholder,
            claim_dockets.c.after_action == since))).first():
        raise Problem(409, "/problems/docket-required", "Generate the Claim Approval Docket first",
                      "Each officer generates the Claim Approval Docket (CAD) before recommending or deciding; "
                      "it may take a moment to show after generating.")


async def _has_docket(session: AsyncSession, case: dict[str, Any], actor: Actor) -> bool:
    try:
        await require_docket(session, case, actor)
        return True
    except Problem:
        return False


def recommendation_of(case: dict[str, Any]) -> str:
    return (case.get("data") or {}).get("recommendation", "APPROVE")


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
    await ensure_unlocked(session, case)
    return staff, case


async def decide(case_id: str, body: Decision, actor: Actor, session: AsyncSession, step_rule: str) -> dict:
    """CITES manuals: only the final level of the chain decides. An intermediate level forwards the initiator's
    recommendation, or — disagreeing with an approval — recommends rejection, which returns the claim to the
    initiator's worklist to be re-forwarded as "Recommend to Reject". The final level sees Approve / Send back when
    approval is recommended and Reject / Send back when rejection is."""
    if body.decision not in ("APPROVE", "REJECT", "RETURN"):
        raise Problem(422, "/problems/validation", "decision must be APPROVE, REJECT or RETURN")
    if body.decision != "APPROVE" and not (body.reason and body.reason.strip()):
        raise Problem(422, "/problems/reason-required", "Give a reason", "A rejection or return needs a reason the member can read.")
    roles = FIRST_CHECKERS if step_rule == "first" else SECOND_CHECKERS
    async with session.begin():
        _, case = await checker_turn(session, case_id, actor, roles, step_rule)
        await require_docket(session, case, actor)
        require_step_up(actor, "decide-case", case_id, case["version"], case["amount_paise"])
        level, rec = case["step"], recommendation_of(case)
        final = level + 1 == len(case["chain"])
        back = {"step": 0, "round": case["round"] + 1, "current_role": case["chain"][0], "assignee_subject": None}
        if body.decision == "RETURN":                                   # "Send Back to First Level / Initiator"
            case = await act(session, case, actor, "RETURN", level, body.reason, None, **back)
            await emit_decision(session, case, actor, "RETURN", level, False, case["chain"][0], body.reason, rec)
        elif final and body.decision != rec:
            raise Problem(409, "/problems/decision-not-offered",
                          f"{'Rejection' if rec == 'REJECT' else 'Approval'} was recommended",
                          f"You may {'reject' if rec == 'REJECT' else 'approve'} it or send it back to the first level.")
        elif final and rec == "REJECT":
            code = await rejection_code(session, body.reason_code, (case.get("data") or {}).get("rejection_code"))
            case = await act(session, case, actor, "REJECT", level, body.reason, None, state="REJECTED", current_role=None, assignee_subject=None)
            await emit_decision(session, case, actor, "REJECT", level, True, None, body.reason, rec, code)
        elif final:
            case = await act(session, case, actor, "APPROVE", level, body.reason, None, state="AWAITING_PAYMENT",
                             current_role="fo.cash", assignee_subject=None)
            await emit_decision(session, case, actor, "APPROVE", level, True, "fo.cash", body.reason, rec)
        elif body.decision == "REJECT" and rec == "APPROVE":        # disagrees: back to the initiator's worklist
            note = f"Rejection recommended by {actor.stakeholder}: {body.reason}"
            code = await rejection_code(session, body.reason_code)
            case = await act(session, case, actor, "RECOMMEND_REJECT", level, body.reason, None,
                             data={**(case.get("data") or {}), "returned_for_rejection": note, "rejection_code": code}, **back)
            await emit_decision(session, case, actor, "RETURN", level, False, case["chain"][0], note, rec)
        elif body.decision == "APPROVE" and rec == "REJECT":
            raise Problem(409, "/problems/decision-not-offered", "Rejection was recommended",
                          "Forward the rejection (Recommend to Reject) or send the claim back to the first level.")
        else:                                                           # forward the recommendation upward
            nxt = case["chain"][level + 1]
            case = await act(session, case, actor, body.decision, level, body.reason, None, step=level + 1, current_role=nxt,
                             assignee_subject=None)
            await emit_decision(session, case, actor, "APPROVE", level, False, nxt, body.reason, rec)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"case.{body.decision.lower()}", target_type="case", target_id=case_id, detail=body.reason)
        return envelope(case_json(case))


# ── routes ──────────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/office/work-queue")
async def work_queue(actor: Actor = Depends(OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    rows = (await session.execute(select(cases).where(and_(
        cases.c.office_id == staff["office_id"],
        or_(cases.c.current_role == actor.stakeholder,                 # finished cases have no role; engine steps
            cases.c.current_role.like(f"{actor.stakeholder}|%"),       # open to several roles list them with "|"
            cases.c.current_role.like(f"%|{actor.stakeholder}"),
            cases.c.current_role.like(f"%|{actor.stakeholder}|%")),
        or_(cases.c.assignee_subject.is_(None), cases.c.assignee_subject == actor.subject))).order_by(cases.c.created_at))).mappings().all()
    from app.engine.engine import startable
    return envelope({"office_id": staff["office_id"], "role": actor.stakeholder, "items": [case_json(dict(r)) for r in rows],
                     "startable_processes": startable(actor.stakeholder)})


@router.get("/api/v1/office/cases/{case_id}")
async def get_case(case_id: str, actor: Actor = Depends(OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    case = await load_case(session, case_id, staff["office_id"])
    from app.engine.engine import next_operation
    return envelope({**case_json(case), "history": await history(session, case_id),
                     "documents": await documents_of(session, case_id, actor.subject),
                     "docket_ready": bool(case["claim_id"]) and await _has_docket(session, case, actor),
                     "your_turn": actor.stakeholder in (case["current_role"] or "").split("|"),
                     "operation": next_operation(case) if case.get("process") else None,
                     "rejection_reasons": await _rejection_reasons(session) if case["claim_id"] else []})


async def _rejection_reasons(session: AsyncSession) -> list[dict]:
    """P2.23b: the reasons an officer may reject a claim for, with what the member is told to do."""
    from epfo_persistence.policy import section
    known = section(await rules_on(session, datetime.now(UTC).date()), "claims").get("rejection_reasons") or {}
    return [{"code": code, "label": r["label"], "fix": r["fix"]} for code, r in known.items()]


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
        await ensure_unlocked(session, case)
        await require_docket(session, case, actor)
        require_step_up(actor, "recommend-case", case_id, case["version"])       # OTP on every officer action
        nxt = case["chain"][1]
        data = {**(case.get("data") or {}), "recommendation": body.recommendation, "account_status": body.account_status}
        data.pop("returned_for_rejection", None)
        if body.recommendation == "REJECT":
            data["rejection_code"] = await rejection_code(session, body.reason_code, data.get("rejection_code"))
        else:
            data.pop("rejection_code", None)
        case = await act(session, case, actor, "RECOMMEND", 0, body.note, body.checks, step=1, current_role=nxt,
                         assignee_subject=None, data=data)
        await emit_decision(session, case, actor, "RECOMMEND", 0, False, nxt, body.note, body.recommendation)
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

# ── Start-Stop Claim (CITES manuals): the initiator parks a claim while a parallel activity finishes ──────────

@router.post("/api/v1/office/cases/{case_id}/stops")
async def stop_case(case_id: str, body: StopInput, actor: Actor = Depends(require_stakeholder("fo.da_accounts")),
                    session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await posting(session, actor)
        case = await load_case(session, case_id, staff["office_id"], lock=True)
        if not case["claim_id"] or case["state"] != "IN_REVIEW":
            raise Problem(409, "/problems/invalid-state", "Only a claim under scrutiny can be stopped", f"State: {case['state']}.")
        held = {"step": case["step"], "current_role": case["current_role"], "reason": body.reason, "by": actor.stakeholder}
        case = await act(session, case, actor, "STOP", None, body.reason, None, state="STOPPED", current_role=None,
                         data={**(case.get("data") or {}), "stopped": held})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="case.stopped",
                    target_type="case", target_id=case_id, detail=body.reason)
    return envelope(case_json(case))


@router.post("/api/v1/office/cases/{case_id}/restarts")
async def restart_case(case_id: str, actor: Actor = Depends(require_stakeholder("fo.da_accounts")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        staff = await posting(session, actor)
        case = await load_case(session, case_id, staff["office_id"], lock=True)
        if case["state"] != "STOPPED":
            raise Problem(409, "/problems/invalid-state", "This claim is not stopped")
        held = dict((case.get("data") or {}).get("stopped") or {})
        data = {k: v for k, v in (case.get("data") or {}).items() if k != "stopped"}
        case = await act(session, case, actor, "RESTART", None, None, None, state="IN_REVIEW", current_role=held.get("current_role"),
                         step=held.get("step", case["step"]), data=data)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="case.restarted",
                    target_type="case", target_id=case_id)
    return envelope(case_json(case))


@router.get("/api/v1/office/stopped-cases")
async def stopped_cases(actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.oic")), session: AsyncSession = Depends(db)) -> dict:
    staff = await posting(session, actor)
    rows = (await session.execute(select(cases).where(cases.c.office_id == staff["office_id"], cases.c.state == "STOPPED")
                                  .order_by(cases.c.updated_at))).mappings().all()
    return envelope([case_json(dict(r)) for r in rows])


async def open_case(session: AsyncSession, payload: dict[str, Any], state: str) -> None:
    if (await session.execute(select(cases.c.case_id).where(cases.c.claim_id == payload["claim_id"]))).first():
        return
    # The chain and service level of the rule version the claim was made under (not whatever is in force now).
    rules = await rules_by_version(session, payload["rule_version"])
    chain = approval_chain(rules, payload.get("claim_type", ""), int(payload["amount_paise"]))
    case_id, due = f"CASE-{secrets.token_hex(4).upper()}", datetime.now(UTC) + timedelta(days=rules["claims"]["settlement_sla_days"])
    uan = (await session.execute(select(member_accounts.c.uan).where(member_accounts.c.account_link_id == payload["account_link_id"]))).scalar_one_or_none()
    if uan:                                   # the case holds the member's ledger while it is open (P2.5c)
        await acquire(session, uan, "CLAIM_ADJUDICATION", payload["account_link_id"], case_id, payload["office_id"], due)
    await session.execute(insert(cases).values(
        case_id=case_id, claim_id=payload["claim_id"], office_id=payload["office_id"],
        kind="CLAIM_SETTLEMENT", form_type=payload["form_type"], account_link_id=payload["account_link_id"],
        amount_paise=payload["amount_paise"], rule_version=payload["rule_version"], chain=chain, step=0, round=1,
        advisory_signal_id=payload.get("advisory_signal_id"),
        state=state, current_role=chain[0] if state == "IN_REVIEW" else None, version=1,
        sla_due_at=due))


async def grievance_case(session: AsyncSession, grievance_id: str, office_id: str, tier: str) -> None:
    """Open the grievance's case, or move it to the tier (and office) now handling it."""
    role = GRIEVANCE_HANDLER[tier]
    sla = (await rules_on(session, datetime.now(UTC).date()))["grievances"]["sla_days"]
    existing = (await session.execute(select(cases).where(cases.c.grievance_id == grievance_id))).mappings().first()
    if existing:
        await session.execute(update(cases).where(cases.c.case_id == existing["case_id"]).values(
            office_id=office_id, current_role=role, state="OPEN", assignee_subject=None, version=existing["version"] + 1,
            chain=[*existing["chain"], role], step=existing["step"] + 1,
            sla_due_at=datetime.now(UTC) + timedelta(days=sla[tier])))
        return
    await session.execute(insert(cases).values(
        case_id=f"CASE-{secrets.token_hex(4).upper()}", grievance_id=grievance_id, office_id=office_id, kind="GRIEVANCE",
        form_type="-", account_link_id="-", amount_paise=0, rule_version="-", chain=[role], step=0, round=1,
        state="OPEN", current_role=role, version=1,
        sla_due_at=datetime.now(UTC) + timedelta(days=sla[tier])))

