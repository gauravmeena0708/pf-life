"""Advisory risk rules (Journey D). Deterministic, versioned and explainable; they never block, accuse or
punish. A signal only asks a human reviewer (ho.caiu) to look, and makes a claim take the officer route.

Deliberately NOT a signal: a device shared by several members. Common Service Centres and family
phones are normal, so sharing is recorded as context for the reviewer, never as evidence."""
from datetime import datetime, timedelta
from typing import Any

RULE_VERSION = "risk-rules-2026.1 (illustrative)"
TAKEOVER_WINDOW = timedelta(hours=24)
SHARED_DEVICE_MIN_SUBJECTS = 3

TAKEOVER = "NEW_DEVICE_CONTACT_CHANGE_CLAIM"
MEMBER_REPORT = "MEMBER_REPORTED_NOT_ME"

EXPLANATIONS = {
    TAKEOVER: ("A sign-in from a device not seen before for this account was followed, within 24 hours, by a "
               "change of contact details and a new claim. This pattern can mean someone else is using the "
               "account; it also happens when a member gets a new phone. Please review; take no action on this alone."),
    MEMBER_REPORT: "The member reported activity they do not recognise. Please review with the member.",
}


def takeover_evidence(events: list[dict[str, Any]], now: datetime, already_cited: set[str] = frozenset()) -> list[str] | None:
    """Event IDs for new-device login → contact change → claim, in that order within the window, or None.
    Events already cited by an earlier signal are not reused: a pattern a reviewer has judged once must not
    raise a fresh signal just because a later, unrelated claim arrives inside the same 24 hours."""
    recent = sorted((e for e in events if now - e["at"] <= TAKEOVER_WINDOW and e["event_id"] not in already_cited),
                    key=lambda e: e["at"])
    login = next((e for e in recent if e["event_type"] == "LOGIN_NEW_DEVICE"), None)
    if not login:
        return None
    change = next((e for e in recent if e["event_type"] == "CONTACT_DETAILS_CHANGED" and e["at"] >= login["at"]), None)
    if not change:
        return None
    claim = next((e for e in recent if e["event_type"] == "CLAIM_CREATED" and e["at"] >= change["at"]), None)
    return [login["event_id"], change["event_id"], claim["event_id"]] if claim else None


def shared_device_context(subjects_on_device: int) -> dict[str, Any] | None:
    if subjects_on_device < SHARED_DEVICE_MIN_SUBJECTS:
        return None
    return {"shared_device": True, "subjects_on_device": subjects_on_device,
            "note": "This device is used by several members (for example a Common Service Centre). "
                    "Sharing a device is normal and is not evidence of fraud."}
