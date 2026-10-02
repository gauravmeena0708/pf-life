"""Phase 2, slice 8b: claims that wait for the employer's attestation, switching a claim's bank account before
payment, and auto-transfer on a change of job. Illustrative rules:

* a claim on a member ID whose UAN has no verified Aadhaar goes to the employer's authorised signatory, who attests
  it (it then goes on as any claim does) or rejects it with a reason;
* until the payment goes to the bank, the member may switch the claim to another of their KYC-verified accounts;
* an exited member ID of the member's Aadhaar-verified set that still holds a balance is offered for transfer into
  the primary member ID; the member confirms it (no Form 13, no employer, no office) and contribution-service posts
  the transfer from AutoTransferConfirmed.v1. A verified Aadhaar is required."""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import MEMBER, PRODUCER, claim_view, db, load_claim, notify, send_on, transition
from app.domain.claims import BANK_SWITCHABLE, OPEN_STATES, rupees
from app.infra.tables import accounts, auto_transfers, claim_timeline, claims, member_bank_accounts
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_by_version

router = APIRouter()
SIGNATORY = require_stakeholder("employer.signatory")
EMPLOYER_READ = require_stakeholder("employer.signatory", "employer.owner")


# ── employer attestation ────────────────────────────────────────────────────────────────────────

async def _attestable(session: AsyncSession, establishment_id: str | None) -> list[dict[str, Any]]:
    rows = (await session.execute(select(claims, accounts.c.uan, accounts.c.establishment_id).join(
        accounts, accounts.c.account_link_id == claims.c.account_link_id).where(
        claims.c.state == "PENDING_EMPLOYER_ATTESTATION", accounts.c.establishment_id == (establishment_id or "-"))
        .order_by(claims.c.created_at))).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/v1/employers/me/claim-attestations")
async def attestations(actor: Actor = Depends(EMPLOYER_READ), session: AsyncSession = Depends(db)) -> dict:
    rows = await _attestable(session, actor.establishment_id)
    return envelope([{"claim_id": r["claim_id"], "uan": r["uan"], "account_link_id": r["account_link_id"],
                      "claim_type": r["claim_type"], "form_type": r["form_type"], "amount_paise": r["amount_paise"],
                      "version": r["version"], "summary": r["summary"],
                      "filed_at": r["created_at"].isoformat() if r["created_at"] else None,
                      "why": "The member's Aadhaar is not verified."} for r in rows])


class AttestationDecision(BaseModel):
    decision: str = Field(pattern="^(ATTEST|REJECT)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/employers/me/claim-attestations/{claimId}/decisions")
async def attest(claimId: str, body: AttestationDecision, actor: Actor = Depends(SIGNATORY),
                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = next((r for r in await _attestable(session, actor.establishment_id) if r["claim_id"] == claimId), None)
        if not claim:
            raise Problem(404, "/problems/not-found", "No claim of your establishment is waiting for attestation with this number")
        claim = await load_claim(session, claimId, lock=True)
        require_step_up(actor, "attest-claim", claimId, claim["version"])
        if body.decision == "ATTEST":
            claim = await transition(session, claim, "SUBMITTED", "employer.signatory", f"Attested by your employer: {body.note}")
            claim, _ = await send_on(session, claim, await rules_by_version(session, claim["rule_version"]), actor.correlation_id)
        else:
            claim = await transition(session, claim, "REJECTED_BY_EMPLOYER", "employer.signatory",
                                     f"Your employer did not attest the claim: {body.note}", reason="EMPLOYER_REJECTED",
                                     decision_reason=body.note)
            await notify(session, claim, "CLAIM_REJECTED_BY_EMPLOYER", actor.correlation_id, reason=body.note)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.employer_attestation",
                    target_type="claim", target_id=claimId, detail=body.decision)
        view = await claim_view(session, claim)
    return envelope(view)


# ── bank switch before payment ──────────────────────────────────────────────────────────────────

async def verified_banks(session: AsyncSession, uan: str | None) -> list[dict[str, Any]]:
    rows = (await session.execute(select(member_bank_accounts).where(member_bank_accounts.c.uan == (uan or "-"))
                                  .order_by(member_bank_accounts.c.verified_at))).mappings().all()
    return [{"bank_ifsc": r["bank_ifsc"], "bank_account_last4": r["bank_account_last4"]} for r in rows]


async def _claim_uan(session: AsyncSession, claim: dict[str, Any]) -> str | None:
    return (await session.execute(select(accounts.c.uan).where(accounts.c.account_link_id == claim["account_link_id"]))).scalar_one_or_none()


