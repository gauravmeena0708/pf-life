"""Phase 2, slice 5b: claims on a member's death — PF (Form 20) and EDLI (Form 5IF) — filed by a nominee or legal
heir, with the beneficiaries' shares; and paper claims and updations inwarded at the PRO counter.

A death claim runs through the same officer chain and payment as any claim; the EDLI benefit is worked out from
the rules in force and paid from the EDLI fund; payment waits until the shares add up to 100 %."""
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import claim_view, db, load_claim, member_id_reasons, staff_office, transition
from app.domain.claims import ROLE_LABELS, approval_chain, months_between, rupees
from app.infra.tables import accounts, claim_beneficiaries, claim_timeline, claims, nominations, physical_intakes
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response
from epfo_persistence.policy import edli_benefit, rules_on

router = APIRouter()
PRODUCER = "claim-service"
CLAIMANT = require_stakeholder("claimant")
SYNTHETIC_AVERAGE_WAGES = 1500000          # the synthetic members' monthly wages (₹15,000)
FORMS = {"FORM_20": ("DEATH_PF", "20", "PF on a member's death"), "FORM_5IF": ("DEATH_EDLI", "5IF", "EDLI assurance benefit")}


class Beneficiary(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    relation: str = Field(pattern="^(SPOUSE|SON|DAUGHTER|FATHER|MOTHER|LEGAL_HEIR|GUARDIAN)$")
    share_bp: int = Field(default=0, ge=0, le=10000)
    bank_account_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")


class DeathClaimInput(BaseModel):
    form_type: str = Field(pattern="^(FORM_20|FORM_5IF|CCF_DEATH)$")
    deceased_uan: str = Field(pattern=r"^[0-9]{12}$")
    process_as: str = Field(default="E_NOMINATION", pattern="^(E_NOMINATION|LSM|NEW_BENEFICIARIES)$")
    beneficiaries: list[Beneficiary] = Field(default_factory=list)


async def _beneficiaries(session: AsyncSession, claim_id: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(claim_beneficiaries).where(claim_beneficiaries.c.claim_id == claim_id)
                                  .order_by(claim_beneficiaries.c.beneficiary_id))).mappings().all()
    return [dict(r) for r in rows]


