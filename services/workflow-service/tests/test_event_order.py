"""Order and concurrency safety for workflow-service event projections (P2.30 Lead 4).

Lead 4 in docs/event-copies.md notes that the `cases` table copy receives events about the same
claim from multiple producers:
- claim-service (ClaimSubmitted.v1, ClaimDecisionRecorded.v1, PaymentInstructed.v1, ClaimStateChanged.v1)
- payment-simulator (PaymentConfirmed.v1, PaymentReturned.v1)

Failure Scenarios:
1. When claim-service emits ClaimStateChanged.v1 (e.g. redisbursement review or hold transitions),
   it races with bank confirmations (PaymentConfirmed.v1 / PaymentReturned.v1) from payment-simulator.
   An out-of-order hold event can overwrite a closed case (CLOSED) back to ON_HOLD or IN_REVIEW,
   corrupting office task queues.
2. Cross-producer race: PaymentConfirmed.v1 or PaymentReturned.v1 arrives before PaymentInstructed.v1
   due to independent queue delivery timings.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import uuid

import pytest

import app.infra.db as db
from app.infra.messaging import dispatch
from epfo_persistence.consumer import apply_once
from tests.test_cases_api import (
    AMOUNT,
    APFC,
    CASH,
    DA,
    SS,
    ctx,  # noqa: F401
    hdr,
    queue,
    submitted,
)


def deliver_event(event_type, payload, producer="claim-service", occurred_at=None):
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "producer": producer,
        "correlation_id": str(uuid.uuid4()),
        "payload": payload,
    }
    if occurred_at is not None:
        event["occurred_at"] = occurred_at.isoformat() if hasattr(occurred_at, "isoformat") else str(occurred_at)
    return asyncio.run(apply_once(db.sessions(), event, dispatch))


def _auto_approved_case(deliver, claim_id="CLM-LEAD4-01"):
    submitted(deliver, amount=5000000, route="AUTO", claim_id=claim_id)
    deliver("ClaimDecisionRecorded.v1", {
        "claim_id": claim_id, "decision": "AUTO_APPROVED", "reason_code": "X",
        "rule_version": "demo-rules-2026.1", "amount_paise": 5000000, "account_link_id": "AL-0001"
    })


def _paid_case(deliver, claim_id="CLM-LEAD4-01", payment_id="P-01"):
    _auto_approved_case(deliver, claim_id=claim_id)
    t0 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    deliver_event("PaymentInstructed.v1", {
        "claim_id": claim_id, "payment_id": payment_id, "amount_paise": 5000000, "attempt": 1
    }, producer="claim-service", occurred_at=t0)
    deliver_event("PaymentConfirmed.v1", {
        "payment_id": payment_id, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference_id": claim_id, "amount_paise": 5000000, "mock": True
    }, producer="payment-simulator", occurred_at=t0 + timedelta(seconds=5))


# ==============================================================================
# Lead 4: cases table (state, current_role, step)
# ==============================================================================

def test_lead_4_closed_case_not_reopened_by_late_hold(ctx):
    """Lead 4: After a case is CLOSED by PaymentConfirmed.v1, a late ClaimStateChanged.v1

    (ON_HOLD_FROZEN) from claim-service must not overwrite the case to ON_HOLD.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-HOLD-1"
    _paid_case(deliver, claim_id=claim_id, payment_id="PAY-01")

    # Verify case is CLOSED
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED" and role is None

    # Late ClaimStateChanged.v1 arrives with earlier timestamp
    t_earlier = datetime(2026, 10, 5, 9, 59, 0, tzinfo=UTC)
    base = {
        "claim_id": claim_id, "from_state": "RECOMMENDED", "to_state": "ON_HOLD_FROZEN",
        "reason": "ACCOUNT_FROZEN", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
        "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"
    }
    deliver_event("ClaimStateChanged.v1", base, producer="claim-service", occurred_at=t_earlier)

    # Correct end state: case must remain CLOSED
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED"
    assert role is None


