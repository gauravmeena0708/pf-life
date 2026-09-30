"""audit-service: append-only hash chain, correlation trail and security-event intake."""
import asyncio
import importlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

SEED_FILE = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"
SEED = json.loads(SEED_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/audit.db")
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base
    from app.infra.tables import install_append_only, metadata
    from app.infra.oversight_tables import oversight_metadata

    async def setup():
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            await c.run_sync(metadata.create_all)
            await c.run_sync(oversight_metadata.create_all)
            await c.run_sync(install_append_only)
        from app import seed
        monkeypatch.setattr(seed, "SEED_FILE", str(SEED_FILE))
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="audit-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def deliver(event_type, correlation_id="c-1", **payload):
        from app.api.routes import record
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "producer": "claim-service",
                 "aggregate_type": "claim", "aggregate_id": "CLM-1", "occurred_at": datetime.now(UTC).isoformat(),
                 "correlation_id": correlation_id, "payload": payload}
        return asyncio.run(apply_once(db.sessions(), event, record)), event

    def sql(statement):
        async def run():
            async with db.engine().begin() as c:
                await c.execute(text(statement))
        asyncio.run(run())
    yield TestClient(application, raise_server_exceptions=False), deliver, sql
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(stakeholder, subject="x", step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "audit-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_events_form_a_verified_chain_and_redelivery_is_ignored(ctx):
    client, deliver, _ = ctx
    deliver("ClaimSubmitted.v1", claim_id="CLM-1")
    applied, event = deliver("CaseDecisionSubmitted.v1", claim_id="CLM-1")
    from app.api.routes import record
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), event, record)) is False
    d = client.get("/api/v1/audit/events", headers=hdr("ho.audit")).json()["data"]
    assert [i["event_type"] for i in d["items"]] == ["ClaimSubmitted.v1", "CaseDecisionSubmitted.v1"]
    assert d["items"][1]["prev_hash"] == d["items"][0]["hash"]
    assert d["chain"] == {"valid": True, "checked": 2, "head": d["items"][1]["hash"]}


def test_log_rejects_update_and_delete(ctx):
    _, deliver, sql = ctx
    deliver("ClaimSubmitted.v1", claim_id="CLM-1")
    with pytest.raises(Exception, match="append-only"):
        sql("UPDATE audit_log SET event_type='Tampered'")
    with pytest.raises(Exception, match="append-only"):
        sql("DELETE FROM audit_log")


def test_tampering_around_the_triggers_is_detected(ctx):
    client, deliver, sql = ctx
    deliver("ClaimSubmitted.v1", claim_id="CLM-1")
    deliver("ClaimDecisionRecorded.v1", claim_id="CLM-1", decision="APPROVED")
    sql("DROP TRIGGER audit_log_no_update")                         # an attacker with DDL rights
    sql("UPDATE audit_log SET payload='{\"claim_id\": \"CLM-1\", \"decision\": \"REJECTED\"}' WHERE seq=2")
    chain = client.get("/api/v1/audit/events", headers=hdr("ho.audit")).json()["data"]["chain"]
    assert chain["valid"] is False and chain["broken_at_seq"] == 2


def test_correlation_trail_and_access(ctx):
    client, deliver, _ = ctx
    deliver("ClaimSubmitted.v1", correlation_id="journey-b", claim_id="CLM-1")
    deliver("PaymentInstructed.v1", correlation_id="journey-b", claim_id="CLM-1")
    deliver("ECRSubmitted.v1", correlation_id="other")
    r = client.get("/api/v1/audit/correlations/journey-b", headers=hdr("gov.cag"))
    assert [i["event_type"] for i in r.json()["data"]["items"]] == ["ClaimSubmitted.v1", "PaymentInstructed.v1"]
    assert client.get("/api/v1/audit/events", headers=hdr("member")).status_code == 403


def test_security_event_intake_publishes_event(ctx):
    client, *_ = ctx
    body = {"subject": "member-1", "event_type": "LOGIN_NEW_DEVICE", "device_fingerprint_hash": "abcdef0123456789"}
    assert client.post("/api/v1/internal/security-events", json=body, headers=hdr("member")).status_code == 403
    r = client.post("/api/v1/internal/security-events", json=body, headers=hdr("system.gateway", "gateway"))
    assert r.status_code == 202
    bad = client.post("/api/v1/internal/security-events", json={**body, "event_type": "ANYTHING"},
                      headers=hdr("system.gateway", "gateway"))
    assert bad.status_code == 422