def _share_view(claim: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    net = (claim.get("tax") or {}).get("net_paise", claim["amount_paise"])
    allocated = net * b["share_bp"] // 10_000
    return {"beneficiary_id": b["beneficiary_id"], "name": b["name"], "relation": b["relation"], "share_pct": b["share_bp"] / 100,
            "source": b["source"], "allocated_paise": allocated, "legacy_settled_paise": b["legacy_settled_paise"],
            "disbursed_paise": b["disbursed_paise"], "pending_paise": max(0, allocated - b["legacy_settled_paise"] - b["disbursed_paise"]),
            "amendments": b["amendments"]}


@router.post("/api/v1/claimants/death-claims", status_code=201)
async def file_death_claim(body: DeathClaimInput, request: Request, actor: Actor = Depends(CLAIMANT),
                           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                           session: AsyncSession = Depends(db)) -> dict:
    operation, h = f"POST {request.url.path}", request_hash(body.model_dump())
    async with session.begin():
        if idempotency_key and (cached := await find_response(session, actor.subject, operation, idempotency_key, h)):
            return envelope(cached.body)
        noms = [dict(n) for n in (await session.execute(select(nominations).where(nominations.c.uan == body.deceased_uan))).mappings().all()]
        if not any(n["subject"] == actor.subject for n in noms):
            raise Problem(404, "/problems/not-found", "No nomination of yours for that UAN",
                          "A legal heir without a nomination files at the PRO counter with a succession certificate.")
        account = (await session.execute(select(accounts).where(accounts.c.uan == body.deceased_uan, accounts.c.deceased_on.is_not(None))
                                         .order_by(accounts.c.is_primary.desc(), accounts.c.date_of_joining.desc()))).mappings().first()
        if not account:
            raise Problem(422, "/problems/death-not-recorded", "The member's death is not recorded",
                          "The employer marks the exit with the reason 'death while in service' first.")
        not_moved = await member_id_reasons(session, {**dict(account), "is_primary": True}, "FINAL_SETTLEMENT")
        if not_moved:                                  # the claim is inwarded against the primary member ID only
            raise Problem(422, "/problems/services-not-transferred", "All services are not transferred to the primary member ID",
                          " ".join(not_moved) + " The office transfers them before the claim is filed.")
        require_step_up(actor, "file-death-claim", body.deceased_uan)
        rules = await rules_on(session, date.today())
        balance = account["employee_paise"] + account["employer_paise"]
        service = months_between(account["date_of_joining"], account["deceased_on"])
        if body.process_as == "E_NOMINATION":
            people = [Beneficiary(name=n["name"], relation=n["relation"], share_bp=n["share_bp"], bank_account_last4=n["bank_account_last4"]) for n in noms]
        elif not body.beneficiaries:
            raise Problem(422, "/problems/validation", "List the surviving family members / new beneficiaries")
        else:
            people = body.beneficiaries
        composite_ref = f"CCF-{secrets.token_hex(6).upper()}" if body.form_type == "CCF_DEATH" else None
        forms = ("FORM_20", "FORM_5IF") if composite_ref else (body.form_type,)
        views = []
        for form_type in forms:
            views.append(await _file_one(session, form_type, body, actor, account, rules, balance, service, people, composite_ref))
        result = ({"composite_ref": composite_ref, "claims": views,
                   "next_step": "Family pension (Form 10D) is settled by the pension section; file Form 10D at the PRO counter."}
                  if composite_ref else views[0])
        if idempotency_key:
            await store_response(session, actor.subject, operation, idempotency_key, h, 201, result)
    return envelope(result)


async def _file_one(session: AsyncSession, form_type: str, body: DeathClaimInput, actor: Actor,
                    account: dict[str, Any], rules: dict[str, Any], balance: int, service: int,
                    people: list[Beneficiary], composite_ref: str | None) -> dict[str, Any]:
    claim_type, form, label = FORMS[form_type]
    open_claim = (await session.execute(select(claims.c.claim_id).where(claims.c.death_of_uan == body.deceased_uan,
                                                                        claims.c.claim_type == claim_type,
                                                                        claims.c.state.notin_(("REJECTED_WITH_REASON", "CANCELLED"))))).first()
    if open_claim:
        raise Problem(409, "/problems/claim-already-open", f"A {label} claim is already on file", f"Claim {open_claim[0]}.", claim_id=open_claim[0])
    if claim_type == "DEATH_EDLI":
        benefit = edli_benefit(SYNTHETIC_AVERAGE_WAGES, balance, service, rules)
        amount, working = benefit["amount_paise"], benefit["working"]
    else:
        amount, working = balance, "The PF balance of the member ID"
    if amount <= 0:
        raise Problem(422, "/problems/not-eligible", "There is nothing to pay on this member ID")
    claim_id = f"CLM-{secrets.token_hex(4).upper()}"
    chain = approval_chain(amount, rules, claim_type)
    text = (f"{label} (Form {form}) for the late member with UAN ending {body.deceased_uan[-4:]}: {rupees(amount)} — {working}. "
            f"Paid to {len(people)} beneficiaries in their shares. Reviewed by: {' → '.join(ROLE_LABELS[r] for r in chain)}. "
            f"Illustrative rules {rules['rule_version']}.")
    await session.execute(insert(claims).values(
        claim_id=claim_id, member_subject=actor.subject, account_link_id=account["account_link_id"], claim_type=claim_type, form_type=form,
        amount_paise=amount, state="SUBMITTED", version=1, rule_version=rules["rule_version"], office_id=account["office_id"],
        evaluation={"working": working, "service_months": service, "balance_paise": balance, "process_as": body.process_as},
        summary=text, death_of_uan=body.deceased_uan, composite_ref=composite_ref))
    await session.execute(insert(claim_timeline).values(claim_id=claim_id, state="SUBMITTED", actor_role="claimant",
                                                        note=f"Form {form} filed by the nominee ({body.process_as.replace('_', ' ').lower()})."))
    for i, p in enumerate(people, start=1):
        await session.execute(insert(claim_beneficiaries).values(
            beneficiary_id=f"{claim_id}-B{i}", claim_id=claim_id, name=p.name.upper(), relation=p.relation, share_bp=p.share_bp,
            source=body.process_as, bank_account_last4=p.bank_account_last4, amendments=[]))
    claim = await load_claim(session, claim_id)
    await add_event(session, producer=PRODUCER, event_type="ClaimSubmitted.v1", aggregate_type="claim", aggregate_id=claim_id,
                    correlation_id=actor.correlation_id, payload={
                        "claim_id": claim_id, "form_type": form, "amount_paise": amount, "rule_version": rules["rule_version"],
                        "office_id": account["office_id"], "account_link_id": account["account_link_id"], "route": "REVIEW",
                        "advisory_signal_id": None, "claim_type": claim_type})
    claim = await transition(session, claim, "UNDER_REVIEW", "system", "Sent to the regional office: " + " → ".join(ROLE_LABELS[r] for r in chain) + ".")
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.death_filed",
                target_type="claim", target_id=claim_id, detail=f"{claim_type} {body.deceased_uan}")
    view = await _claimant_view(session, claim)
    return view


