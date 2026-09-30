"""claim-service: member claims (Journey B3) and the cash section's payment instructions (Journey B6).

State machine: init.md §7 "Claim". Every transition bumps `version`, writes a timeline row and is
checked against the current state; anything else is 409."""
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.claims import NEXT_STEP, OPEN_STATES, ROLE_LABELS, approval_chain, eligibility, months_between, route, rupees, summary
from app.infra.db import sessions
from app.infra.tables import accounts, cads, claim_beneficiaries, claim_timeline, claims, office_staff, risk_flags, tax_declarations
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response
from epfo_persistence.policy import financial_year, rules_by_version, rules_on, tds_on

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
                     reason: str = "", **values: Any) -> dict[str, Any]:
    """Move a claim to `to` with optimistic locking on `version`."""
    result = await session.execute(update(claims).where(
        claims.c.claim_id == claim["claim_id"], claims.c.version == claim["version"]).values(
        state=to, version=claim["version"] + 1, updated_at=datetime.now(UTC), **values))
    if result.rowcount != 1:
        raise Problem(409, "/problems/version-conflict", "This claim changed meanwhile", "Reload the claim and try again.")
    await session.execute(insert(claim_timeline).values(claim_id=claim["claim_id"], state=to, actor_role=actor_role, note=note))
    await add_event(session, producer=PRODUCER, event_type="ClaimStateChanged.v1", aggregate_type="claim",
                    aggregate_id=claim["claim_id"], payload={
                        "claim_id": claim["claim_id"], "from_state": claim["state"], "to_state": to, "reason": reason,
                        "claim_type": claim["claim_type"], "amount_paise": claim["amount_paise"],
                        "rule_version": claim["rule_version"], "office_id": claim["office_id"],
                        "account_link_id": claim["account_link_id"]})
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
                        "account_link_id": claim["account_link_id"],
                        "fund": {"DEATH_EDLI": "EDLI", "PENSION_WITHDRAWAL": "EPS"}.get(claim["claim_type"], "MEMBER_ACCOUNT")})   # EDLI is paid from the EDLI fund


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
        "next_step": NEXT_STEP.get(claim["state"], ""), "tax": claim.get("tax"),
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


WHOLE_BALANCE_TYPES = {"FINAL_SETTLEMENT", "PENSION_WITHDRAWAL"}


async def member_id_reasons(session: AsyncSession, account: dict[str, Any], claim_type: str) -> list[str]:
    """P2.7d: claims go against the primary member ID; a claim for the whole balance needs every other member ID of
    the member's Aadhaar-verified set transferred first (tracker: "all services are not transferred to primary member id")."""
    siblings = [dict(r) for r in (await session.execute(select(accounts).where(
        accounts.c.set_key == account["set_key"], accounts.c.account_link_id != account["account_link_id"]))).mappings().all()] \
        if account.get("set_key") else []
    reasons = []
    if not account.get("is_primary"):
        primary = next((x["account_link_id"] for x in siblings if x["is_primary"]), None)
        reasons.append(f"Requested member ID does not match with the primary member ID{f' ({primary})' if primary else ''}. "
                       "Claims are made against the primary member ID.")
    elif claim_type in WHOLE_BALANCE_TYPES:
        held = [x for x in siblings if x["employee_paise"] + x["employer_paise"] > 0]
        if held:
            reasons.append("All services are not transferred to the primary member ID: "
                           + ", ".join(f"{x['account_link_id']} holds {rupees(x['employee_paise'] + x['employer_paise'])}" for x in held)
                           + ". Transfer them first (Form 13).")
    return reasons


