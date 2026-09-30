"""Events compliance-service consumes: the demands contribution-service raises and changes."""
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import demands

BINDINGS = ["contribution-service.DemandStateChanged.v1"]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] != "DemandStateChanged.v1":
        return
    p = event["payload"]
    values = {k: p[k] for k in ("establishment_id", "kind", "trrn", "wage_month", "amount_paise", "days_late", "state", "working")}
    if (await session.execute(select(demands.c.demand_id).where(demands.c.demand_id == p["demand_id"]))).first():
        await session.execute(update(demands).where(demands.c.demand_id == p["demand_id"]).values(**values))
    else:
        from sqlalchemy import insert
        await session.execute(insert(demands).values(demand_id=p["demand_id"], **values))