async def _claimant_view(session: AsyncSession, claim: dict[str, Any]) -> dict[str, Any]:
    v = await claim_view(session, claim)
    return {k: v[k] for k in ("claim_id", "claim_type", "form_type", "amount_paise", "state", "summary", "next_step", "timeline", "decision_reason")} | (
        {"composite_ref": claim["composite_ref"]} if claim["composite_ref"] else {}) | {
        "beneficiaries": [_share_view(claim, b) for b in await _beneficiaries(session, claim["claim_id"])]}


@router.get("/api/v1/claimants/death-claims/{claim_id}")
async def my_death_claim(claim_id: str, actor: Actor = Depends(CLAIMANT), session: AsyncSession = Depends(db)) -> dict:
    claim = await load_claim(session, claim_id, member=actor.subject)
    if not claim.get("death_of_uan"):
        raise Problem(404, "/problems/not-found", "Claim not found")
    return envelope(await _claimant_view(session, claim))


@router.post("/api/v1/claimants/death-claims/{claim_id}/beneficiaries", status_code=201)
async def add_beneficiary(claim_id: str, body: Beneficiary, actor: Actor = Depends(CLAIMANT), session: AsyncSession = Depends(db)) -> dict:
    """A co-beneficiary or legal heir left out: added with no share; the APFC sets the shares."""
    async with session.begin():
        claim = await load_claim(session, claim_id, member=actor.subject, lock=True)
        if not claim.get("death_of_uan") or claim["state"] in ("SETTLED", "REJECTED_WITH_REASON", "CANCELLED", "PAYMENT_PENDING"):
            raise Problem(409, "/problems/invalid-state", "Beneficiaries can no longer be added to this claim")
        n = (await session.execute(select(func.count()).select_from(claim_beneficiaries).where(claim_beneficiaries.c.claim_id == claim_id))).scalar_one()
        await session.execute(insert(claim_beneficiaries).values(
            beneficiary_id=f"{claim_id}-B{n + 1}", claim_id=claim_id, name=body.name.upper(), relation=body.relation, share_bp=0,
            source="ADDED_BY_CLAIMANT", bank_account_last4=body.bank_account_last4, amendments=[]))
        await session.execute(insert(claim_timeline).values(claim_id=claim_id, state=claim["state"], actor_role="claimant",
                                                            note=f"Beneficiary {body.name.upper()} ({body.relation.lower()}) added; the APFC sets the shares."))
        view = await _claimant_view(session, claim)
    return envelope(view)


class ShareAmendment(BaseModel):
    share_bp: int = Field(ge=0, le=10000)
    legacy_settled_paise: int = Field(default=0, ge=0)
    reason: str = Field(pattern="^(NOMINEE_DECEASED|COURT_ORDER|LEGACY_SETTLEMENT_OFFSET|GUARDIAN_APPOINTMENT|ADDED_HEIR)$")
    note: str = Field(min_length=5, max_length=500)


APFC = require_stakeholder("fo.apfc")


@router.put("/api/v1/office/death-claims/{claim_id}/beneficiaries/{beneficiary_id}/shares")
async def amend_share(claim_id: str, beneficiary_id: str, body: ShareAmendment, actor: Actor = Depends(APFC), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await load_claim(session, claim_id, office=await staff_office(session, actor), lock=True)
        if not claim.get("death_of_uan") or claim["state"] in ("SETTLED", "PAYMENT_PENDING", "REJECTED_WITH_REASON"):
            raise Problem(409, "/problems/invalid-state", "Shares can no longer be amended on this claim")
        people = await _beneficiaries(session, claim_id)
        b = next((x for x in people if x["beneficiary_id"] == beneficiary_id), None)
        if not b:
            raise Problem(404, "/problems/not-found", "Beneficiary not found")
        require_step_up(actor, "amend-share", beneficiary_id)
        total = sum(x["share_bp"] for x in people if x["beneficiary_id"] != beneficiary_id) + body.share_bp
        if total > 10_000:
            raise Problem(422, "/problems/shares-exceed", "The shares would add up to more than 100%", f"They would total {total / 100:g}%.")
        amendment = {"from_bp": b["share_bp"], "to_bp": body.share_bp, "legacy_settled_paise": body.legacy_settled_paise, "reason": body.reason,
                     "note": body.note, "by_role": actor.stakeholder}
        await session.execute(update(claim_beneficiaries).where(claim_beneficiaries.c.beneficiary_id == beneficiary_id).values(
            share_bp=body.share_bp, legacy_settled_paise=body.legacy_settled_paise, amendments=[*b["amendments"], amendment]))
        await add_event(session, producer=PRODUCER, event_type="BeneficiaryShareAmended.v1", aggregate_type="claim", aggregate_id=claim_id,
                        correlation_id=actor.correlation_id, payload={"claim_id": claim_id, "beneficiary_id": beneficiary_id,
                                                                      "previous_share_bp": b["share_bp"], "new_share_bp": body.share_bp,
                                                                      "reason_code": body.reason if body.reason != "ADDED_HEIR" else "COURT_ORDER",
                                                                      "amended_by": actor.subject})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.share_amended",
                    target_type="claim", target_id=claim_id, detail=f"{beneficiary_id} {b['share_bp']}→{body.share_bp} {body.reason}")
    return envelope(await _summary(session, claim))


