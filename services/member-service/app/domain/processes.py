"""member-service owns the freeze contract; the engine in workflow-service runs the process (ADR-0005).
On each ProcessTransitioned.v1 of `member_freeze` this service records the account state and publishes
the domain event other services react to."""
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import members
from epfo_persistence import add_event


async def on_process_transitioned(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["process"] != "member_freeze" or p["to_state"] not in ("FROZEN", "ACTIVE"):
        return
    uan, data = p["subject_ref"], p.get("data") or {}
    await session.execute(update(members).where(members.c.uan == uan).values(account_state=p["to_state"]))
    if p["to_state"] == "FROZEN":
        await add_event(session, producer="member-service", event_type="AccountFrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "category": data.get("category", ""),
                            "order_ref": data.get("order_ref", "")})
    else:
        await add_event(session, producer="member-service", event_type="AccountDefrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "order_ref": p["instance_id"]})
