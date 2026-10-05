"""Tests for event arrival order and cross-producer out-of-order delivery.

Leads verified:
- Lead 5: claim_facts (producers: claim-service, payment-simulator)
- Lead 6: contribution_facts (producers: contribution-service, payment-simulator)
"""
import asyncio
from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select

import app.infra.db as db
from app.infra.tables import claim_facts, contribution_facts, principal_employer_tags
from tests.test_read_models import confirmed, ctx, hdr


def test_claim_facts_payment_before_submission(ctx):
    """Lead 5: PaymentConfirmed.v1 and PaymentReturned.v1 arrive before ClaimSubmitted.v1."""
    client, deliver = ctx
    now = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    claim_id = "CLM-ORDER-001"

    # Out-of-order delivery: payment returned and confirmed arrive before claim is submitted
    deliver("PaymentReturned.v1", {"payment_id": str(uuid.uuid4()), "purpose": "CLAIM_SETTLEMENT",
                                   "reference": claim_id, "amount_paise": 50000},
            occurred_at=now + timedelta(minutes=5))
    confirmed(deliver, claim_id, "CLAIM_SETTLEMENT", at=now + timedelta(minutes=10))

    # Then ClaimSubmitted arrives from claim-service
    deliver("ClaimSubmitted.v1", {"claim_id": claim_id, "office_id": "RO-DEMO-01", "form_type": "19",
                                  "amount_paise": 50000, "route": "AUTO"},
            occurred_at=now)

    # Verify claim_facts row
    async def get_claim():
        async with db.sessions()() as session:
            return (await session.execute(select(claim_facts).where(claim_facts.c.claim_id == claim_id))).mappings().first()

    row = asyncio.run(get_claim())
    assert row is not None
    assert row["settled_at"] is not None
    assert row["returned_count"] == 1
    assert row["office_id"] == "RO-DEMO-01"
    assert row["amount_paise"] == 50000

    # Verify claim monitoring endpoint reflects the settled claim
    response = client.get("/api/v1/monitoring/claims", headers=hdr("fo.oic"))
    assert response.status_code == 200
    totals = response.json()["data"]["totals"]
    assert totals["submitted"] == 1
    assert totals["settled"] == 1
    assert totals["payment_returns"] == 1


def test_claim_facts_interleaved_decision_and_payment(ctx):
    """Lead 5: Decision and payment arrive before submission, followed by payment return."""
    client, deliver = ctx
    now = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    claim_id = "CLM-ORDER-002"

    # 1. Decision arrives first
    deliver("ClaimDecisionRecorded.v1", {"claim_id": claim_id, "decision": "AUTO_APPROVED"},
            occurred_at=now + timedelta(minutes=2))
    # 2. Payment confirmed arrives second
    confirmed(deliver, claim_id, "CLAIM_SETTLEMENT", at=now + timedelta(minutes=5))
    # 3. Claim submission arrives third
    deliver("ClaimSubmitted.v1", {"claim_id": claim_id, "office_id": "RO-DEMO-01", "form_type": "10C",
                                  "amount_paise": 75000, "route": "AUTO"},
            occurred_at=now)
    # 4. Bank return arrives fourth
    deliver("PaymentReturned.v1", {"payment_id": str(uuid.uuid4()), "purpose": "CLAIM_SETTLEMENT",
                                   "reference": claim_id},
            occurred_at=now + timedelta(minutes=15))

    async def get_claim():
        async with db.sessions()() as session:
            return (await session.execute(select(claim_facts).where(claim_facts.c.claim_id == claim_id))).mappings().first()

    row = asyncio.run(get_claim())
    assert row is not None
    assert row["decision"] == "AUTO_APPROVED"
    assert row["settled_at"] is not None
    assert row["returned_count"] == 1
    assert row["form_type"] == "10C"
    assert row["amount_paise"] == 75000

    response = client.get("/api/v1/monitoring/claims", headers=hdr("fo.oic"))
    assert response.status_code == 200
    totals = response.json()["data"]["totals"]
    assert totals["submitted"] == 1
    assert totals["auto_approved"] == 1
    assert totals["settled"] == 1
    assert totals["payment_returns"] == 1


