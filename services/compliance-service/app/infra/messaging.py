"""Events compliance-service consumes: the demands contribution-service raises and changes."""
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import demands, establishments

BINDINGS = ["contribution-service.DemandStateChanged.v1", "workflow-service.StaffPostingChanged.v1",
            "employer-service.EstablishmentOfficeTransferred.v1", "platform-service.PolicyPublished.v1"]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] == "PolicyPublished.v1":              # the rule set in force for inquiries' time limits (P2.11a)
        from epfo_persistence.policy import on_policy_published
        await on_policy_published(session, event)
        return
    if event["event_type"] == "EstablishmentOfficeTransferred.v1":
        p = event["payload"]
        await session.execute(update(establishments).where(establishments.c.establishment_id == p["establishment_id"],
                                                           establishments.c.office_id == p["from_office_id"])
                              .values(office_id=p["to_office_id"]))
        return
    if event["event_type"] == "StaffPostingChanged.v1":           # HR re-posted an officer (P2.8e)
        from app.infra.tables import office_staff
        from epfo_persistence.postings import apply_posting
        await apply_posting(session, event, office_staff)
        return
    if event["event_type"] != "DemandStateChanged.v1":
        return
    p = event["payload"]
    values = {k: p[k] for k in ("establishment_id", "kind", "trrn", "wage_month", "amount_paise", "days_late", "state", "working")}
    if (await session.execute(select(demands.c.demand_id).where(demands.c.demand_id == p["demand_id"]))).first():
        await session.execute(update(demands).where(demands.c.demand_id == p["demand_id"]).values(**values))
    else:
        from sqlalchemy import insert
        await session.execute(insert(demands).values(demand_id=p["demand_id"], **values))
