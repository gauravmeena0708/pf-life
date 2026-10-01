"""Event consumers: a published rule set is stored, then pensions in payment are recomputed under it; a pension
updation inwarded on paper at the PRO counter becomes a NEW activity on the pension office's tracker."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import propose_revisions
from app.infra.tables import higher_pension_options, pensioners, updation_activities
from epfo_persistence import add_event
from epfo_persistence.policy import on_policy_published

BINDINGS = ["platform-service.PolicyPublished.v1", "claim-service.PhysicalClaimInwarded.v1", "workflow-service.StaffPostingChanged.v1",
            "contribution-service.HigherPensionTransferPosted.v1"]
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


async def on_higher_pension_transfer(session: AsyncSession, event: dict[str, Any]) -> None:
    payload = event["payload"]
    row = (await session.execute(select(higher_pension_options).where(
        higher_pension_options.c.option_id == payload["option_id"]).with_for_update())).mappings().first()
    if not row or row["state"] != "TRANSFER_REQUESTED" or payload.get("status") not in ("POSTED", "INSUFFICIENT_BALANCE"):
        return
    state = "DUES_TRANSFERRED" if payload["status"] == "POSTED" else "TRANSFER_FAILED"
    await session.execute(update(higher_pension_options).where(higher_pension_options.c.option_id == row["option_id"]).values(state=state))
    await add_event(session, producer="pension-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=row["option_id"], correlation_id=event["correlation_id"], payload={
                        "recipient_subject": row["subject"], "template": "HIGHER_PENSION_" + state,
                        "reference_id": row["option_id"], "params": {"amount_paise": row["dues_paise"],
                        "reason": "The member deposits the difference through the office (VDR)." if state == "TRANSFER_FAILED" else ""}})


HANDLERS = {"HigherPensionTransferPosted.v1": on_higher_pension_transfer}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if handler := HANDLERS.get(event["event_type"]):
        await handler(session, event)
        return
    if event["event_type"] == "StaffPostingChanged.v1":           # HR re-posted an officer (P2.8e)
        from app.infra.tables import office_staff
        from epfo_persistence.postings import apply_posting
        await apply_posting(session, event, office_staff)
        return
    if event["event_type"] == "PhysicalClaimInwarded.v1":
        await on_physical_intake(session, event)
    if event["event_type"] == "PolicyPublished.v1":
        await on_policy_published(session, event)
        p = event["payload"]
        await propose_revisions(session, p["document"], date.fromisoformat(p["effective_from"]))