def test_contribution_facts_payment_before_submission(ctx):
    """Lead 6: PaymentConfirmed.v1 (CHALLAN) arrives before ECRSubmitted.v1."""
    client, deliver = ctx
    now = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    filing_id = "F-ORDER-001"
    trrn = "TRRN-ORDER-001"

    # ECRValidated may arrive first or not; let's deliver ECRValidated first
    deliver("ECRValidated.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0001",
                                "wage_month": "2026-08", "member_count": 5},
            occurred_at=now)

    # Tag principal employer before payment
    deliver("PrincipalEmployerTagged.v1", {
        "filing_id": filing_id, "principal_establishment_id": "EST-PRINCIPAL-001",
        "work_order_ref": "WO-001", "contractor_establishment_id": "EST-DEMO-0001",
        "wage_month": "2026-08", "members": 5, "epf_wages_paise": 500000,
        "contribution_paise": 60000, "paid": False,
    }, occurred_at=now + timedelta(minutes=1))

    # PaymentConfirmed (CHALLAN) arrives with trrn from payment-simulator BEFORE ECRSubmitted
    confirmed(deliver, trrn, "CHALLAN", at=now + timedelta(minutes=5))

    # Finally ECRSubmitted arrives from contribution-service
    deliver("ECRSubmitted.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0001",
                                "trrn": trrn, "total_paise": 60000, "rule_version": "demo"},
            occurred_at=now + timedelta(minutes=2))

    # Verify contribution_facts row
    async def get_facts():
        async with db.sessions()() as session:
            fact = (await session.execute(
                select(contribution_facts).where(contribution_facts.c.filing_id == filing_id)
            )).mappings().first()
            tag = (await session.execute(
                select(principal_employer_tags).where(principal_employer_tags.c.filing_id == filing_id)
            )).mappings().first()
            return fact, tag

    fact, tag = asyncio.run(get_facts())
    assert fact is not None
    assert fact["paid_at"] is not None
    assert fact["trrn"] == trrn
    assert fact["total_paise"] == 60000
    assert tag is not None
    assert tag["paid"] is True

    # Verify contribution monitoring endpoint
    response = client.get("/api/v1/monitoring/contributions", headers=hdr("fo.rpfc1"))
    assert response.status_code == 200
    totals = response.json()["data"]["totals"]
    assert totals["returns_filed"] == 1
    assert totals["amount_paid_paise"] == 60000
    assert totals["pending_payment"] == 0


def test_contribution_facts_payment_before_validation_and_submission(ctx):
    """Lead 6: PaymentConfirmed.v1 (CHALLAN) arrives before both ECRValidated.v1 and ECRSubmitted.v1."""
    client, deliver = ctx
    now = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)
    filing_id = "F-ORDER-002"
    trrn = "TRRN-ORDER-002"

    # 1. PaymentConfirmed arrives FIRST of all events
    confirmed(deliver, trrn, "CHALLAN", at=now + timedelta(minutes=5))

    # 2. ECRValidated arrives second
    deliver("ECRValidated.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0002",
                                "wage_month": "2026-09", "member_count": 10},
            occurred_at=now)

    # 3. PrincipalEmployerTagged arrives third
    deliver("PrincipalEmployerTagged.v1", {
        "filing_id": filing_id, "principal_establishment_id": "EST-PRINCIPAL-002",
        "work_order_ref": "WO-002", "contractor_establishment_id": "EST-DEMO-0002",
        "wage_month": "2026-09", "members": 10, "epf_wages_paise": 1000000,
        "contribution_paise": 120000, "paid": False,
    }, occurred_at=now + timedelta(minutes=1))

    # 4. ECRSubmitted arrives fourth
    deliver("ECRSubmitted.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0002",
                                "trrn": trrn, "total_paise": 120000, "rule_version": "demo"},
            occurred_at=now + timedelta(minutes=2))

    # 5. ContributionPosted arrives fifth
    deliver("ContributionPosted.v1", {"filing_id": filing_id, "wage_month": "2026-09",
                                      "establishment_id": "EST-DEMO-0002", "journal_id": "J-002",
                                      "payment_id": "P-002", "postings": []},
            occurred_at=now + timedelta(minutes=6))

    async def get_facts():
        async with db.sessions()() as session:
            fact = (await session.execute(
                select(contribution_facts).where(contribution_facts.c.filing_id == filing_id)
            )).mappings().first()
            tag = (await session.execute(
                select(principal_employer_tags).where(principal_employer_tags.c.filing_id == filing_id)
            )).mappings().first()
            return fact, tag

    fact, tag = asyncio.run(get_facts())
    assert fact is not None
    assert fact["paid_at"] is not None
    assert fact["posted_at"] is not None
    assert fact["trrn"] == trrn
    assert fact["wage_month"] == "2026-09"
    assert fact["total_paise"] == 120000
    assert tag is not None
    assert tag["paid"] is True

    response = client.get("/api/v1/monitoring/contributions", headers=hdr("fo.rpfc1"))
    assert response.status_code == 200
    totals = response.json()["data"]["totals"]
    assert totals["returns_filed"] == 1
    assert totals["amount_paid_paise"] == 120000
    assert totals["posted"] == 1
    assert totals["pending_payment"] == 0
