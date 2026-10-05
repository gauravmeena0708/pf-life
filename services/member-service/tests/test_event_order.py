"""Event ordering and concurrency tests for member-service (docs/event-copies.md).

Lead 3: members table (account_state)
Producers:
- workflow-service (ProcessTransitioned.v1 for process == "member_freeze")
- platform-service (IssueTrackerExecuted.v1 for administrative actions FREEZE_MEMBER and DEFREEZE_MEMBER)

Failure scenario from docs/event-copies.md:
An urgent administrative defreeze order executed by the IS Division via
platform-service.IssueTrackerExecuted.v1 unfreezes an account (account_state = 'ACTIVE').
Meanwhile, a delayed or retried message from an earlier workflow freeze case
(workflow-service.ProcessTransitioned.v1) reaches member-service and overwrites
account_state = 'FROZEN', silently undoing the official administrative order.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import uuid
from typing import Any

from sqlalchemy import select

import app.infra.db as db
from app.infra.tables import members
from app.main import _route
from epfo_persistence.consumer import apply_once
from tests.test_member_api import SEED, api, token  # noqa: F401 (fixtures)
from tests.test_member_processes import outbox

UAN = "100000000002"
MEMBER_B = SEED["keycloak_subjects"]["member-b"]


def deliver(event_type: str, payload: dict[str, Any], *, occurred_at: datetime | str,
            producer: str, aggregate_type: str, aggregate_id: str, correlation_id: str = "c") -> bool:
    if isinstance(occurred_at, datetime):
        occurred_at_str = occurred_at.isoformat().replace("+00:00", "Z")
    else:
        occurred_at_str = str(occurred_at)
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "producer": producer,
        "occurred_at": occurred_at_str,
        "correlation_id": correlation_id,
        "payload": payload,
    }
    return asyncio.run(apply_once(db.sessions(), event, _route))


def workflow_freeze_event(uan: str = UAN, to_state: str = "FROZEN", instance_id: str = "CASE-FREEZE-1",
                          category: str = "AUDIT", order_ref: str = "RO/ORDER/01") -> dict[str, Any]:
    return {
        "process": "member_freeze",
        "instance_id": instance_id,
        "subject_ref": uan,
        "from_state": "ACTIVE" if to_state == "FROZEN" else "FROZEN",
        "to_state": to_state,
        "operation": "freeze" if to_state == "FROZEN" else "defreeze",
        "actor_subject": "apfc-1",
        "actor_role": "fo.apfc",
        "data": {"category": category, "order_ref": order_ref},
    }


def issue_tracker_event(kind: str, uan: str = UAN, request_id: str = "ITR-REQ-1",
                        order_ref: str = "IS/ORDER/99", notice: str = "") -> dict[str, Any]:
    return {
        "request_id": request_id,
        "kind": kind,
        "target_uan": uan,
        "order_ref": order_ref,
        "notice": notice,
    }


def get_account_state(uan: str = UAN) -> str:
    async def fetch():
        async with db.sessions()() as session:
            row = (await session.execute(select(members.c.account_state).where(members.c.uan == uan))).first()
            return row[0] if row else None
    return asyncio.run(fetch())


def test_lead_3_delayed_workflow_freeze_cannot_overwrite_newer_admin_defreeze(api):
    """Lead 3: An urgent administrative defreeze order executed by the IS Division via
    platform-service.IssueTrackerExecuted.v1 unfreezes an account (account_state = 'ACTIVE').
    Meanwhile, a delayed message from an earlier workflow freeze case
    (workflow-service.ProcessTransitioned.v1) reaches member-service later.
    The older event must NOT overwrite account_state to FROZEN.
    """
    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 15, 0, tzinfo=UTC)

    # 1. Start with an account frozen earlier (e.g. at t0)
    t0 = datetime(2026, 10, 5, 9, 0, 0, tzinfo=UTC)
    deliver("ProcessTransitioned.v1",
            workflow_freeze_event(UAN, "FROZEN", instance_id="CASE-F0", order_ref="RO/ORD/0"),
            occurred_at=t0, producer="workflow-service", aggregate_type="process_instance", aggregate_id="CASE-F0")
    assert get_account_state(UAN) == "FROZEN"

    # Event 1 occurred at t1 (workflow freeze, e.g. CASE-F1)
    wf_freeze = workflow_freeze_event(UAN, "FROZEN", instance_id="CASE-F1", order_ref="RO/ORD/1")

    # Event 2 occurred at t2 > t1 (IS Division administrative defreeze)
    admin_defreeze = issue_tracker_event("DEFREEZE_MEMBER", UAN, request_id="ITR-DEF-1", order_ref="HO/DEF/01")

    # Out-of-order delivery: Event 2 (newer) arrives before Event 1 (older)
    assert deliver("IssueTrackerExecuted.v1", admin_defreeze,
                   occurred_at=t2, producer="platform-service",
                   aggregate_type="issue_tracker_request", aggregate_id="ITR-DEF-1") is True
    assert get_account_state(UAN) == "ACTIVE"

    # Delayed Event 1 (older) arrives now
    assert deliver("ProcessTransitioned.v1", wf_freeze,
                   occurred_at=t1, producer="workflow-service",
                   aggregate_type="process_instance", aggregate_id="CASE-F1") is True

    # Correct end state: account must remain ACTIVE, not overwritten to FROZEN by the older event
    assert get_account_state(UAN) == "ACTIVE"
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["account_state"] == "ACTIVE"
    # Outbox check: delayed wf_freeze must NOT have published a second AccountFrozen event
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN, "category": "AUDIT", "order_ref": "RO/ORD/0"}]
    assert outbox("AccountDefrozen.v1") == [{"target_type": "member", "target_id": UAN, "order_ref": "HO/DEF/01"}]


def test_lead_3_delayed_workflow_defreeze_cannot_overwrite_newer_admin_freeze(api):
    """Lead 3: An urgent administrative freeze order executed by IS Division at t2
    must not be overwritten by a delayed older workflow defreeze event from t1 < t2.
    """
    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 15, 0, tzinfo=UTC)

    # Event 1 occurred at t1: workflow defreeze
    wf_defreeze = workflow_freeze_event(UAN, "ACTIVE", instance_id="CASE-DEF-1", order_ref="RO/DEF/1")

    # Event 2 occurred at t2 > t1: admin urgent freeze
    admin_freeze = issue_tracker_event("FREEZE_MEMBER", UAN, request_id="ITR-FRZ-1", order_ref="HO/FRZ/01")

    # Out-of-order delivery: Event 2 arrives first
    assert deliver("IssueTrackerExecuted.v1", admin_freeze,
                   occurred_at=t2, producer="platform-service",
                   aggregate_type="issue_tracker_request", aggregate_id="ITR-FRZ-1") is True
    assert get_account_state(UAN) == "FROZEN"

    # Delayed Event 1 (older) arrives later
    assert deliver("ProcessTransitioned.v1", wf_defreeze,
                   occurred_at=t1, producer="workflow-service",
                   aggregate_type="process_instance", aggregate_id="CASE-DEF-1") is True

    # Correct end state: account must remain FROZEN
    assert get_account_state(UAN) == "FROZEN"
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["account_state"] == "FROZEN"
    # Outbox check: delayed wf_defreeze must NOT have published an AccountDefrozen event
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN, "category": "ISSUE_TRACKER", "order_ref": "HO/FRZ/01"}]
    assert outbox("AccountDefrozen.v1") == []


def test_lead_3_delayed_admin_freeze_cannot_overwrite_newer_workflow_defreeze(api):
    """Lead 3: A workflow defreeze at t2 must not be overwritten by an older
    delayed administrative freeze from t1 < t2.
    """
    t0 = datetime(2026, 10, 5, 9, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 15, 0, tzinfo=UTC)

    # 1. Freeze member initially at t0
    deliver("IssueTrackerExecuted.v1",
            issue_tracker_event("FREEZE_MEMBER", UAN, request_id="ITR-FRZ-0", order_ref="HO/FRZ/0"),
            occurred_at=t0, producer="platform-service",
            aggregate_type="issue_tracker_request", aggregate_id="ITR-FRZ-0")
    assert get_account_state(UAN) == "FROZEN"

    admin_freeze = issue_tracker_event("FREEZE_MEMBER", UAN, request_id="ITR-FRZ-OLD", order_ref="HO/FRZ/OLD")
    wf_defreeze = workflow_freeze_event(UAN, "ACTIVE", instance_id="CASE-DEF-NEW", order_ref="RO/DEF/NEW")

    # Out-of-order delivery: Event 2 arrives first
    assert deliver("ProcessTransitioned.v1", wf_defreeze,
                   occurred_at=t2, producer="workflow-service",
                   aggregate_type="process_instance", aggregate_id="CASE-DEF-NEW") is True
    assert get_account_state(UAN) == "ACTIVE"

    # Delayed Event 1 (older) arrives
    assert deliver("IssueTrackerExecuted.v1", admin_freeze,
                   occurred_at=t1, producer="platform-service",
                   aggregate_type="issue_tracker_request", aggregate_id="ITR-FRZ-OLD") is True

    # Correct end state: account must remain ACTIVE
    assert get_account_state(UAN) == "ACTIVE"
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["account_state"] == "ACTIVE"
    # Outbox check: delayed admin_freeze must NOT have published an AccountFrozen event
    assert outbox("AccountDefrozen.v1") == [{"target_type": "member", "target_id": UAN, "order_ref": "CASE-DEF-NEW"}]
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN, "category": "ISSUE_TRACKER", "order_ref": "HO/FRZ/0"}]


def test_lead_3_delayed_admin_defreeze_cannot_overwrite_newer_workflow_freeze(api):
    """Lead 3: A workflow freeze at t2 must not be overwritten by an older
    delayed administrative defreeze from t1 < t2.
    """
    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 15, 0, tzinfo=UTC)

    admin_defreeze = issue_tracker_event("DEFREEZE_MEMBER", UAN, request_id="ITR-DEF-OLD", order_ref="HO/DEF/OLD")
    wf_freeze = workflow_freeze_event(UAN, "FROZEN", instance_id="CASE-FRZ-NEW", order_ref="RO/FRZ/NEW")

    # Out-of-order delivery: Event 2 arrives first
    assert deliver("ProcessTransitioned.v1", wf_freeze,
                   occurred_at=t2, producer="workflow-service",
                   aggregate_type="process_instance", aggregate_id="CASE-FRZ-NEW") is True
    assert get_account_state(UAN) == "FROZEN"

    # Delayed Event 1 (older) arrives
    assert deliver("IssueTrackerExecuted.v1", admin_defreeze,
                   occurred_at=t1, producer="platform-service",
                   aggregate_type="issue_tracker_request", aggregate_id="ITR-DEF-OLD") is True

    # Correct end state: account must remain FROZEN
    assert get_account_state(UAN) == "FROZEN"
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["account_state"] == "FROZEN"
    # Outbox check: delayed admin_defreeze must NOT have published an AccountDefrozen event
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN, "category": "AUDIT", "order_ref": "RO/FRZ/NEW"}]
    assert outbox("AccountDefrozen.v1") == []


def test_lead_3_interleaved_events_from_multiple_producers(api):
    """Lead 3: Events from workflow-service and platform-service interleaved in arrival order.
    Timeline:
      t1: Workflow freeze (WF-1) -> FROZEN
      t2: IssueTracker defreeze (ITR-1) -> ACTIVE
      t3: Workflow freeze (WF-2) -> FROZEN
      t4: IssueTracker defreeze (ITR-2) -> ACTIVE
    Delivered in interleaved out-of-order sequence: t3, t1, t2, t4.
    End state must be ACTIVE with proper outbox event accounting.
    """
    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 10, 0, tzinfo=UTC)
    t3 = datetime(2026, 10, 5, 10, 20, 0, tzinfo=UTC)
    t4 = datetime(2026, 10, 5, 10, 30, 0, tzinfo=UTC)

    e1 = ("ProcessTransitioned.v1", workflow_freeze_event(UAN, "FROZEN", instance_id="CASE-WF1", order_ref="WF-1"),
          t1, "workflow-service", "process_instance", "CASE-WF1")
    e2 = ("IssueTrackerExecuted.v1", issue_tracker_event("DEFREEZE_MEMBER", UAN, request_id="ITR-1", order_ref="ITR-1"),
          t2, "platform-service", "issue_tracker_request", "ITR-1")
    e3 = ("ProcessTransitioned.v1", workflow_freeze_event(UAN, "FROZEN", instance_id="CASE-WF2", order_ref="WF-2"),
          t3, "workflow-service", "process_instance", "CASE-WF2")
    e4 = ("IssueTrackerExecuted.v1", issue_tracker_event("DEFREEZE_MEMBER", UAN, request_id="ITR-2", order_ref="ITR-2"),
          t4, "platform-service", "issue_tracker_request", "ITR-2")

    # Deliver in interleaved order: e3 (t3), e1 (t1), e2 (t2), e4 (t4)
    for etype, payload, occ, prod, agg_t, agg_id in (e3, e1, e2, e4):
        assert deliver(etype, payload, occurred_at=occ, producer=prod, aggregate_type=agg_t, aggregate_id=agg_id) is True

    # Final state must be ACTIVE (the state of the newest event e4 at t4)
    assert get_account_state(UAN) == "ACTIVE"
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["account_state"] == "ACTIVE"

    # Outbox check: exactly one AccountFrozen.v1 (from e3) and one AccountDefrozen.v1 (from e4)
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN, "category": "AUDIT", "order_ref": "WF-2"}]
    assert outbox("AccountDefrozen.v1") == [{"target_type": "member", "target_id": UAN, "order_ref": "ITR-2"}]