async def _summary(session: AsyncSession, claim: dict[str, Any]) -> dict[str, Any]:
    rows = [_share_view(claim, b) for b in await _beneficiaries(session, claim["claim_id"])]
    total_bp = sum(round(r["share_pct"] * 100) for r in rows)
    return {"claim_id": claim["claim_id"], "claim_type": claim["claim_type"], "state": claim["state"], "amount_paise": claim["amount_paise"],
            "shares_total_pct": total_bp / 100, "payable": total_bp == 10_000, "beneficiaries": rows,
            "totals": {k: sum(r[k] for r in rows) for k in ("allocated_paise", "legacy_settled_paise", "disbursed_paise", "pending_paise")}}


@router.get("/api/v1/office/death-claims/{claim_id}/shares-summary")
async def shares_summary(claim_id: str, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.da_accounts", "fo.ao", "fo.cash")),
                         session: AsyncSession = Depends(db)) -> dict:
    claim = await load_claim(session, claim_id, office=await staff_office(session, actor))
    if not claim.get("death_of_uan"):
        raise Problem(404, "/problems/not-found", "Not a death claim")
    return envelope(await _summary(session, claim))


# ── the PRO counter: paper claims and updations ─────────────────────────────────────────────────

PRO_FORMS = {"FORM_20", "FORM_10D", "FORM_13", "FORM_5IF", "SCHEME_CERTIFICATE_SURRENDER", "PPO_AMENDMENT_BENEFICIARY", "PPO_AMENDMENT_SERVICE",
             "PPO_AMENDMENT_POHW", "DEATH_UPDATION", "PHYSICAL_LC_UPDATION", "SPOUSE_REMARRIAGE_UPDATION", "FORM_19", "FORM_31"}
PENSION_UPDATIONS = {"PPO_AMENDMENT_BENEFICIARY", "PPO_AMENDMENT_SERVICE", "PPO_AMENDMENT_POHW", "DEATH_UPDATION", "PHYSICAL_LC_UPDATION",
                     "SPOUSE_REMARRIAGE_UPDATION"}


class IntakeInput(BaseModel):
    form_type: str
    uan: str = Field(pattern=r"^[0-9]{12}$")
    ppo_id: str | None = Field(default=None, max_length=40)
    filed_by: str = Field(pattern="^(MEMBER|BENEFICIARY|PENSIONER)$")
    claim_mode: str = Field(default="IN_PERSON", pattern="^(IN_PERSON|BY_POST)$")
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/office/physical-claims", status_code=201)
async def inward(body: IntakeInput, actor: Actor = Depends(require_stakeholder("fo.pro_intake", "fo.diary")), session: AsyncSession = Depends(db)) -> dict:
    """PRO counter: register a paper claim or updation. Pension updations go to the pension office's tracker."""
    if body.form_type not in PRO_FORMS:
        raise Problem(422, "/problems/validation", "Unknown request form type", "Choose one of: " + ", ".join(sorted(PRO_FORMS)))
    if body.form_type in PENSION_UPDATIONS and not body.ppo_id:
        raise Problem(422, "/problems/validation", "A PPO number is needed for a pension updation")
    async with session.begin():
        office = await staff_office(session, actor)
        intake = {"intake_id": f"INW-{secrets.token_hex(4).upper()}", "form_type": body.form_type, "uan": body.uan, "ppo_id": body.ppo_id,
                  "filed_by": body.filed_by, "claim_mode": body.claim_mode, "details": body.details, "office_id": office,
                  "inwarded_by": actor.subject, "state": "ROUTED" if body.form_type in PENSION_UPDATIONS else "INWARDED"}
        await session.execute(insert(physical_intakes).values(**intake))
        await add_event(session, producer=PRODUCER, event_type="PhysicalClaimInwarded.v1", aggregate_type="physical_intake",
                        aggregate_id=intake["intake_id"], correlation_id=actor.correlation_id, payload={
                            "intake_id": intake["intake_id"], "form_type": body.form_type, "uan": body.uan, "ppo_id": body.ppo_id or "",
                            "office_id": office, "filed_by": body.filed_by, "details": body.details})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="intake.inwarded",
                    target_type="physical_intake", target_id=intake["intake_id"], detail=body.form_type)
    return envelope({**intake, "next_step": "Sent to the pension office's updation tracker." if intake["state"] == "ROUTED"
                     else "Validate the member's identity next; then the dealing assistant enters the claim."})
