"""Tier-3 reporting projections consume synthetic events, with no service database joins."""
import asyncio
import importlib
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from tests.conftest import JWKS, KEY, KID


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/reporting.db")
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base
    from app.infra.tables import metadata

    async def setup():
        async with db.engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(metadata.create_all)

    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app()
    epfo_auth.configure(audience="reporting-service", jwks=epfo_auth.JwksCache("http://test", fetch=lambda _: JWKS))

    def deliver(event_type, payload, *, occurred_at=None):
        from app.api.routes import EVENT_PRODUCERS, dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type,
                 "producer": EVENT_PRODUCERS[event_type],
                 "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
                 "correlation_id": str(uuid.uuid4()), "payload": payload}
        assert asyncio.run(apply_once(db.sessions(), event, dispatch)) is True
        return event

    yield TestClient(app, raise_server_exceptions=False), deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(stakeholder, office_id=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "reporting-service", "sub": "test-subject",
              "stakeholder": stakeholder, "iat": now, "exp": now + 60,
              "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if office_id:
        claims["office_id"] = office_id
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def claim(deliver, claim_id, *, office="RO-DEMO-01", form="19", route="REVIEW", at=None):
    deliver("ClaimSubmitted.v1", {"claim_id": claim_id, "office_id": office, "form_type": form,
                                  "amount_paise": 10000, "route": route}, occurred_at=at)


def decision(deliver, claim_id, value, *, at=None):
    deliver("ClaimDecisionRecorded.v1", {"claim_id": claim_id, "decision": value}, occurred_at=at)


def confirmed(deliver, reference_id, purpose, *, at=None):
    return deliver("PaymentConfirmed.v1", {"payment_id": str(uuid.uuid4()), "purpose": purpose,
                                           "reference_id": reference_id, "amount_paise": 10000}, occurred_at=at)


def filing(deliver, filing_id, month, trrn, total):
    deliver("ECRValidated.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0001",
                                "wage_month": month, "member_count": 2})
    deliver("ECRSubmitted.v1", {"filing_id": filing_id, "establishment_id": "EST-DEMO-0001",
                                "trrn": trrn, "total_paise": total, "rule_version": "demo"})


