"""Illustrative P2.24 review periods, not a statutory EPFO appeal process."""
from datetime import UTC, datetime, timedelta

from epfo_observability import Problem

REQUEST_DAYS = 30
DECISION_DAYS = 30


def deadline(closed_at: datetime) -> datetime:
    return (closed_at if closed_at.tzinfo else closed_at.replace(tzinfo=UTC)) + timedelta(days=REQUEST_DAYS)


def check_request_window(closed_at: datetime, now: datetime) -> datetime:
    # P2.24 illustrative rule: one request within 30 days of closure.
    due = deadline(closed_at)
    if now > due:
        raise Problem(409, "/problems/review-window-closed", "The review request period has passed",
                      "A review must be requested within 30 days of closure.")
    return due
