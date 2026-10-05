"""Order and concurrency safety for claim-service event projections (P2.30 Lead 1).

Lead 1 in docs/event-copies.md notes that the claims table copy receives events about the same claim
from multiple producers (member-service, workflow-service, payment-simulator).
The failure scenario hypothesized:
- An AccountFrozen.v1 event races with CaseDecisionSubmitted.v1 or PaymentConfirmed.v1.
- If AccountDefrozen.v1 or an out-of-order decision arrives after payment has been completed,
  the terminal SETTLED state could be reverted to UNDER_REVIEW or AUTO_APPROVED.

These tests deliver the lead's events in out-of-order and interleaved sequences on the unchanged code
to verify whether the existing state machine and HOLDABLE guards protect the copy.
"""
from tests.test_claims_api import (
    CASHIER,
    JOURNEY_B_AMOUNT,
    SEED,
    _approved_claim,
    confirm,
    create,
    ctx,  # noqa: F401
    hdr,
    member,
)


def _debit(deliver, claim_id, amount=JOURNEY_B_AMOUNT):
    deliver(
        "ClaimDebitPosted.v1",
        {
            "journal_id": f"J-{claim_id}",
            "claim_id": claim_id,
            "postings": [
                {
                    "account_code": "AC01_EPF",
                    "side": "debit",
                    "amount_paise": amount,
                    "account_link_id": "AL-0001",
                    "share": "employee",
                },
                {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": amount},
            ],
        },
        "contribution-service",
    )


def _settled_claim(client, deliver, amount=JOURNEY_B_AMOUNT):
    claim_id = _approved_claim(client, deliver)
    _debit(deliver, claim_id, amount)
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": amount}
    res = client.post(
        f"/api/v1/office/claims/{claim_id}/payment-instructions",
        json={},
        headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": f"pay-{claim_id}"}),
    )
    assert res.status_code == 200, res.json()
    pid = res.json()["data"]["payment_id"]
    deliver(
        "PaymentConfirmed.v1",
        {
            "payment_id": pid,
            "purpose": "CLAIM_SETTLEMENT",
            "reference_type": "claim",
            "reference_id": claim_id,
            "amount_paise": amount,
            "mock": True,
        },
        "payment-simulator",
    )
    return claim_id, pid


def test_settled_claim_not_reopened_by_late_freeze_or_decision(ctx):
    """Lead 1: After a claim is SETTLED by payment-simulator, late AccountFrozen / AccountDefrozen

    events from member-service or an out-of-order CaseDecisionSubmitted from workflow-service
    must not revert the terminal SETTLED state to UNDER_REVIEW or AUTO_APPROVED.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]
    claim_id, pid = _settled_claim(client, deliver)

    # Verify claim is SETTLED
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"

    # Out-of-order AccountFrozen.v1 arrives after settlement
    deliver(
        "AccountFrozen.v1",
        {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "ORD-LATE"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"

    # Subsequent AccountDefrozen.v1 arrives
    deliver(
        "AccountDefrozen.v1",
        {"target_type": "member", "target_id": uan, "order_ref": "ORD-DEFROST"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"

    # Late CaseDecisionSubmitted.v1 (e.g. delayed re-delivery or out-of-order arrival from workflow)
    base = {"case_id": "CASE-1", "claim_id": claim_id, "officer_subject": "x", "reason": "Late review"}
    for decision, role in [
        ("RECOMMEND", "fo.da_accounts"),
        ("APPROVE", "fo.apfc"),
        ("REJECT", "fo.apfc"),
        ("RETURN", "fo.ss"),
    ]:
        deliver(
            "CaseDecisionSubmitted.v1",
            {**base, "decision": decision, "officer_role": role, "final": decision == "APPROVE"},
            "workflow-service",
        )
        claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
        assert claim["state"] == "SETTLED"

    # In database as well
    db_state = q(f"SELECT state FROM claims WHERE claim_id = '{claim_id}'")[0][0]
    assert db_state == "SETTLED"


def test_payment_pending_claim_not_held_by_concurrent_freeze(ctx):
    """Lead 1: A claim in PAYMENT_PENDING (already with mock bank) is not put on hold by

    AccountFrozen.v1, allowing PaymentConfirmed.v1 to settle it normally.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]
    claim_id = _approved_claim(client, deliver)
    _debit(deliver, claim_id)

    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    res = client.post(
        f"/api/v1/office/claims/{claim_id}/payment-instructions",
        json={},
        headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": f"pay-{claim_id}"}),
    )
    assert res.status_code == 200
    pid = res.json()["data"]["payment_id"]

    # Claim is now PAYMENT_PENDING
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "PAYMENT_PENDING"

    # AccountFrozen.v1 arrives while payment is in-flight
    deliver(
        "AccountFrozen.v1",
        {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "ORD-1"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "PAYMENT_PENDING"

    # PaymentConfirmed.v1 arrives from bank
    deliver(
        "PaymentConfirmed.v1",
        {
            "payment_id": pid,
            "purpose": "CLAIM_SETTLEMENT",
            "reference_type": "claim",
            "reference_id": claim_id,
            "amount_paise": JOURNEY_B_AMOUNT,
            "mock": True,
        },
        "payment-simulator",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"

    # Later AccountDefrozen.v1 arrives
    deliver(
        "AccountDefrozen.v1",
        {"target_type": "member", "target_id": uan, "order_ref": "ORD-2"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"


def test_decision_before_freeze_restarts_under_review_after_defreeze(ctx):
    """Lead 1: Approver decision arrives before AccountFrozen.v1.

    When AccountDefrozen.v1 subsequently arrives, earlier approvals are voided and
    the claim restarts in UNDER_REVIEW.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]

    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]
    base = {"case_id": "CASE-1", "claim_id": claim_id, "officer_subject": "x", "reason": None, "next_role": None}
    deliver(
        "CaseDecisionSubmitted.v1",
        {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts", "approval_level": 0, "final": False},
        "workflow-service",
    )
    # Approver approves
    deliver(
        "CaseDecisionSubmitted.v1",
        {**base, "decision": "APPROVE", "officer_role": "fo.ss", "approval_level": 1, "final": False},
        "workflow-service",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "AWAITING_NEXT_APPROVAL"

    # Freeze arrives after approval
    deliver("AccountFrozen.v1", {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "O1"}, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "ON_HOLD_FROZEN"

    # Defreeze arrives -> approvals void, claim restarted in UNDER_REVIEW
    deliver("AccountDefrozen.v1", {"target_type": "member", "target_id": uan, "order_ref": "O2"}, "member-service")
    d = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert d["state"] == "UNDER_REVIEW"
    db_row = q(f"SELECT state, recommended FROM claims WHERE claim_id = '{claim_id}'")[0]
    assert db_row == ("UNDER_REVIEW", False)


def test_freeze_before_decision_restarts_under_review_after_defreeze(ctx):
    """Lead 1: AccountFrozen.v1 arrives before an in-flight CaseDecisionSubmitted.v1.

    The decision is ignored while ON_HOLD_FROZEN, and once AccountDefrozen.v1 arrives,
    the claim restarts in UNDER_REVIEW. Both interleavings achieve the exact same end state.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]

    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]
    base = {"case_id": "CASE-2", "claim_id": claim_id, "officer_subject": "x", "reason": None, "next_role": None}
    deliver(
        "CaseDecisionSubmitted.v1",
        {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts", "approval_level": 0, "final": False},
        "workflow-service",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "RECOMMENDED"

    # Freeze arrives before next approver's decision
    deliver("AccountFrozen.v1", {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "O3"}, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "ON_HOLD_FROZEN"

    # In-flight approval from approver arrives while ON_HOLD_FROZEN
    deliver(
        "CaseDecisionSubmitted.v1",
        {**base, "decision": "APPROVE", "officer_role": "fo.ss", "approval_level": 1, "final": False},
        "workflow-service",
    )
    # The decision is ignored while on hold
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "ON_HOLD_FROZEN"

    # Defreeze arrives
    deliver("AccountDefrozen.v1", {"target_type": "member", "target_id": uan, "order_ref": "O4"}, "member-service")
    d = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert d["state"] == "UNDER_REVIEW"
    db_row = q(f"SELECT state, recommended FROM claims WHERE claim_id = '{claim_id}'")[0]
    assert db_row == ("UNDER_REVIEW", False)


def test_member_death_rejects_open_claim_and_ignores_late_decision_or_freeze(ctx):
    """Lead 1: When a member death is recorded (MemberDeathRecorded), open claims transition

    to REJECTED_WITH_REASON. Out-of-order decisions or freeze events cannot overwrite
    this terminal rejection.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]

    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "UNDER_REVIEW"

    deliver(
        "MemberDeathRecorded.v1",
        {"uan": uan, "date_of_death": "2026-10-01", "source": "CIVIL_REGISTRY"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "REJECTED_WITH_REASON"

    # Out-of-order approval decision arrives
    deliver(
        "CaseDecisionSubmitted.v1",
        {
            "case_id": "CASE-D",
            "claim_id": claim_id,
            "officer_subject": "x",
            "decision": "APPROVE",
            "officer_role": "fo.apfc",
            "final": True,
        },
        "workflow-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "REJECTED_WITH_REASON"

    # Out-of-order AccountFrozen.v1 arrives
    deliver(
        "AccountFrozen.v1",
        {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "ORD-D"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert claim["state"] == "REJECTED_WITH_REASON"


def test_settled_claim_not_closed_by_subsequent_member_death(ctx):
    """Lead 1: A claim that was already SETTLED is left untouched by a subsequent

    MemberDeathRecorded event (claims already paid are not retroactively closed).
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]

    settled_id, _ = _settled_claim(client, deliver)
    deliver(
        "MemberDeathRecorded.v1",
        {"uan": uan, "date_of_death": "2026-10-01", "source": "CIVIL_REGISTRY"},
        "member-service",
    )
    claim = client.get(f"/api/v1/members/me/claims/{settled_id}", headers=member()).json()["data"]
    assert claim["state"] == "SETTLED"
    db_state = q(f"SELECT state FROM claims WHERE claim_id = '{settled_id}'")[0][0]
    assert db_state == "SETTLED"


def test_auto_approved_settled_claim_not_reopened_by_late_freeze(ctx):
    """Lead 1: An auto-approved claim settled by the bank cannot be put on hold or reverted

    by late AccountFrozen.v1 / AccountDefrozen.v1 events.
    """
    client, q, deliver = ctx
    uan = SEED["members"][0]["uan"]
    amount = 5000000  # ₹50,000 is within auto-settlement limit

    claim_id = confirm(client, create(client, amount=amount).json()["data"]).json()["data"]["claim_id"]
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "AUTO_APPROVED"

    _debit(deliver, claim_id, amount)
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": amount}
    res = client.post(
        f"/api/v1/office/claims/{claim_id}/payment-instructions",
        json={},
        headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": f"pay-auto-{claim_id}"}),
    )
    assert res.status_code == 200
    pid = res.json()["data"]["payment_id"]

    deliver(
        "PaymentConfirmed.v1",
        {
            "payment_id": pid,
            "purpose": "CLAIM_SETTLEMENT",
            "reference_type": "claim",
            "reference_id": claim_id,
            "amount_paise": amount,
            "mock": True,
        },
        "payment-simulator",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "SETTLED"

    # Out-of-order freeze and defreeze arrive
    deliver("AccountFrozen.v1", {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "O-LATE"}, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "SETTLED"

    deliver("AccountDefrozen.v1", {"target_type": "member", "target_id": uan, "order_ref": "O-DEF"}, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "SETTLED"
    assert q(f"SELECT state FROM claims WHERE claim_id = '{claim_id}'")[0][0] == "SETTLED"


def test_payment_returned_claim_not_overwritten_by_late_decision_or_stale_confirmation(ctx):
    """Lead 1: When a payment is returned by the bank, the claim transitions to PAYMENT_RETURNED.

    Late decisions or stale PaymentConfirmed events must not overwrite PAYMENT_RETURNED.
    """
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    _debit(deliver, claim_id)

    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    res = client.post(
        f"/api/v1/office/claims/{claim_id}/payment-instructions",
        json={"demo_scenario": "RETURN"},
        headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": f"pay-ret-{claim_id}"}),
    )
    assert res.status_code == 200
    pid = res.json()["data"]["payment_id"]

    deliver(
        "PaymentReturned.v1",
        {
            "payment_id": pid,
            "purpose": "CLAIM_SETTLEMENT",
            "reference_type": "claim",
            "reference": claim_id,
            "return_reason": "ACCOUNT_CLOSED",
            "mock": True,
        },
        "payment-simulator",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "PAYMENT_RETURNED"

    # Stale PaymentConfirmed.v1 for this payment (e.g. out of order delivery after return)
    deliver(
        "PaymentConfirmed.v1",
        {
            "payment_id": pid,
            "purpose": "CLAIM_SETTLEMENT",
            "reference_type": "claim",
            "reference_id": claim_id,
            "amount_paise": JOURNEY_B_AMOUNT,
            "mock": True,
        },
        "payment-simulator",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "PAYMENT_RETURNED"

    # Delayed CaseDecisionSubmitted.v1 (APPROVE)
    base = {"case_id": "CASE-R", "claim_id": claim_id, "officer_subject": "x", "reason": "Late"}
    deliver(
        "CaseDecisionSubmitted.v1",
        {**base, "decision": "APPROVE", "officer_role": "fo.apfc", "final": True},
        "workflow-service",
    )
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "PAYMENT_RETURNED"
