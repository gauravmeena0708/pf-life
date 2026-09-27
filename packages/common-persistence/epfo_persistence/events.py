"""Event envelope matching contracts/events/*.schema.json."""
import uuid
from datetime import UTC, datetime
from typing import Any

EXCHANGE = "epfo.events"
DLX = "epfo.events.dlx"


def routing_key(producer: str, event_type: str) -> str:
    """e.g. ('payment-simulator', 'PaymentConfirmed.v1') -> 'payment-simulator.PaymentConfirmed.v1'."""
    return f"{producer}.{event_type}"


def envelope(*, producer: str, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict[str, Any],
             correlation_id: str, causation_id: str | None = None, event_id: str | None = None,
             occurred_at: datetime | None = None) -> dict[str, Any]:
    if not event_type.endswith(".v1"):
        raise ValueError("event_type must carry its version, e.g. 'ContributionPosted.v1'")
    body: dict[str, Any] = {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "producer": producer,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "payload": payload,
    }
    if causation_id:
        body["causation_id"] = causation_id
    return body