def test_lead_4_closed_case_not_reopened_by_late_defreeze_review(ctx):
    """Lead 4: After a case is CLOSED, a delayed ClaimStateChanged.v1 with DEFROZEN_APPROVALS_VOID

    must not restart the case to IN_REVIEW or put it back into an officer's queue.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-DEFROST-1"
    _paid_case(deliver, claim_id=claim_id, payment_id="PAY-02")

    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED"

    t_earlier = datetime(2026, 10, 5, 9, 59, 30, tzinfo=UTC)
    base = {
        "claim_id": claim_id, "from_state": "ON_HOLD_FROZEN", "to_state": "UNDER_REVIEW",
        "reason": "DEFROZEN_APPROVALS_VOID", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
        "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"
    }
    deliver_event("ClaimStateChanged.v1", base, producer="claim-service", occurred_at=t_earlier)

    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED"
    assert role is None
    assert queue(client, DA, "fo.da_accounts") == []


def test_lead_4_closed_case_not_reopened_by_late_redisbursement(ctx):
    """Lead 4: After a case is CLOSED, an out-of-order CORRECTION_PENDING ClaimStateChanged.v1

    must not set REDISBURSEMENT_REVIEW or push a task to fo.apfc.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-REDISB-1"
    _paid_case(deliver, claim_id=claim_id, payment_id="PAY-03")

    t_earlier = datetime(2026, 10, 5, 9, 58, 0, tzinfo=UTC)
    base = {
        "claim_id": claim_id, "from_state": "PAYMENT_RETURNED", "to_state": "CORRECTION_PENDING",
        "reason": "", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
        "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"
    }
    deliver_event("ClaimStateChanged.v1", base, producer="claim-service", occurred_at=t_earlier)

    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED"
    assert role is None
    assert queue(client, APFC, "fo.apfc") == []


def test_lead_4_payment_confirmed_arriving_before_payment_instructed(ctx):
    """Lead 4: PaymentConfirmed.v1 from payment-simulator arrives before PaymentInstructed.v1

    from claim-service (cross-producer race). Case must finish in CLOSED, not stuck in PAYMENT_ISSUED.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-RACE-CONFIRM"
    _auto_approved_case(deliver, claim_id=claim_id)

    # Case is in AWAITING_PAYMENT
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "AWAITING_PAYMENT"

    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 0, 5, tzinfo=UTC)

    # PaymentConfirmed.v1 (t2) arrives FIRST
    deliver_event("PaymentConfirmed.v1", {
        "payment_id": "P-RACE-1", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference_id": claim_id, "amount_paise": 5000000, "mock": True
    }, producer="payment-simulator", occurred_at=t2)

    # PaymentInstructed.v1 (t1) arrives SECOND
    deliver_event("PaymentInstructed.v1", {
        "claim_id": claim_id, "payment_id": "P-RACE-1", "amount_paise": 5000000, "attempt": 1
    }, producer="claim-service", occurred_at=t1)

    # End state must be CLOSED
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "CLOSED"
    assert role is None


def test_lead_4_payment_returned_arriving_before_payment_instructed(ctx):
    """Lead 4: PaymentReturned.v1 arrives before PaymentInstructed.v1 (cross-producer race).

    Case must finish in RETURNED_AWAITING_MEMBER, not stuck in PAYMENT_ISSUED.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-RACE-RETURN"
    _auto_approved_case(deliver, claim_id=claim_id)

    # Case is in AWAITING_PAYMENT
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "AWAITING_PAYMENT"

    t1 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 10, 0, 5, tzinfo=UTC)

    # PaymentReturned.v1 (t2) arrives FIRST
    deliver_event("PaymentReturned.v1", {
        "payment_id": "P-RACE-2", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference": claim_id, "return_reason": "ACCOUNT_CLOSED", "mock": True
    }, producer="payment-simulator", occurred_at=t2)

    # PaymentInstructed.v1 (t1) arrives SECOND
    deliver_event("PaymentInstructed.v1", {
        "claim_id": claim_id, "payment_id": "P-RACE-2", "amount_paise": 5000000, "attempt": 1
    }, producer="claim-service", occurred_at=t1)

    # End state must be RETURNED_AWAITING_MEMBER
    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "RETURNED_AWAITING_MEMBER"
    assert role is None


