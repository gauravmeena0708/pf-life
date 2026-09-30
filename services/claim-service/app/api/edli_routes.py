"""Phase 2, slice 8c: the EDLI section's decision on an assurance-benefit claim (Form 5IF). The officer chain admits
the claim (the death, the nominees); the EDLI section then verifies the member's average monthly wages (the
employer's certificate on Form 5IF) and decides. The benefit is worked out again from the rules the claim was filed
under, with the verified wages; the confirmation is bound to that amount. Illustrative."""
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import claim_view, db, load_claim, notify, record_decision, staff_office, transition
from app.domain.claims import rupees
from app.infra.tables import claims
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import edli_benefit, rules_by_version

router = APIRouter()
EDLI = require_stakeholder("fo.edli")


async def _pending(session: AsyncSession, claim_id: str, office: str) -> dict[str, Any]:
    claim = await load_claim(session, claim_id, office=office, lock=True)
    if claim["claim_type"] != "DEATH_EDLI":
        raise Problem(404, "/problems/not-found", "Not an EDLI claim")
    if claim["state"] != "PENDING_EDLI_DECISION":
        raise Problem(409, "/problems/invalid-state", "This claim is not waiting for the EDLI section", f"Current status: {claim['state']}.")
    return claim


async def benefit(session: AsyncSession, claim: dict[str, Any], average_wages_paise: int) -> dict[str, Any]:
    e = claim["evaluation"] or {}
    rules = await rules_by_version(session, claim["rule_version"])
    return edli_benefit(average_wages_paise, int(e.get("balance_paise", 0)), int(e.get("service_months", 0)), rules)


@router.get("/api/v1/office/edli-claims")
async def queue(actor: Actor = Depends(EDLI), session: AsyncSession = Depends(db)) -> dict:
    office = await staff_office(session, actor)
    rows = (await session.execute(select(claims).where(claims.c.office_id == office, claims.c.claim_type == "DEATH_EDLI",
                                                       claims.c.state == "PENDING_EDLI_DECISION").order_by(claims.c.created_at))).mappings().all()
    return envelope([{"claim_id": r["claim_id"], "death_of_uan": r["death_of_uan"], "amount_paise": r["amount_paise"],
                      "version": r["version"], "summary": r["summary"], "working": (r["evaluation"] or {}).get("working"),
                      "service_months": (r["evaluation"] or {}).get("service_months")} for r in rows])


class Wages(BaseModel):
    average_monthly_wages_paise: int = Field(gt=0, le=10**9)


@router.post("/api/v1/office/edli-claims/{claimId}/benefit-previews")
async def preview(claimId: str, body: Wages, actor: Actor = Depends(EDLI), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await _pending(session, claimId, await staff_office(session, actor))
        b = await benefit(session, claim, body.average_monthly_wages_paise)
    return envelope({"claim_id": claimId, "amount_paise": b["amount_paise"], "working": b["working"],
                     "filed_amount_paise": claim["amount_paise"], "version": claim["version"]})


class EdliDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    average_monthly_wages_paise: int | None = Field(default=None, gt=0, le=10**9)
    reason: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/office/edli-claims/{claimId}/decisions")
async def decide(claimId: str, body: EdliDecision, actor: Actor = Depends(EDLI), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await _pending(session, claimId, await staff_office(session, actor))
        if body.decision == "APPROVE":
            if not body.average_monthly_wages_paise:
                raise Problem(422, "/problems/validation", "Give the verified average monthly wages")
            b = await benefit(session, claim, body.average_monthly_wages_paise)
            require_step_up(actor, "decide-edli", claimId, claim["version"], b["amount_paise"])
            claim = await transition(session, claim, "APPROVED", "fo.edli",
                                     f"EDLI benefit sanctioned: {rupees(b['amount_paise'])} — {b['working']} (verified wages). {body.reason}",
                                     decision_reason=body.reason, amount_paise=b["amount_paise"],
                                     evaluation={**(claim["evaluation"] or {}), "verified_average_wages_paise": body.average_monthly_wages_paise,
                                                 "working": b["working"]})
            await record_decision(session, claim, "APPROVED", "EDLI_SANCTIONED", actor.correlation_id)
            await notify(session, claim, "CLAIM_APPROVED", actor.correlation_id)
        else:
            require_step_up(actor, "decide-edli", claimId, claim["version"])
            claim = await transition(session, claim, "REJECTED_WITH_REASON", "fo.edli", f"Rejected by the EDLI section: {body.reason}",
                                     decision_reason=body.reason)
            await record_decision(session, claim, "REJECTED", "EDLI_REJECTED", actor.correlation_id)
            await notify(session, claim, "CLAIM_REJECTED", actor.correlation_id, reason=body.reason)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.edli_decision",
                    target_type="claim", target_id=claimId, detail=body.decision)
        view = await claim_view(session, claim)
    return envelope(view)
