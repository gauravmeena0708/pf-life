"""Event consumers: a published rule set is stored, then pensions in payment are recomputed under it; a pension
updation inwarded on paper at the PRO counter becomes a NEW activity on the pension office's tracker."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import propose_revisions
from app.infra.tables import pensioners, updation_activities
from epfo_persistence.policy import on_policy_published

BINDINGS = ["platform-service.PolicyPublished.v1", "claim-service.PhysicalClaimInwarded.v1"]
# PRO counter request → updation activity. PPO amendments are basic-details updations the DA (Pension) takes up.
INTAKE_ACTIVITIES = {"PHYSICAL_LC_UPDATION": "PHYSICAL_LC", "DEATH_UPDATION": "DEATH", "SPOUSE_REMARRIAGE_UPDATION": "SPOUSE_REMARRIAGE",
                     "PPO_AMENDMENT_BENEFICIARY": "BASIC_DETAILS", "PPO_AMENDMENT_SERVICE": "BASIC_DETAILS", "PPO_AMENDMENT_POHW": "BASIC_DETAILS"}


async def on_physical_intake(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    activity = INTAKE_ACTIVITIES.get(p["form_type"])
    if not activity or not (await session.execute(select(pensioners.c.ppo_id).where(pensioners.c.ppo_id == p["ppo_id"]))).first():
        return                                            # not a pension updation, or an unknown PPO: nothing to track
    activity_id = f"UPD-{p['intake_id']}"
    if (await session.execute(select(updation_activities.c.activity_id).where(updation_activities.c.activity_id == activity_id))).first():
        return                                            # redelivered
    now = datetime.now(UTC)
    await session.execute(insert(updation_activities).values(
        activity_id=activity_id, ppo_id=p["ppo_id"], activity=activity, mode="PHYSICAL", status="NEW",
        details={**p["details"], "intake_id": p["intake_id"], "form_type": p["form_type"], "filed_by": p["filed_by"]},
        initiated_by="pro-counter", initiated_role="fo.pro_intake", created_at=now, updated_at=now))


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] == "PhysicalClaimInwarded.v1":
        await on_physical_intake(session, event)
    if event["event_type"] == "PolicyPublished.v1":
        await on_policy_published(session, event)
        p = event["payload"]
        await propose_revisions(session, p["document"], date.fromisoformat(p["effective_from"]))
