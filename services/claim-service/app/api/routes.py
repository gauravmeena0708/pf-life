"""claim-service: member claims (Journey B3) and the cash section's payment instructions (Journey B6).

State machine: init.md §7 "Claim". Every transition bumps `version`, writes a timeline row and is
checked against the current state; anything else is 409."""
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.claims import NEXT_STEP, OPEN_STATES, ROLE_LABELS, approval_chain, eligibility, route, summary
from app.infra.db import sessions
from app.infra.tables import accounts, claim_timeline, claims, office_staff, risk_flags
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response
from epfo_persistence.policy import rules_by_version, rules_on

router = APIRouter()
PRODUCER = "claim-service"
MEMBER = require_stakeholder("member")
CASHIER = require_stakeholder("fo.cash")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class ClaimInput(BaseModel):
    account_link_id: str
    claim_type: str
    amount_paise: int = Field(gt=0)


class PaymentInstructionInput(BaseModel):
    demo_scenario: str = "SUCCESS"   # SUCCESS | RETURN — a demo switch for the mock bank, shown as such in the UI


# ── helpers shared with the event handlers ─────────────────────────────────────────────────────

async def transition(session: AsyncSession, claim: dict[str, Any], to: str, actor_role: str, note: str,
                     **values: Any) -> dict[str, Any]:
    """Move a claim to `to` with optimistic locking on `version`."""
    result = await session.execute(update(claims).where(
        claims.c.claim_id == claim["claim_id"], claims.c.version == claim["version"]).values(
        state=to, version=claim["version"] + 1, updated_at=datetime.now(UTC), **values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This claim changed meanwhile", "Reload the claim and try again.")
    await session.execute(insert(claim_timeline).values(claim_id=claim["claim_id"], state=to, actor_role=actor_role, note=note))
    return {**claim, **values, "state": to, "version": claim["version"] + 1}


async def notify(session: AsyncSession, claim: dict[str, Any], template: str, correlation_id: str | None = None,
                 **params: Any) -> None:
    await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=claim["claim_id"], correlation_id=correlation_id, payload={
                        "recipient_subject": claim["member_subject"], "template": template,
                        "reference_id": claim["claim_id"], "params": {"amount_paise": claim["amount_paise"], **params}})


async def record_decision(session: AsyncSession, claim: dict[str, Any], decision: str, reason_code: str,
                          correlation_id: str | None = None) -> None:
    await add_event(session, producer=PRODUCER, event_type="ClaimDecisionRecorded.v1", aggregate_type="claim",
                    aggregate_id=claim["claim_id"], correlation_id=correlation_id, payload={
                        "claim_id": claim["claim_id"], "decision": decision, "reason_code": reason_code,
                        "rule_version": claim["rule_version"], "amount_paise": claim["amount_paise"],
                        "account_link_id": claim["account_link_id"]})


async def load_claim(session: AsyncSession, claim_id: str, *, member: str | None = None, office: str | None = None,
                     lock: bool = False) -> dict[str, Any]:
    q = select(claims).where(claims.c.claim_id == claim_id)
    if lock and session.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    row = (await session.execute(q)).mappings().first()
    if not row or (member and row["member_subject"] != member) or (office and row["office_id"] != office):
        raise Problem(404, "/problems/not-found", "Claim not found")   # never reveal another member's claim
    return dict(row)


async def claim_view(session: AsyncSession, claim: dict[str, Any]) -> dict[str, Any]:
    timeline = (await session.execute(select(claim_timeline).where(claim_timeline.c.claim_id == claim["claim_id"])
                                      .order_by(claim_timeline.c.id))).mappings().all()
    return {
        "claim_id": claim["claim_id"], "account_link_id": claim["account_link_id"], "claim_type": claim["claim_type"],
        "form_type": claim["form_type"], "amount_paise": claim["amount_paise"], "state": claim["state"],
        "version": claim["version"], "rule_version": claim["rule_version"], "summary": claim["summary"],
        "decision_reason": claim["decision_reason"], "payment_id": claim["payment_id"],
        "next_step": NEXT_STEP.get(claim["state"], ""),
        "timeline": [{"at": t["at"].isoformat() if t["at"] else None, "state": t["state"],
                      "by": ROLE_LABELS.get(t["actor_role"], t["actor_role"]), "note": t["note"]} for t in timeline],
    }


async def ensure_not_frozen(session: AsyncSession, claim: dict[str, Any], status: int) -> None:
    frozen = (await session.execute(select(accounts.c.frozen).where(
        accounts.c.account_link_id == claim["account_link_id"]))).scalar_one_or_none()
    if frozen:
        raise Problem(status, "/problems/account-frozen", "The account is frozen",
                      "Nothing is paid or confirmed while the account is under verification (FIA SOP, illustrative).")


async def member_accounts(session: AsyncSession, subject: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(accounts).where(accounts.c.member_subject == subject)
                                  .order_by(accounts.c.account_link_id))).mappings().all()
    return [dict(r) for r in rows]


