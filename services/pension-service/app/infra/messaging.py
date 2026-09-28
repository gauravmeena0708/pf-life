"""Event consumers: a published rule set is stored, then pensions in payment are recomputed under it."""
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import propose_revisions
from epfo_persistence.policy import on_policy_published

BINDINGS = ["platform-service.PolicyPublished.v1"]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] == "PolicyPublished.v1":
        await on_policy_published(session, event)
        p = event["payload"]
        await propose_revisions(session, p["document"], date.fromisoformat(p["effective_from"]))
