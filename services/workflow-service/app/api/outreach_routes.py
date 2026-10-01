"""Nidhi Aapke Nikat camp assistance recorded by the camp officer (P2.12f)."""
from datetime import date
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, posting
from app.infra.tables import camp_requests, outreach_camps
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "workflow-service"

NEXT_STEPS = {
    "GRIEVANCE": "Registered for the PRO to enter in the grievance system.",
    "CLAIM_HELP": "Helped to file online; the member tracks it in My claims.",
    "KYC_UPDATE": "The member submits the KYC update online for employer approval.",
    "INOPERATIVE_ACCOUNT": "Verification through co-workers by the DA (Accounts); then reactivation by the AO.",
    "PENSION": "The pension section will guide the member on the applicable pension process.",
    "UAN_HELP": "The member will be guided through UAN activation or account access.",
}


class AssistedRequest(BaseModel):
    kind: Literal["GRIEVANCE", "CLAIM_HELP", "KYC_UPDATE", "INOPERATIVE_ACCOUNT", "PENSION", "UAN_HELP"]
    name: str = Field(min_length=1, max_length=200)
    mobile: str = Field(pattern=r"^[0-9]{10}$")
    uan: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    details: str = Field(min_length=10, max_length=4000)


@router.post("/api/v1/office/outreach-camps/{campId}/assisted-requests")
async def take_assisted_request(campId: str, body: AssistedRequest,
                                actor: Actor = Depends(require_stakeholder("fo.nan")),
                                session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        mine = await posting(session, actor)
        if mine["stakeholder"] != "fo.nan":
            raise Problem(403, "/problems/wrong-posting", "You are not posted as a NAN officer")
        camp_query = select(outreach_camps).where(outreach_camps.c.camp_id == campId)
        if session.bind.dialect.name == "postgresql":
            camp_query = camp_query.with_for_update()  # serialize reference allocation within this camp
        camp = (await session.execute(camp_query)).mappings().first()
        if not camp or camp["office_id"] != mine["office_id"]:
            raise Problem(404, "/problems/not-found", "Camp not found")

        last_number = (await session.execute(select(func.max(camp_requests.c.request_number)).where(
            camp_requests.c.camp_id == campId))).scalar_one()
        number = int(last_number or 0) + 1
        request_id = str(uuid4())
        reference = f"NAN/{campId}/{number}"
        next_step = NEXT_STEPS[body.kind]
        await session.execute(insert(camp_requests).values(
            request_id=request_id, camp_id=campId, office_id=camp["office_id"],
            request_number=number, reference=reference, kind=body.kind,
            name=body.name, mobile=body.mobile, uan=body.uan, details=body.details,
            next_step=next_step, taken_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="CampRequestTaken.v1", aggregate_type="camp_request",
                        aggregate_id=request_id, correlation_id=actor.correlation_id, payload={
                            "request_id": request_id, "camp_id": campId, "office_id": camp["office_id"], "kind": body.kind})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="outreach.assisted_request", target_type="camp_request", target_id=request_id,
                    detail=f"{reference}: {body.kind}")
        counts = {kind: 0 for kind in NEXT_STEPS}
        rows = (await session.execute(select(camp_requests.c.kind, func.count().label("count"))
                                      .where(camp_requests.c.camp_id == campId)
                                      .group_by(camp_requests.c.kind))).all()
        counts.update({kind: int(count) for kind, count in rows})
    held_on = camp["held_on"]
    return envelope({"request_id": request_id, "reference": reference, "kind": body.kind,
                     "next_step": next_step, "camp": {"camp_id": campId, "office_id": camp["office_id"],
                     "held_on": held_on.isoformat() if isinstance(held_on, date) else held_on,
                     "venue": camp["venue"], "request_counts": counts}})