async def evaluate(session: AsyncSession, account: dict[str, Any], claim_type: str, rules: dict[str, Any], today: date) -> dict[str, Any]:
    e = eligibility(account, claim_type, rules, today, await previous_claims(session, account["account_link_id"], claim_type))
    extra = await member_id_reasons(session, account, claim_type)
    return {**e, "eligible": False, "max_amount_paise": 0, "reasons": [*e["reasons"], *extra]} if extra else e


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
            e = await evaluate(session, a, t, rules, today)
            types.append({k: v for k, v in e.items() if k != "trace"})
        out.append({"account_link_id": a["account_link_id"], "primary": bool(a.get("is_primary")),
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
        evaluation = await evaluate(session, account, body.claim_type, rules, date.today())
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

async def work_out_tax(session: AsyncSession, claim: dict[str, Any], day: date) -> dict[str, Any]:
    """TDS under the rules in force on the payment date (illustrative), with the member's PAN status, service and
    any Form 15G / 15H for that financial year. Worked out once, at the first payment instruction."""
    account = (await session.execute(select(accounts).where(accounts.c.account_link_id == claim["account_link_id"]))).mappings().one()
    fy = financial_year(day)
    declared = (await session.execute(select(tax_declarations.c.form).where(
        tax_declarations.c.member_subject == claim["member_subject"], tax_declarations.c.financial_year == fy))).scalar_one_or_none()
    rules = await rules_on(session, day)
    service = months_between(account["date_of_joining"], account["date_of_exit"] or day)
    t = tds_on(claim["amount_paise"], claim["claim_type"], service, account["pan_verified"], declared is not None, rules)
    return {**t, "gross_paise": claim["amount_paise"], "net_paise": claim["amount_paise"] - t["tds_paise"],
            "rule_version": rules["rule_version"], "financial_year": fy, "service_months": service, "declaration": declared,
            "payment_date": day.isoformat()}


async def _instruct(session: AsyncSession, claim: dict[str, Any], actor: Actor, scenario: str, template: str | None) -> dict:
    if claim.get("death_of_uan"):                              # a death claim is paid only when the shares add up
        shares = (await session.execute(select(func.coalesce(func.sum(claim_beneficiaries.c.share_bp), 0)).where(
            claim_beneficiaries.c.claim_id == claim["claim_id"]))).scalar_one()
        if int(shares) != 10_000:
            raise Problem(409, "/problems/shares-incomplete", "The beneficiaries' shares do not add up to 100%",
                          f"They add up to {int(shares) / 100:g}%. The APFC amends the shares first.")
    attempt = claim["payment_attempt"] + 1
    payment_id = f"PAY-{claim['claim_id']}-{attempt}"
    first_tax = claim.get("tax") is None
    cad = (await session.execute(select(cads.c.tax).where(cads.c.claim_id == claim["claim_id"])            # the last docket
                                 .order_by(cads.c.created_at.desc(), cads.c.cad_id).limit(1))).scalar_one_or_none()
    # The last Claim Approval Docket (the approver's) fixes the figures; otherwise they are worked out now.
    tax = (cad or await work_out_tax(session, claim, datetime.now(UTC).date())) if first_tax else claim["tax"]
    withheld = f" Income tax of ₹{tax['tds_paise'] // 100:,} withheld (TDS, {tax['basis']})" if tax["tds_paise"] else ""
    claim = await transition(session, claim, "PAYMENT_PENDING", actor.stakeholder,
                             ("Payment sent to the bank." if attempt == 1 else f"Payment re-issued (attempt {attempt}).") + withheld,
                             payment_id=payment_id, payment_attempt=attempt, tax=tax)
    if first_tax and tax["tds_paise"]:
        await add_event(session, producer=PRODUCER, event_type="TaxDeducted.v1", aggregate_type="claim",
                        aggregate_id=claim["claim_id"], correlation_id=actor.correlation_id, payload={
                            "claim_id": claim["claim_id"], "account_link_id": claim["account_link_id"], "gross_paise": tax["gross_paise"],
                            "tds_paise": tax["tds_paise"], "net_paise": tax["net_paise"], "rate_bp": tax["rate_bp"],
                            "rule_version": tax["rule_version"], "financial_year": tax["financial_year"], "basis": tax["basis"]})
    await add_event(session, producer=PRODUCER, event_type="PaymentInstructed.v1", aggregate_type="claim",
                    aggregate_id=claim["claim_id"], correlation_id=actor.correlation_id, payload={
                        "claim_id": claim["claim_id"], "payment_id": payment_id, "amount_paise": tax["net_paise"],
                        "attempt": attempt, "demo_scenario": scenario})
    if template:
        await notify(session, claim, template, actor.correlation_id)
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.payment_instructed",
                target_type="claim", target_id=claim["claim_id"], detail=payment_id)
    return {"claim_id": claim["claim_id"], "state": claim["state"], "payment_id": payment_id, "attempt": attempt,
            "amount_paise": claim["amount_paise"], "tds_paise": tax["tds_paise"], "net_paise": tax["net_paise"], "mock": True}


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
        await ensure_not_frozen(session, claim, 409)
        if claim["state"] not in allowed:
            raise Problem(409, "/problems/invalid-state", "The claim is not ready for this payment step",
                          f"Current status: {claim['state']}.")
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
    # Only after the member corrected the bank details and an APFC approved the re-disbursement (init.md §7).
    return await _cash_command(claim_id, "reissue-payment", {"REISSUE_APPROVED"}, body, request, actor,
                               idempotency_key, session, "CLAIM_REISSUED")



# ── re-disbursement after a bank return (init.md §7) ────────────────────────────────────────────

class BankDetails(BaseModel):
    ifsc: str = Field(pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    account_number: str = Field(pattern=r"^[0-9]{9,18}$")


def penny_drop_ok(ifsc: str, account_number: str) -> bool:
    """MOCK penny-drop verification: synthetic accounts ending in 0000 are treated as closed."""
    return not account_number.endswith("0000")


@router.post("/api/v1/members/me/claims/{claim_id}/re-disbursement-requests")
async def request_redisbursement(claim_id: str, body: BankDetails, actor: Actor = Depends(MEMBER),
                                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await load_claim(session, claim_id, member=actor.subject, lock=True)
        if claim["state"] != "PAYMENT_RETURNED":
            raise Problem(409, "/problems/invalid-state", "Bank details can be corrected only after the bank returned the payment",
                          f"Current status: {claim['state']}.")
        if not penny_drop_ok(body.ifsc, body.account_number):
            raise Problem(422, "/problems/penny-drop-failed", "The bank could not confirm this account",
                          "Check the account number and IFSC with your bank (mock penny-drop check).")
        claim = await transition(session, claim, "CORRECTION_PENDING", "member",
                                 f"New bank account ending {body.account_number[-4:]} submitted; an APFC will approve the re-payment.",
                                 payee_ifsc=body.ifsc, payee_account_last4=body.account_number[-4:])
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.redisbursement_request",
                    target_type="claim", target_id=claim_id)
        view = await claim_view(session, claim)
    return envelope(view)


class RedisbursementDecision(BaseModel):
    decision: str                                         # APPROVE | REJECT
    note: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/office/claims/{claim_id}/re-disbursement-approvals")
async def approve_redisbursement(claim_id: str, body: RedisbursementDecision,
                                 actor: Actor = Depends(require_stakeholder("fo.apfc")),
                                 session: AsyncSession = Depends(db)) -> dict:
    if body.decision not in ("APPROVE", "REJECT"):
        raise Problem(422, "/problems/validation", "decision must be APPROVE or REJECT")
    async with session.begin():
        claim = await load_claim(session, claim_id, office=await staff_office(session, actor), lock=True)
        require_step_up(actor, "approve-redisbursement", claim_id, None, claim["amount_paise"])
        if claim["state"] != "CORRECTION_PENDING":
            raise Problem(409, "/problems/invalid-state", "No re-disbursement is waiting for approval", f"Current status: {claim['state']}.")
        if body.decision == "APPROVE":             # adjudication is not reopened: only the payee account changes
            claim = await transition(session, claim, "REISSUE_APPROVED", actor.stakeholder,
                                     f"Re-payment to the account ending {claim['payee_account_last4']} approved.")
        else:
            claim = await transition(session, claim, "PAYMENT_RETURNED", actor.stakeholder, f"New bank details not accepted: {body.note}")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"claim.redisbursement_{body.decision.lower()}", target_type="claim", target_id=claim_id, detail=body.note)
        view = await claim_view(session, claim)
    return envelope(view)


# ── Form 15G / 15H (self-declaration that no tax is payable; waives TDS when the policy allows it) ─────

class TaxDeclaration(BaseModel):
    form: str = Field(pattern=r"^15[GH]$")
    declaration: bool                                   # "my estimated income for the year is not taxable"


@router.post("/api/v1/members/me/tax/form-15g-15h", status_code=201)
async def declare_no_tax(body: TaxDeclaration, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    if not body.declaration:
        raise Problem(422, "/problems/validation", "The declaration must be confirmed")
    fy = financial_year(datetime.now(UTC).date())
    async with session.begin():
        existing = (await session.execute(select(tax_declarations).where(
            tax_declarations.c.member_subject == actor.subject, tax_declarations.c.financial_year == fy))).mappings().first()
        if existing:
            raise Problem(409, "/problems/already-declared", f"Form {existing['form']} is already on file for {fy}")
        await session.execute(insert(tax_declarations).values(member_subject=actor.subject, financial_year=fy, form=body.form))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="tax.declaration",
                    target_type="member", target_id=actor.subject, detail=f"Form {body.form} for {fy}")
    return envelope({"form": body.form, "financial_year": fy,
                     "effect": "No TDS on withdrawals paid this financial year, while the policy allows the waiver. "
                               "A false declaration is an offence (illustrative)."})