def test_claim_lifecycle_and_redelivery(ctx):
    client, deliver = ctx
    start = datetime(2026, 9, 20, tzinfo=UTC)
    claim(deliver, "C1", route="AUTO", at=start)
    decision(deliver, "C1", "AUTO_APPROVED", at=start + timedelta(hours=1))
    returned = deliver("PaymentReturned.v1", {"payment_id": "P1", "purpose": "CLAIM_SETTLEMENT",
                                               "reference": "C1"}, occurred_at=start + timedelta(days=1))
    confirmed(deliver, "C1", "CLAIM_SETTLEMENT", at=start + timedelta(days=2))
    claim(deliver, "C2", form="10C", at=start)
    decision(deliver, "C2", "APPROVED", at=start + timedelta(days=1))
    confirmed(deliver, "C2", "CLAIM_SETTLEMENT", at=start + timedelta(days=4))
    claim(deliver, "C3", form="10C")
    claim(deliver, "C4", form="31")
    decision(deliver, "C4", "REJECTED")

    from app.api.routes import dispatch
    from epfo_persistence.consumer import apply_once
    import app.infra.db as db
    assert asyncio.run(apply_once(db.sessions(), returned, dispatch)) is False

    response = client.get("/api/v1/monitoring/claims", headers=hdr("fo.oic"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["totals"] == {"submitted": 4, "auto_approved": 1, "under_officer_review": 1,
                              "approved": 1, "rejected": 1, "settled": 2, "payment_returns": 1,
                              "median_days_to_settle": 3, "pending_by_form": {"10C": 1}}
    assert data["offices"][0]["office_id"] == "RO-DEMO-01"
    assert "ClaimSubmitted.v1" in data["source"] and data["as_of"].endswith("+00:00")
    fresh = client.get("/api/v1/monitoring/data-freshness", headers=hdr("ho.cpfc")).json()["data"]
    payment = next(source for source in fresh["sources"] if source["source"] == "payment-simulator")
    assert payment["events_seen"] == 3


def test_contribution_months_paid_and_pending(ctx):
    client, deliver = ctx
    filing(deliver, "F1", "2026-08", "TRRN-1", 120000)
    filing(deliver, "F2", "2026-08", "TRRN-2", 80000)
    filing(deliver, "F3", "2026-09", "TRRN-3", 50000)
    confirmed(deliver, "TRRN-1", "CHALLAN")
    deliver("ContributionPosted.v1", {"filing_id": "F1", "wage_month": "2026-08",
                                      "establishment_id": "EST-DEMO-0001", "journal_id": "J1",
                                      "payment_id": "P1", "postings": []})
    response = client.get("/api/v1/monitoring/contributions", headers=hdr("fo.rpfc1"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["wage_months"] == [
        {"wage_month": "2026-08", "returns_filed": 2, "amount_due_paise": 200000,
         "amount_paid_paise": 120000, "posted": 1, "pending_payment": 1},
        {"wage_month": "2026-09", "returns_filed": 1, "amount_due_paise": 50000,
         "amount_paid_paise": 0, "posted": 0, "pending_payment": 1},
    ]
    assert data["totals"]["amount_due_paise"] == 250000
    assert data["totals"]["pending_payment"] == 2


def test_freshness_uses_event_time_and_reports_stale(ctx):
    client, deliver = ctx
    now = datetime.now(UTC)
    deliver("RiskSignalRaised.v1", {"signal_id": "R1"}, occurred_at=now - timedelta(hours=2))
    deliver("ClaimSubmitted.v1", {"claim_id": "C1", "office_id": "RO-DEMO-01",
                                  "form_type": "19", "amount_paise": 100, "route": "AUTO"}, occurred_at=now)
    data = client.get("/api/v1/monitoring/data-freshness", headers=hdr("ho.cpfc")).json()["data"]
    sources = {row["source"]: row for row in data["sources"]}
    assert sources["intelligence-service"]["status"] == "stale"
    assert sources["intelligence-service"]["lag_seconds"] >= 7200
    assert sources["claim-service"]["status"] == "fresh"
    assert sources["claim-service"]["events_seen"] == 1


def test_public_statistics_suppresses_small_counts_and_ids(ctx):
    client, deliver = ctx
    claim(deliver, "C1")
    confirmed(deliver, "C1", "CLAIM_SETTLEMENT")
    deliver("GrievanceRegistered.v1", {"grievance_id": "G1", "office_id": "RO-DEMO-01",
                                        "category": "CLAIM_DELAY"})
    deliver("GrievanceResolved.v1", {"grievance_id": "G1", "office_id": "RO-DEMO-01",
                                      "tier": "RO", "within_sla": True})
    data = client.get("/api/v1/public/statistics", headers=hdr("public")).json()["data"]
    assert data["claims_settled"] is None and data["grievances_resolved"] is None
    assert data["contributions_posted_paise"] is None
    assert all(data["suppressed"].values())
    assert "RO-DEMO-01" not in str(data) and "office_id" not in str(data)
    assert "below 5" in data["note"]
    assert client.get("/api/v1/public/statistics", headers=hdr("gov.mole")).status_code == 200


def test_zone_dashboard_filters_to_seed_zone(ctx):
    client, deliver = ctx
    claim(deliver, "C1")
    claim(deliver, "C2", office="RO-OTHER")
    deliver("GrievanceRegistered.v1", {"grievance_id": "G1", "office_id": "RO-DEMO-01",
                                        "category": "KYC"})
    data = client.get("/api/v1/zo/dashboards", headers=hdr("zo.acc", "ZO-DEMO-01")).json()["data"]
    assert data["zone_id"] == "ZO-DEMO-01"
    assert data["claims"]["totals"]["submitted"] == 1
    assert [row["office_id"] for row in data["claims"]["offices"]] == ["RO-DEMO-01"]
    assert data["grievances"]["offices"][0]["pending"] == 1
    assert client.get("/api/v1/zo/dashboards", headers=hdr("zo.acc", "ZO-OTHER")).json()["data"]["claims"]["totals"]["submitted"] == 0


@pytest.mark.parametrize("path", [
    "/api/v1/monitoring/claims", "/api/v1/monitoring/contributions",
    "/api/v1/monitoring/data-freshness", "/api/v1/public/statistics", "/api/v1/zo/dashboards",
])
def test_wrong_stakeholder_gets_403(ctx, path):
    client, _ = ctx
    assert client.get(path, headers=hdr("member")).status_code == 403
