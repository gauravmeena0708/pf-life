"""Events employer-service consumes: the establishment freeze run by the process engine (workflow-service)."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import establishments
from epfo_persistence import audit

BINDINGS = ["workflow-service.ProcessTransitioned.v1"]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if event["event_type"] != "ProcessTransitioned.v1" or p["process"] != "establishment_freeze":
        return
    data = p.get("data") or {}
    if p["to_state"] == "FROZEN":
        values = {"frozen_at": datetime.now(UTC), "freeze": {"case_id": p["instance_id"], "category": data.get("category"),
                                                             "order_ref": data.get("order_ref"), "reason": data.get("reason"),
                                                             "ordered_by_role": p["actor_role"]}}
    elif p["to_state"] == "ACTIVE":
        values = {"frozen_at": None, "freeze": None}
    else:
        return
    await session.execute(update(establishments).where(establishments.c.establishment_id == p["subject_ref"]).values(**values))
    await audit(session, actor_subject=p["actor_subject"], actor_stakeholder=p["actor_role"],
                action=f"establishment.{'frozen' if p['to_state'] == 'FROZEN' else 'defrozen'}",
                target_type="establishment", target_id=p["subject_ref"], detail=data.get("order_ref") or data.get("reason"))
