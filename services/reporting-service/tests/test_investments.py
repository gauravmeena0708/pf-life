"""Synthetic fund feed and governance aggregates."""
import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.api.investment_routes import feed_signature
from tests.test_read_models import ctx, hdr


def position(manager="Manager A", fund="EPF", as_of="2026-09-30", holdings=None):
    body = {"fund_manager": manager, "fund": fund, "as_of": as_of,
            "holdings": holdings or [{"isin": "IN0020260001", "asset_class": "GOVT_SECURITIES",
                                      "book_value_paise": 50, "market_value_paise": 50},
                                     {"isin": "INE0000A0001", "asset_class": "DEBT",
                                      "book_value_paise": 50, "market_value_paise": 50}]}
    body["signature"] = feed_signature(body)
    return body


def test_signed_feed_replacement_and_investment_flags(ctx):
    client, _ = ctx
    path = "/api/v1/integrations/fund-managers/positions"
    body = position()
    assert client.post(path, json=body, headers=hdr("ext.fund_manager")).status_code == 201
    bad = {**body, "signature": "0" * 64}
    response = client.post(path, json=bad, headers=hdr("ext.fund_manager"))
    assert response.status_code == 401 and response.json()["type"] == "/problems/bad-signature"
    malformed = {**body, "fund": "OTHER"}
    assert client.post(path, json=malformed, headers=hdr("ext.fund_manager")).status_code == 400
    replacement = position(holdings=[{"isin": "INE0000A0001", "asset_class": "DEBT",
                                       "book_value_paise": 70, "market_value_paise": 70},
                                      {"isin": "INF000000001", "asset_class": "EQUITY",
                                       "book_value_paise": 30, "market_value_paise": 30}])
    assert client.post(path, json=replacement, headers=hdr("ext.fund_manager")).status_code == 200
    from app.infra.db import sessions
    from app.infra.models import Outbox
    from sqlalchemy import select
    async def events():
        async with sessions()() as session:
            return (await session.execute(select(Outbox).where(
                Outbox.event_type == "FundPositionsReceived.v1"))).scalars().all()
    evs = asyncio.run(events())
    assert len(evs) == 2
    def get_payload(ev):
        raw = ev.payload if isinstance(ev.payload, dict) else json.loads(ev.payload)
        return raw.get("envelope", {}).get("payload", raw)
    assert get_payload(evs[0])["by_asset_class"] == [
        {"asset_class": "DEBT", "book_value_paise": 50},
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 50},
    ]
    assert get_payload(evs[1])["by_asset_class"] == [
        {"asset_class": "DEBT", "book_value_paise": 70},
        {"asset_class": "EQUITY", "book_value_paise": 30},
    ]
    data = client.get("/api/v1/ho/finance/investments?as_of=2026-10-01", headers=hdr("gov.fiac")).json()["data"]
    fund = data["funds"][0]
    classes = {item["asset_class"]: item for item in fund["asset_classes"]}
    assert fund["totals"]["market_value_paise"] == 100
    assert classes["DEBT"]["share_pct"] == 70.0 and classes["DEBT"]["flag"] == "ABOVE"
    assert classes["GOVT_SECURITIES"]["flag"] == "BELOW"
    assert data["fund_managers"] == ["Manager A"]
    assert client.get("/api/v1/ho/finance/investments?as_of=2026-09-29", headers=hdr("ho.fa_cao")).json()["data"]["funds"] == []
    newer = position(as_of="2026-10-02", holdings=[{"isin": "IN0020260001",
                                                   "asset_class": "GOVT_SECURITIES", "book_value_paise": 200,
                                                   "market_value_paise": 200}])
    assert client.post(path, json=newer, headers=hdr("ext.fund_manager")).status_code == 201
    latest = client.get("/api/v1/ho/finance/investments?as_of=2026-10-03",
                        headers=hdr("ho.investment")).json()["data"]
    assert latest["totals"]["market_value_paise"] == 200


def test_seed_idempotent_and_board_packs_are_aggregate(ctx, tmp_path, monkeypatch):
    client, deliver = ctx
    from app import seed
    source = {"fund_positions": {"as_of": "2026-09-30", "positions": [
        {"fund_manager": "Manager B", "fund": "EPS", "holdings": position()["holdings"]}]}}
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(seed, "SEED_FILE", str(path))
    asyncio.run(seed.main())
    asyncio.run(seed.main())
    assert client.get("/api/v1/ho/finance/investments?as_of=2026-09-30", headers=hdr("ho.investment")).json()["data"]["totals"]["market_value_paise"] == 100
    now = datetime.now(UTC)
    deliver("ClaimSubmitted.v1", {"claim_id": "SECRET-CLAIM", "office_id": "SECRET-OFFICE",
                                  "form_type": "19", "amount_paise": 100, "route": "AUTO"}, occurred_at=now - timedelta(days=3))
    deliver("ClaimDecisionRecorded.v1", {"claim_id": "SECRET-CLAIM", "decision": "APPROVED"})
    deliver("PaymentConfirmed.v1", {"payment_id": "PAY", "purpose": "CLAIM_SETTLEMENT",
                                    "reference_id": "SECRET-CLAIM", "amount_paise": 100})
    deliver("GrievanceRegistered.v1", {"grievance_id": "SECRET-GRIEVANCE", "office_id": "SECRET-OFFICE",
                                        "category": "KYC"}, occurred_at=now - timedelta(days=2))
    for meeting, role in (("CBT", "gov.cbt"), ("EC", "gov.ec"), ("FIAC", "gov.fiac")):
        response = client.get(f"/api/v1/governance/board-packs?meeting={meeting}", headers=hdr(role))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert set(data["sections"]) == {"contributions", "claims", "grievances", "investments"}
        assert ("pattern_flags" in data["sections"]["investments"]) == (meeting == "FIAC")
        assert "SECRET-" not in json.dumps(data) and "Manager B" not in json.dumps(data)
    from app.infra.db import sessions
    from app.infra.models import AuditLocal
    from sqlalchemy import select
    async def audits():
        async with sessions()() as session:
            return (await session.execute(select(AuditLocal))).scalars().all()
    assert len(asyncio.run(audits())) == 3


def test_wrong_roles_get_403(ctx):
    client, _ = ctx
    assert client.post("/api/v1/integrations/fund-managers/positions", json=position(),
                       headers=hdr("member")).status_code == 403
    assert client.get("/api/v1/ho/finance/investments", headers=hdr("member")).status_code == 403
    assert client.get("/api/v1/governance/board-packs?meeting=CBT", headers=hdr("member")).status_code == 403
