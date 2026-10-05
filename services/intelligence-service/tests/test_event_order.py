"""Tests for event arrival order and cross-producer out-of-order delivery.

Leads verified:
- Lead 8: claim_facts (producers: claim-service, workflow-service)
"""
import asyncio
from sqlalchemy import select

import app.infra.db as db
from app.infra.tables import claim_facts
from tests.test_ai import DA_OFFICE, ctx, hdr


def test_claim_facts_decision_before_submission(ctx):
    """Lead 8: CaseDecisionSubmitted.v1 arrives before ClaimSubmitted.v1.

    When workflow-service emits CaseDecisionSubmitted.v1 before claim-service emits
    ClaimSubmitted.v1 (or if delivery is reordered across queues), the decision history
    must not be dropped when ClaimSubmitted.v1 arrives.
    """
    client, deliver, _ = ctx
    claim_id = "CLM-ORDER-001"

    # 1. Out-of-order delivery: decision arrives first from workflow-service
    deliver("CaseDecisionSubmitted.v1", {
        "case_id": "CASE-ORDER-001",
        "claim_id": claim_id,
        "decision": "RECOMMEND",
        "approval_level": 0,
        "officer_role": "fo.da_accounts",
    })

    # 2. ClaimSubmitted arrives later from claim-service
    deliver("ClaimSubmitted.v1", {
        "claim_id": claim_id,
        "office_id": "RO-DEMO-01",
        "form_type": "19",
        "amount_paise": 5000000,
        "account_link_id": "AL-0001",
        "route": "REVIEW",
        "rule_version": "demo-rules-2026.9",
    })

    # 3. Verify claim_facts row contains both the claim attributes and the earlier decision
    async def get_fact():
        async with db.sessions()() as session:
            return (await session.execute(
                select(claim_facts).where(claim_facts.c.claim_id == claim_id)
            )).mappings().first()

    row = asyncio.run(get_fact())
    assert row is not None
    assert row["office_id"] == "RO-DEMO-01"
    assert row["form_type"] == "19"
    assert row["amount_paise"] == 5000000
    assert row["account_link_id"] == "AL-0001"
    assert row["route"] == "REVIEW"
    assert row["rule_version"] == "demo-rules-2026.9"
    assert len(row["decisions"]) == 1
    assert row["decisions"] == [{"decision": "RECOMMEND", "level": 0, "role": "fo.da_accounts"}]

    # 4. Verify AI analysis endpoint recognises the earlier decision
    res = client.post(
        "/api/v1/ai/claims/analyse",
        json={"claim_id": claim_id},
        headers=hdr("fo.da_accounts", DA_OFFICE),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert any("Earlier decisions exist" in u for u in data["uncertainties"])


def test_claim_facts_interleaved_decisions_and_submission(ctx):
    """Lead 8: Multiple decisions arrive interleaved before and after ClaimSubmitted.v1.

    Two decisions arrive from workflow-service before ClaimSubmitted.v1,
    then ClaimSubmitted.v1 arrives, followed by a final approval decision.
    All three decisions must be preserved in order.
    """
    client, deliver, _ = ctx
    claim_id = "CLM-ORDER-002"

    # 1. Level 0 recommendation arrives first
    deliver("CaseDecisionSubmitted.v1", {
        "case_id": "CASE-ORDER-002",
        "claim_id": claim_id,
        "decision": "RECOMMEND",
        "approval_level": 0,
        "officer_role": "fo.da_accounts",
    })

    # 2. Level 1 approval arrives second
    deliver("CaseDecisionSubmitted.v1", {
        "case_id": "CASE-ORDER-002",
        "claim_id": claim_id,
        "decision": "APPROVE",
        "approval_level": 1,
        "officer_role": "fo.ss",
    })

    # 3. Claim submission arrives third
    deliver("ClaimSubmitted.v1", {
        "claim_id": claim_id,
        "office_id": "RO-DEMO-01",
        "form_type": "31",
        "amount_paise": 10000000,
        "account_link_id": "AL-0002",
        "route": "REVIEW",
        "rule_version": "demo-rules-2026.9",
    })

    # 4. Final level 2 approval arrives fourth
    deliver("CaseDecisionSubmitted.v1", {
        "case_id": "CASE-ORDER-002",
        "claim_id": claim_id,
        "decision": "APPROVE",
        "approval_level": 2,
        "officer_role": "fo.apfc",
    })

    # 5. Verify claim_facts row contains all three decisions
    async def get_fact():
        async with db.sessions()() as session:
            return (await session.execute(
                select(claim_facts).where(claim_facts.c.claim_id == claim_id)
            )).mappings().first()

    row = asyncio.run(get_fact())
    assert row is not None
    assert row["office_id"] == "RO-DEMO-01"
    assert row["form_type"] == "31"
    assert row["amount_paise"] == 10000000
    assert row["account_link_id"] == "AL-0002"
    assert row["route"] == "REVIEW"
    assert len(row["decisions"]) == 3
    assert row["decisions"] == [
        {"decision": "RECOMMEND", "level": 0, "role": "fo.da_accounts"},
        {"decision": "APPROVE", "level": 1, "role": "fo.ss"},
        {"decision": "APPROVE", "level": 2, "role": "fo.apfc"},
    ]

    # 6. Verify AI analysis endpoint works and recognises earlier decisions
    res = client.post(
        "/api/v1/ai/claims/analyse",
        json={"claim_id": claim_id},
        headers=hdr("fo.da_accounts", DA_OFFICE),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert any("Earlier decisions exist" in u for u in data["uncertainties"])


def test_claim_facts_stub_row_cannot_be_analysed_before_submission(ctx):
    """A claim with only a decision stub cannot be analysed until ClaimSubmitted arrives."""
    client, deliver, _ = ctx
    claim_id = "CLM-ORDER-003"

    # 1. Decision arrives first, creating a stub row with decisions but no office_id
    deliver("CaseDecisionSubmitted.v1", {
        "case_id": "CASE-ORDER-003",
        "claim_id": claim_id,
        "decision": "RECOMMEND",
        "approval_level": 0,
        "officer_role": "fo.da_accounts",
    })

    # 2. Officer analysis before ClaimSubmitted returns 404
    res = client.post(
        "/api/v1/ai/claims/analyse",
        json={"claim_id": claim_id},
        headers=hdr("fo.da_accounts", DA_OFFICE),
    )
    assert res.status_code == 404

    # 3. Now ClaimSubmitted arrives
    deliver("ClaimSubmitted.v1", {
        "claim_id": claim_id,
        "office_id": "RO-DEMO-01",
        "form_type": "19",
        "amount_paise": 4000000,
        "account_link_id": "AL-0003",
        "route": "REVIEW",
        "rule_version": "demo-rules-2026.9",
    })

    # 4. Officer analysis now succeeds and includes the decision history
    res = client.post(
        "/api/v1/ai/claims/analyse",
        json={"claim_id": claim_id},
        headers=hdr("fo.da_accounts", DA_OFFICE),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert any("Earlier decisions exist" in u for u in data["uncertainties"])
