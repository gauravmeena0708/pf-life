"""Which member ID of a member is primary (Phase 2, slice 7d).

A member has one UAN, sometimes more than one when an older UAN is linked by the same verified Aadhaar (an
"Aadhaar-verified set"), and a member ID for every job. The primary member ID is the latest-joined member ID that
has received at least one contribution; if none has, the latest-joined. A member ID transferred out (Form 13) is
never primary. Claims are filed, and transfers made, against the primary member ID; the others are secondary.
"""
from datetime import date
from typing import Any


def _joined(x: dict[str, Any]) -> date:
    d = x["date_of_joining"]
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def primary_member_id(member_ids: list[dict[str, Any]]) -> str | None:
    """`member_ids`: dicts with account_link_id, date_of_joining, last_contribution_month (or None) and
    transferred_to (or None). Returns the primary member ID, or None when there is none."""
    candidates = [x for x in member_ids if not x.get("transferred_to")]
    contributed = [x for x in candidates if x.get("last_contribution_month")]
    pool = contributed or candidates
    if not pool:
        return None
    return max(pool, key=lambda x: (_joined(x), x["account_link_id"]))["account_link_id"]