@router.get("/api/v1/members/me/claims/{claimId}/bank-details")
async def bank_options(claimId: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    claim = await load_claim(session, claimId, member=actor.subject)
    banks = await verified_banks(session, await _claim_uan(session, claim))
    return envelope({"claim_id": claimId, "switchable": claim["state"] in BANK_SWITCHABLE and not claim["death_of_uan"],
                     "current_account_last4": claim["payee_account_last4"] or (banks[-1]["bank_account_last4"] if banks else None),
                     "verified_accounts": banks})


class BankSwitch(BaseModel):
    bank_ifsc: str = Field(pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    bank_account_last4: str = Field(pattern=r"^[0-9]{4}$")


@router.put("/api/v1/members/me/claims/{claimId}/bank-details")
async def switch_bank(claimId: str, body: BankSwitch, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await load_claim(session, claimId, member=actor.subject, lock=True)
        if claim["death_of_uan"]:
            raise Problem(409, "/problems/invalid-state", "Death claims are paid to each beneficiary's own account")
        if claim["state"] not in BANK_SWITCHABLE:
            raise Problem(409, "/problems/invalid-state", "The bank account can no longer be switched",
                          f"Current status: {claim['state']}. After a payment is returned, use the re-disbursement request.")
        banks = await verified_banks(session, await _claim_uan(session, claim))
        if {"bank_ifsc": body.bank_ifsc, "bank_account_last4": body.bank_account_last4} not in banks:
            raise Problem(422, "/problems/bank-not-verified", "This is not one of your KYC-verified bank accounts",
                          "Add the account under KYC first; your employer approves it.",
                          verified_accounts=banks)
        require_step_up(actor, "switch-claim-bank", claimId, claim["version"])
        result = await session.execute(update(claims).where(claims.c.claim_id == claimId, claims.c.version == claim["version"]).values(
            payee_ifsc=body.bank_ifsc, payee_account_last4=body.bank_account_last4, version=claim["version"] + 1,
            updated_at=datetime.now(UTC)))
        if result.rowcount != 1:
            raise Problem(409, "/problems/version-conflict", "This claim changed meanwhile", "Reload the claim and try again.")
        await session.execute(insert(claim_timeline).values(claim_id=claimId, state=claim["state"], actor_role="member",
                                                            note=f"Payment account switched to the account ending {body.bank_account_last4}."))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.bank_switch",
                    target_type="claim", target_id=claimId, detail=f"****{body.bank_account_last4}")
        claim = await load_claim(session, claimId)
        view = {**await claim_view(session, claim), "payee_account_last4": body.bank_account_last4}
    return envelope(view)


# ── auto-transfer on a change of job ────────────────────────────────────────────────────────────

async def auto_candidates(session: AsyncSession, subject: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """The primary member ID and the member IDs that can be auto-transferred into it, or why none can."""
    mine = [dict(r) for r in (await session.execute(select(accounts).where(accounts.c.member_subject == subject))).mappings().all()]
    primary = next((a for a in mine if a["is_primary"]), None)
    if not primary:
        return None, [], ["No primary member ID is recorded for you yet."]
    if not primary["aadhaar_verified"]:
        return primary, [], ["Auto-transfer needs a verified Aadhaar on your UAN."]
    same_set = accounts.c.set_key == primary["set_key"] if primary["set_key"] else accounts.c.uan == primary["uan"]
    rows = [dict(r) for r in (await session.execute(select(accounts).where(
        or_(same_set, accounts.c.member_subject == subject)))).mappings().all()]
    pending = set((await session.execute(select(auto_transfers.c.from_account_link_id).where(
        auto_transfers.c.state == "CONFIRMED"))).scalars())
    busy = set((await session.execute(select(claims.c.account_link_id).where(claims.c.state.in_(OPEN_STATES)))).scalars())
    out = [a for a in rows if a["account_link_id"] != primary["account_link_id"] and a["date_of_exit"]
           and a["employee_paise"] + a["employer_paise"] > 0 and a["account_link_id"] not in pending | busy
           and not a["deceased_on"]]
    return primary, out, []


def _transfer_id(frm: str, to: str) -> str:
    return f"AUTO-{frm}-{to}"


async def start_auto_transfer(session: AsyncSession, subject: str, primary: dict[str, Any], a: dict[str, Any],
                              correlation_id: str | None, by_system: bool = False) -> str:
    """Record the transfer of an exited member ID's balance into the primary one and ask the ledger to post it."""
    transfer_id = _transfer_id(a["account_link_id"], primary["account_link_id"])
    amount = a["employee_paise"] + a["employer_paise"]
    await session.execute(insert(auto_transfers).values(transfer_id=transfer_id, member_subject=subject, uan=a["uan"],
                                                        from_account_link_id=a["account_link_id"],
                                                        to_account_link_id=primary["account_link_id"], amount_paise=amount,
                                                        state="CONFIRMED"))
    await add_event(session, producer=PRODUCER, event_type="AutoTransferConfirmed.v1", aggregate_type="auto_transfer",
                    aggregate_id=transfer_id, correlation_id=correlation_id, payload={
                        "transfer_id": transfer_id, "uan": a["uan"], "from_account_link_id": a["account_link_id"],
                        "to_account_link_id": primary["account_link_id"]})
    if by_system:
        await audit(session, actor_subject="system", actor_stakeholder="system", action="transfer.auto_started",
                    target_type="auto_transfer", target_id=transfer_id, detail=rupees(amount))
    return transfer_id


async def auto_transfer_on_contribution(session: AsyncSession, account_link_ids: set[str], correlation_id: str | None) -> list[str]:
    """P2.21: the first contribution on a primary member ID moves the member's exited member IDs into it — no request. The
    member is told (CLAIM-style notification); anything that blocks it (no verified Aadhaar, a claim running) leaves it
    for the member to see and confirm later as before."""
    started = []
    for link in account_link_ids:
        acct = (await session.execute(select(accounts).where(accounts.c.account_link_id == link))).mappings().first()
        if not acct or not acct["is_primary"] or not acct["member_subject"]:
            continue
        primary, candidates, _ = await auto_candidates(session, acct["member_subject"])
        for a in candidates:
            started.append(await start_auto_transfer(session, acct["member_subject"], primary, a, correlation_id, by_system=True))
            await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                            aggregate_id=a["account_link_id"], correlation_id=correlation_id, payload={
                                "recipient_subject": acct["member_subject"], "template": "AUTO_TRANSFER_STARTED",
                                "reference_id": _transfer_id(a["account_link_id"], primary["account_link_id"]),
                                "params": {"amount_paise": a["employee_paise"] + a["employer_paise"]}})
    return started


@router.get("/api/v1/members/me/transfers/auto")
async def auto_status(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    primary, candidates, reasons = await auto_candidates(session, actor.subject)
    history = (await session.execute(select(auto_transfers).where(auto_transfers.c.member_subject == actor.subject)
                                     .order_by(auto_transfers.c.confirmed_at.desc()))).mappings().all()
    return envelope({
        "primary_account_link_id": primary["account_link_id"] if primary else None, "reasons": reasons,
        "eligible": [{"transfer_id": _transfer_id(a["account_link_id"], primary["account_link_id"]), "state": "AWAITING_CONFIRMATION",
                      "uan": a["uan"], "from_account_link_id": a["account_link_id"], "to_account_link_id": primary["account_link_id"],
                      "date_of_exit": a["date_of_exit"].isoformat(), "amount_paise": a["employee_paise"] + a["employer_paise"]}
                     for a in candidates],
        "history": [{"transfer_id": h["transfer_id"], "state": h["state"], "from_account_link_id": h["from_account_link_id"],
                     "to_account_link_id": h["to_account_link_id"], "amount_paise": h["amount_paise"],
                     "confirmed_at": h["confirmed_at"].isoformat() if h["confirmed_at"] else None,
                     "posted_at": h["posted_at"].isoformat() if h["posted_at"] else None} for h in history],
        "note": "Illustrative: when you join a new employer, the balance of your previous (exited) member IDs moves to "
                "your primary member ID once you confirm; no Form 13 or employer attestation is needed."})


@router.post("/api/v1/members/me/transfers/auto/{transferId}/confirmations", status_code=201)
async def confirm_auto(transferId: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        primary, candidates, reasons = await auto_candidates(session, actor.subject)
        a = next((c for c in candidates if primary and _transfer_id(c["account_link_id"], primary["account_link_id"]) == transferId), None)
        if not a:
            raise Problem(409, "/problems/not-eligible", "This auto-transfer is not available",
                          " ".join(reasons) or "The member ID is already transferred, has a claim in progress, or has no balance.")
        amount = a["employee_paise"] + a["employer_paise"]
        require_step_up(actor, "confirm-auto-transfer", transferId, None, amount)
        await start_auto_transfer(session, actor.subject, primary, a, actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="transfer.auto_confirm",
                    target_type="auto_transfer", target_id=transferId, detail=rupees(amount))
    return envelope({"transfer_id": transferId, "state": "CONFIRMED", "from_account_link_id": a["account_link_id"],
                     "to_account_link_id": primary["account_link_id"], "amount_paise": amount,
                     "next_step": "The ledger moves the balance in a few seconds; you will be notified."})