def test_lead_4_interleaved_freeze_and_payment_confirmed(ctx):
    """Lead 4: Interleaved race between hold (ON_HOLD_FROZEN) and payment confirmation.

    In both interleavings:
    - Hold applied before PaymentConfirmed -> PaymentConfirmed must still settle and close the case.
    - PaymentConfirmed applied before Hold -> Hold must not reopen the closed case.
    """
    client, q, deliver = ctx

    # Subcase A: Hold arrives while PAYMENT_ISSUED, then PaymentConfirmed arrives
    claim_a = "CLM-INTERLEAVE-A"
    _auto_approved_case(deliver, claim_id=claim_a)
    t0 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    deliver_event("PaymentInstructed.v1", {
        "claim_id": claim_a, "payment_id": "P-INT-A", "amount_paise": 5000000, "attempt": 1
    }, producer="claim-service", occurred_at=t0)

    # Hold arrives while PAYMENT_ISSUED (e.g. account frozen at t1)
    t1 = t0 + timedelta(seconds=1)
    base_a = {
        "claim_id": claim_a, "from_state": "PAYMENT_ISSUED", "to_state": "ON_HOLD_FROZEN",
        "reason": "ACCOUNT_FROZEN", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
        "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"
    }
    deliver_event("ClaimStateChanged.v1", base_a, producer="claim-service", occurred_at=t1)

    # Bank payment confirmation arrives at t2 > t1
    t2 = t0 + timedelta(seconds=5)
    deliver_event("PaymentConfirmed.v1", {
        "payment_id": "P-INT-A", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference_id": claim_a, "amount_paise": 5000000, "mock": True
    }, producer="payment-simulator", occurred_at=t2)

    [(state_a, role_a)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_a}'")
    assert state_a == "CLOSED"
    assert role_a is None

    # Subcase B: PaymentConfirmed arrives at t2, older hold event at t1 arrives after t2
    claim_b = "CLM-INTERLEAVE-B"
    _paid_case(deliver, claim_id=claim_b, payment_id="P-INT-B")
    base_b = {
        "claim_id": claim_b, "from_state": "PAYMENT_ISSUED", "to_state": "ON_HOLD_FROZEN",
        "reason": "ACCOUNT_FROZEN", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
        "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"
    }
    deliver_event("ClaimStateChanged.v1", base_b, producer="claim-service", occurred_at=t1)

    [(state_b, role_b)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_b}'")
    assert state_b == "CLOSED"
    assert role_b is None


def test_lead_4_stale_payment_confirmation_after_return(ctx):
    """Lead 4: When a payment has been returned (RETURNED_AWAITING_MEMBER), a stale or delayed

    PaymentConfirmed.v1 for that same payment must not overwrite the case to CLOSED.
    """
    client, q, deliver = ctx
    claim_id = "CLM-ORDER-STALE-CONFIRM"
    _auto_approved_case(deliver, claim_id=claim_id)

    t0 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    deliver_event("PaymentInstructed.v1", {
        "claim_id": claim_id, "payment_id": "P-STALE-1", "amount_paise": 5000000, "attempt": 1
    }, producer="claim-service", occurred_at=t0)

    # Bank returned payment
    t1 = t0 + timedelta(seconds=2)
    deliver_event("PaymentReturned.v1", {
        "payment_id": "P-STALE-1", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference": claim_id, "return_reason": "ACCOUNT_CLOSED", "mock": True
    }, producer="payment-simulator", occurred_at=t1)

    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "RETURNED_AWAITING_MEMBER"

    # Stale PaymentConfirmed.v1 with earlier timestamp arrives
    t_stale = t0 + timedelta(seconds=1)
    deliver_event("PaymentConfirmed.v1", {
        "payment_id": "P-STALE-1", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference_id": claim_id, "amount_paise": 5000000, "mock": True
    }, producer="payment-simulator", occurred_at=t_stale)

    [(state, role)] = q(f"SELECT state, current_role FROM cases WHERE claim_id = '{claim_id}'")
    assert state == "RETURNED_AWAITING_MEMBER"
    assert role is None