async def staff_office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(
        office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office", "Ask HR to record your posting.")
    return office


# ── member routes ───────────────────────────────────────────────────────────────────────────────

async def previous_claims(session: AsyncSession, account_link_id: str, claim_type: str) -> list[date]:
    rows = (await session.execute(select(claims.c.created_at).where(
        claims.c.account_link_id == account_link_id, claims.c.claim_type == claim_type,
        claims.c.state.notin_(("REJECTED_WITH_REASON", "AWAITING_CONFIRMATION"))))).scalars().all()
    return [r.date() for r in rows if r]


@router.get("/api/v1/members/me/claims/eligible-types")
async def eligible_types(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    today = date.today()
    rules = await rules_on(session, today)                   # the rule set in force today
    out = []
    for a in await member_accounts(session, actor.subject):
        types = []
        for t, spec in rules["claims"]["types"].items():
            if spec.get("retired"):
                continue
            e = eligibility(a, t, rules, today, await previous_claims(session, a["account_link_id"], t))
            types.append({k: v for k, v in e.items() if k != "trace"})
        out.append({"account_link_id": a["account_link_id"],
                    "balance": {"employee_paise": a["employee_paise"], "employer_paise": a["employer_paise"],
                                "total_paise": a["employee_paise"] + a["employer_paise"]}, "types": types})
    return envelope({"rule_version": rules["rule_version"], "illustrative_only": True,
                     "auto_settlement_limit_paise": rules["claims"]["auto_settlement_limit_paise"], "accounts": out})


@router.post("/api/v1/members/me/claims", status_code=201)
async def create_claim(body: ClaimInput, request: Request, actor: Actor = Depends(MEMBER),
                       idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                       session: AsyncSession = Depends(db)) -> dict:
    operation, h = "POST /members/me/claims", request_hash(body.model_dump())
    async with session.begin():
        rules = await rules_on(session, date.today())
        offered = {k for k, v in rules["claims"]["types"].items() if not v.get("retired")}
        if body.claim_type not in offered:
            raise Problem(422, "/problems/validation", "This claim type is not offered", "Choose one of: " + ", ".join(sorted(offered)))
        if idempotency_key and (cached := await find_response(session, actor.subject, operation, idempotency_key, h)):
            return envelope(cached.body)
        account = next((a for a in await member_accounts(session, actor.subject)
                        if a["account_link_id"] == body.account_link_id), None)
        if not account:
            raise Problem(404, "/problems/not-found", "Account not found")
        if account["frozen"]:
            raise Problem(403, "/problems/account-frozen", "This account is on hold",
                          "A new claim cannot be filed while the account is under verification. Contact your regional office.")
        evaluation = eligibility(account, body.claim_type, rules, date.today(),
                                 await previous_claims(session, account["account_link_id"], body.claim_type))
        if not evaluation["eligible"]:
            raise Problem(422, "/problems/not-eligible", "You are not eligible for this claim today",
                          " ".join(evaluation["reasons"]), reasons=evaluation["reasons"])
        if body.amount_paise > evaluation["max_amount_paise"]:
            raise Problem(422, "/problems/amount-above-limit", "The amount is above your limit",
                          f"Enter at most {evaluation['max_amount_paise'] // 100} rupees.",
                          max_amount_paise=evaluation["max_amount_paise"])
        open_claim = (await session.execute(select(claims.c.claim_id).where(
            claims.c.account_link_id == body.account_link_id, claims.c.claim_type == body.claim_type,
            claims.c.state.in_(OPEN_STATES)))).scalar_one_or_none()
        if open_claim:
            raise Problem(409, "/problems/claim-already-open", "A claim of this type is already in progress",
                          f"Follow claim {open_claim}; you can file another once it is settled or rejected.",
                          claim_id=open_claim)
        claim_id = f"CLM-{secrets.token_hex(4).upper()}"
        text = summary(evaluation, body.amount_paise, rules)
        await session.execute(insert(claims).values(
            claim_id=claim_id, member_subject=actor.subject, account_link_id=body.account_link_id,
            claim_type=body.claim_type, form_type=evaluation["form_type"], amount_paise=body.amount_paise,
            state="AWAITING_CONFIRMATION", version=1, rule_version=rules["rule_version"], office_id=account["office_id"],
            evaluation=evaluation, summary=text))
        await session.execute(insert(claim_timeline).values(
            claim_id=claim_id, state="AWAITING_CONFIRMATION", actor_role="member",
            note="Claim prepared; waiting for your confirmation."))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.create",
                    target_type="claim", target_id=claim_id, detail=f"{body.claim_type} {body.amount_paise}")
        claim = await load_claim(session, claim_id)
        result = {**await claim_view(session, claim),
                  "rules_applied": {"rule_version": rules["rule_version"], "plain_rule": evaluation["plain_rule"],
                                    "max_amount_paise": evaluation["max_amount_paise"],
                                    "route": route(body.amount_paise, rules, body.claim_type),
                                    "approval_chain": [ROLE_LABELS[r] for r in approval_chain(body.amount_paise, rules, body.claim_type)]},
                  "confirmation": {"action": "confirm-claim", "resource_id": claim_id, "resource_version": 1,
                                   "amount_paise": body.amount_paise}}
        if idempotency_key:
            await store_response(session, actor.subject, operation, idempotency_key, h, 201, result)
    return envelope(result)


@router.post("/api/v1/members/me/claims/{claim_id}/confirmations")
async def confirm_claim(claim_id: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await load_claim(session, claim_id, member=actor.subject, lock=True)
        rules = await rules_by_version(session, claim["rule_version"])     # the rules the member was shown
        require_step_up(actor, "confirm-claim", claim_id, claim["version"], claim["amount_paise"])
        await ensure_not_frozen(session, claim, 403)
        if claim["state"] != "AWAITING_CONFIRMATION":
            raise Problem(409, "/problems/invalid-state", "This claim is already confirmed",
                          f"Current status: {claim['state']}.")
        claim = await transition(session, claim, "SUBMITTED", "member", "You confirmed the claim.")
        signal = (await session.execute(select(risk_flags.c.signal_id).where(
            risk_flags.c.subject == actor.subject, risk_flags.c.status != "BENIGN"))).scalars().first()
        path = "REVIEW" if signal else route(claim["amount_paise"], rules, claim["claim_type"])
        await add_event(session, producer=PRODUCER, event_type="ClaimSubmitted.v1", aggregate_type="claim",
                        aggregate_id=claim_id, correlation_id=actor.correlation_id, payload={
                            "claim_id": claim_id, "form_type": claim["form_type"], "amount_paise": claim["amount_paise"],
                            "rule_version": claim["rule_version"], "office_id": claim["office_id"],
                            "account_link_id": claim["account_link_id"], "route": path, "claim_type": claim["claim_type"],
                            "advisory_signal_id": signal})
        await notify(session, claim, "CLAIM_SUBMITTED", actor.correlation_id)
        if path == "AUTO":
            claim = await transition(session, claim, "AUTO_APPROVED", "system",
                                     "Within the automatic settlement limit; approved without an officer.")
            await record_decision(session, claim, "AUTO_APPROVED", "WITHIN_AUTO_LIMIT", actor.correlation_id)
            await notify(session, claim, "CLAIM_APPROVED", actor.correlation_id)
        else:
            chain = approval_chain(claim["amount_paise"], rules, claim["claim_type"])
            why = (" A routine security check on recent account activity asks an officer to look at this claim; "
                   "this is not an accusation and does not change what you are entitled to.") if signal else ""
            claim = await transition(session, claim, "UNDER_REVIEW", "system",
                                     "Sent to your regional office for review: "
                                     + " → ".join(ROLE_LABELS[r] for r in chain) + "." + why)
            await notify(session, claim, "CLAIM_UNDER_REVIEW", actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.confirm",
                    target_type="claim", target_id=claim_id, detail=path)
        view = await claim_view(session, claim)
    return envelope(view)


@router.get("/api/v1/members/me/claims")
async def list_claims(actor: Actor = Depends(require_stakeholder("member", "ext.umang")),
                      session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(claims).where(claims.c.member_subject == actor.subject)
                                  .order_by(claims.c.created_at.desc()))).mappings().all()
    return envelope([{"claim_id": r["claim_id"], "claim_type": r["claim_type"], "form_type": r["form_type"],
                      "amount_paise": r["amount_paise"], "state": r["state"], "next_step": NEXT_STEP.get(r["state"], ""),
                      "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows])


@router.get("/api/v1/members/me/claims/{claim_id}")
async def get_claim(claim_id: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    return envelope(await claim_view(session, await load_claim(session, claim_id, member=actor.subject)))


# ── cash section ────────────────────────────────────────────────────────────────────────────────

async def _instruct(session: AsyncSession, claim: dict[str, Any], actor: Actor, scenario: str, template: str | None) -> dict:
    attempt = claim["payment_attempt"] + 1
    payment_id = f"PAY-{claim['claim_id']}-{attempt}"
    claim = await transition(session, claim, "PAYMENT_PENDING", actor.stakeholder,
                             "Payment sent to the bank." if attempt == 1 else f"Payment re-issued (attempt {attempt}).",
                             payment_id=payment_id, payment_attempt=attempt)
    await add_event(session, producer=PRODUCER, event_type="PaymentInstructed.v1", aggregate_type="claim",
                    aggregate_id=claim["claim_id"], correlation_id=actor.correlation_id, payload={
                        "claim_id": claim["claim_id"], "payment_id": payment_id, "amount_paise": claim["amount_paise"],
                        "attempt": attempt, "demo_scenario": scenario})
    if template:
        await notify(session, claim, template, actor.correlation_id)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.payment_instructed",
                target_type="claim", target_id=claim["claim_id"], detail=payment_id)
    return {"claim_id": claim["claim_id"], "state": claim["state"], "payment_id": payment_id, "attempt": attempt,
            "amount_paise": claim["amount_paise"], "mock": True}


async def _cash_command(claim_id: str, action: str, allowed: set[str], body: PaymentInstructionInput, request: Request,
                        actor: Actor, key: str | None, session: AsyncSession, template: str | None) -> dict:
    if not key:
        raise Problem(400, "/problems/idempotency-key-required", "Idempotency-Key header is required",
                      "Send a unique Idempotency-Key so a retried instruction never pays twice.")
    if body.demo_scenario not in ("SUCCESS", "RETURN"):
        raise Problem(422, "/problems/validation", "demo_scenario must be SUCCESS or RETURN")
    operation, h = f"POST {request.url.path}", request_hash(body.model_dump())
    async with session.begin():
        if cached := await find_response(session, actor.subject, operation, key, h):
            return envelope(cached.body)
        claim = await load_claim(session, claim_id, office=await staff_office(session, actor), lock=True)
        require_step_up(actor, action, claim_id, None, claim["amount_paise"])
        if claim["state"] not in allowed:
            raise Problem(409, "/problems/invalid-state", "The claim is not ready for this payment step",
                          f"Current status: {claim['state']}.")
        await ensure_not_frozen(session, claim, 409)
        if not claim["debit_journal_id"]:
            raise Problem(409, "/problems/ledger-debit-pending", "The ledger debit is not posted yet",
                          "The member's account is being debited; try again in a few seconds.")
        result = await _instruct(session, claim, actor, body.demo_scenario, template)
        await store_response(session, actor.subject, operation, key, h, 200, result)
    return envelope(result)


@router.post("/api/v1/office/claims/{claim_id}/payment-instructions")
async def payment_instruction(claim_id: str, body: PaymentInstructionInput, request: Request,
                              actor: Actor = Depends(CASHIER),
                              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                              session: AsyncSession = Depends(db)) -> dict:
    return await _cash_command(claim_id, "instruct-payment", {"APPROVED", "AUTO_APPROVED"}, body, request, actor,
                               idempotency_key, session, None)


@router.post("/api/v1/office/claims/{claim_id}/reissues")
async def reissue(claim_id: str, body: PaymentInstructionInput, request: Request, actor: Actor = Depends(CASHIER),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                  session: AsyncSession = Depends(db)) -> dict:
    # Phase 1 re-issues straight from PAYMENT_RETURNED; the member bank-detail correction and APFC
    # re-disbursement approval in between (init.md §7) are phase 2 endpoints.
    return await _cash_command(claim_id, "reissue-payment", {"PAYMENT_RETURNED"}, body, request, actor,
                               idempotency_key, session, "CLAIM_REISSUED")
