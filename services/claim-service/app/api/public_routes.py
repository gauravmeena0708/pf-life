"""Phase 2, slice 8d: claim status without a login. The claim number and the member's UAN (or, for a death claim,
the late member's UAN), with a one-time code to the registered mobile (MOCK: any six digits except 000000); the
gateway asks for its public challenge and limits the rate. The answer is the progress only: no amounts, names or
bank details."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.domain.claims import NEXT_STEP
from app.infra.tables import accounts, claim_timeline, claims
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope

router = APIRouter()


class ClaimStatusLookup(BaseModel):
    challenge_id: str                                      # checked by the gateway
    answer: int
    claim_id: str = Field(pattern=r"^CLM-[0-9A-F]{8}$")
    uan: str = Field(pattern=r"^[0-9]{12}$")
    otp: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/api/v1/public/claims/status-lookups")
async def claim_status(body: ClaimStatusLookup, actor: Actor = Depends(require_stakeholder("public")),
                       session: AsyncSession = Depends(db)) -> dict:
    if body.otp == "000000":
        raise Problem(422, "/problems/otp-invalid", "The one-time code is not correct",
                      "Enter the code sent to the registered mobile (mock: any six digits except 000000).")
    row = (await session.execute(select(claims, accounts.c.uan).join(accounts, accounts.c.account_link_id == claims.c.account_link_id)
                                 .where(claims.c.claim_id == body.claim_id))).mappings().first()
    if not row or body.uan not in (row["uan"], row["death_of_uan"]) or row["state"] == "AWAITING_CONFIRMATION":
        raise Problem(404, "/problems/not-found", "No claim matches this number and UAN")
    steps = (await session.execute(select(claim_timeline.c.at, claim_timeline.c.state).where(claim_timeline.c.claim_id == body.claim_id)
                                   .order_by(claim_timeline.c.id))).mappings().all()
    return envelope({"claim_id": row["claim_id"], "form_type": row["form_type"], "state": row["state"],
                     "next_step": NEXT_STEP.get(row["state"], ""),
                     "filed_on": row["created_at"].date().isoformat() if row["created_at"] else None,
                     "steps": [{"at": s["at"].isoformat() if s["at"] else None, "state": s["state"]} for s in steps]})
