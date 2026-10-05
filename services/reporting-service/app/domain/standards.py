"""Published service standards and aggregate performance calculations."""
from datetime import UTC, datetime, timedelta
from math import ceil
from statistics import median
from typing import Any, Mapping

# EPF Scheme 1952 para 72(7); other durations are EPFO service targets.
CHARTER_STANDARDS = (
    {"code": "CLAIM_SETTLEMENT", "name": "Claim settlement", "days": 20,
     "basis": "STATUTORY", "source": "EPF Scheme 1952 para 72(7)"},
    {"code": "AUTO_CLAIM", "name": "Auto-settled claim", "days": 3,
     "basis": "TARGET", "source": "EPFO auto-settlement service target"},
    {"code": "GRIEVANCE", "name": "Grievance resolution", "days": 30,
     "basis": "TARGET", "source": "EPFO Citizen's Charter"},
    {"code": "TRANSFER", "name": "PF transfer", "days": 20,
     "basis": "TARGET", "source": "EPFO Citizen's Charter"},
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def performance(rows: list[Mapping[str, Any]], *, start_field: str, end_field: str,
                days: int, as_of: datetime, period_days: int) -> dict[str, Any] | None:
    """A completion cohort, with currently overdue open cases from the same period."""
    cutoff = as_of - timedelta(days=period_days)
    completed = [row for row in rows if row[start_field] is not None and row[end_field] is not None
                 and cutoff <= _utc(row[end_field]) <= as_of
                 and _utc(row[start_field]) <= _utc(row[end_field])]
    # Suppress the whole cell, including open counts, to prevent subtraction attacks.
    if len(completed) < 10:
        return None
    elapsed = sorted((_utc(row[end_field]) - _utc(row[start_field])).total_seconds() / 86400
                     for row in completed)
    overdue = sum(row[start_field] is not None and row[end_field] is None
                  and cutoff <= _utc(row[start_field]) <= as_of
                  and as_of - _utc(row[start_field]) > timedelta(days=days) for row in rows)
    return {"completed": len(completed), "within_pct": round(100 * sum(value <= days for value in elapsed) / len(elapsed)),
            "median_days": round(median(elapsed), 2),
            "p90_days": round(elapsed[ceil(.9 * len(elapsed)) - 1], 2),
            "open_past_standard": None if 0 < overdue < 10 else overdue,
            "met": all(value <= days for value in elapsed)}
