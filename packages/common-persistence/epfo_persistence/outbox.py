"""Write events to the outbox in the caller's transaction (never publish directly from a handler)."""
from typing import Any

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, insert
from sqlalchemy.ext.asyncio import AsyncSession

from epfo_observability import correlation_id as current_correlation_id

from .events import envelope

metadata = MetaData()
outbox_table = Table(
    "outbox", metadata,
    Column("id", Integer, primary_key=True),
    Column("event_id", String(36)), Column("event_type", String(120)),
    Column("aggregate_type", String(60)), Column("aggregate_id", String(80)),
    Column("payload", JSON), Column("correlation_id", String(36)),
    Column("published_at"), Column("attempts", Integer),
)


async def add_event(session: AsyncSession, *, producer: str, event_type: str, aggregate_type: str, aggregate_id: str,
                    payload: dict[str, Any], correlation_id: str | None = None, causation_id: str | None = None) -> dict:
    """Insert one event into the outbox. Commits with the caller's transaction; the relay publishes it later.

    The stored payload is the full envelope, so the relay publishes exactly what was committed."""
    body = envelope(producer=producer, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
                    payload=payload, correlation_id=correlation_id or current_correlation_id(), causation_id=causation_id)
    await session.execute(insert(outbox_table).values(
        event_id=body["event_id"], event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        payload={"producer": producer, "envelope": body}, correlation_id=body["correlation_id"], attempts=0))
    return body
