"""reporting-service: grievance metrics built from events only."""
import asyncio
import importlib
import time
import uuid

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
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            await c.run_sync(metadata.create_all)
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="reporting-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def deliver(event_type, payload):
        from app.api.routes import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "occurred_at": "2026-09-27T10:00:00Z",
                 "correlation_id": str(uuid.uuid4()), "payload": payload}
        return asyncio.run(apply_once(db.sessions(), event, dispatch)), event
    yield TestClient(application, raise_server_exceptions=False), deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(stakeholder):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "reporting-service", "sub": "x", "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_grievance_metrics_from_events(ctx):
    client, deliver = ctx
    for gid, cat in (("G1", "CLAIM_DELAY"), ("G2", "CLAIM_DELAY"), ("G3", "KYC")):
        deliver("GrievanceRegistered.v1", {"grievance_id": gid, "category": cat, "office_id": "RO-DEMO-01", "linked_claim_id": ""})
    _, dup = deliver("GrievanceEscalated.v1", {"grievance_id": "G1", "from_tier": "RO", "to_tier": "ZO", "office_id": "ZO-DEMO-01"})
    deliver("GrievanceResolved.v1", {"grievance_id": "G1", "office_id": "RO-DEMO-01", "tier": "ZO", "within_sla": True})
    deliver("GrievanceResolved.v1", {"grievance_id": "G3", "office_id": "RO-DEMO-01", "tier": "RO", "within_sla": False})
    import app.infra.db as db
    from app.api.routes import dispatch
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), dup, dispatch)) is False     # redelivery counts once
    r = client.get("/api/v1/monitoring/grievances", headers=hdr("zo.acc"))
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["offices"] == [{"office_id": "RO-DEMO-01", "registered": 3, "resolved": 2, "pending": 1, "escalations": 1,
                             "resolved_within_sla_pct": 50}]
    assert d["pending_by_tier"] == {"RO": 1} and d["by_category"] == {"CLAIM_DELAY": 2, "KYC": 1}


def test_members_cannot_see_monitoring(ctx):
    client, _ = ctx
    assert client.get("/api/v1/monitoring/grievances", headers=hdr("member")).status_code == 403


def test_a_published_rule_set_reaches_reporting(ctx):
    """P2.27: reporting looked rules up (investment pattern bands) but never received a published version — always the
    baseline. It now keeps the published versions like every other service."""
    import copy
    from datetime import date
    import app.infra.db as db
    from epfo_persistence.policy import baseline, policy_metadata, rules_on
    _, deliver = ctx

    async def tables():
        async with db.engine().begin() as c:
            await c.run_sync(policy_metadata.create_all)
    asyncio.run(tables())
    doc = copy.deepcopy(baseline())
    doc.update(rule_version="demo-rules-2026.5", effective_from="2026-10-01")
    deliver("PolicyPublished.v1", {"version_id": "POL-5", "rule_version": "demo-rules-2026.5", "effective_from": "2026-10-01",
                                   "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc})

    async def version():
        async with db.sessions()() as s:
            return (await rules_on(s, date(2026, 10, 2)))["rule_version"]
    assert asyncio.run(version()) == "demo-rules-2026.5"
