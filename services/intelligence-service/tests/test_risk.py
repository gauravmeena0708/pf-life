"""intelligence-service: advisory risk rules, shared-device context and human review."""
import asyncio
import importlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/intel.db")
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
            from epfo_persistence.policy import policy_metadata
            await c.run_sync(policy_metadata.create_all)
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="intelligence-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))
    start = datetime.now(UTC) - timedelta(hours=2)

    def security(subject, event_type, device="dev-aaaaaaaa", minutes=0):
        from app.api.routes import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": "SecurityEventRecorded.v1", "correlation_id": str(uuid.uuid4()),
                 "occurred_at": (start + timedelta(minutes=minutes)).isoformat(),
                 "payload": {"subject": subject, "event_type": event_type, "device_fingerprint_hash": device}}
        asyncio.run(apply_once(db.sessions(), event, dispatch))
        return event["event_id"]

    def raised():
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text("SELECT payload FROM outbox WHERE event_type='RiskSignalRaised.v1'"))).all()
        return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for (p,) in asyncio.run(run())]
    yield TestClient(application, raise_server_exceptions=False), security, raised
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(stakeholder, subject="caiu-1"):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "intelligence-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_new_device_contact_change_claim_raises_one_advisory_signal(ctx):
    client, security, raised = ctx
    login = security("m-1", "LOGIN_NEW_DEVICE", minutes=0)
    change = security("m-1", "CONTACT_DETAILS_CHANGED", minutes=5)
    assert raised() == []                                         # two steps are not the pattern
    claim = security("m-1", "CLAIM_CREATED", minutes=10)
    security("m-1", "CLAIM_CREATED", minutes=11)                  # a second claim does not add a second signal
    [signal] = raised()
    assert signal["detection_type"] == "NEW_DEVICE_CONTACT_CHANGE_CLAIM" and signal["evidence_refs"] == [login, change, claim]
    assert signal["subject_ref"] == "m-1" and "take no action on this alone" in signal["explanation"]


def test_order_matters_and_old_logins_do_not_count(ctx):
    _, security, raised = ctx
    security("m-2", "CONTACT_DETAILS_CHANGED", minutes=0)
    security("m-2", "LOGIN_NEW_DEVICE", minutes=5)
    security("m-2", "CLAIM_CREATED", minutes=10)
    assert raised() == []


def test_shared_device_alone_is_context_not_a_signal(ctx):
    client, security, raised = ctx
    for i in range(4):                                            # four members at one Common Service Centre kiosk
        security(f"csc-{i}", "LOGIN_NEW_DEVICE", device="kiosk-00000001", minutes=i)
        security(f"csc-{i}", "CLAIM_CREATED", device="kiosk-00000001", minutes=i + 1)
    assert raised() == []
    d = client.get("/api/v1/caiu/synthetic-risk-signals", headers=hdr("ho.caiu")).json()["data"]
    assert d["signals"] == [] and d["shared_devices_not_signals"][0]["subjects"] == 4
    assert "not evidence of fraud" in d["shared_devices_not_signals"][0]["note"]


def test_signal_on_shared_device_carries_the_context_for_the_reviewer(ctx):
    client, security, raised = ctx
    for i in range(3):
        security(f"csc-{i}", "LOGIN", device="kiosk-00000002", minutes=i)
    security("m-3", "LOGIN_NEW_DEVICE", device="kiosk-00000002", minutes=10)
    security("m-3", "CONTACT_DETAILS_CHANGED", device="kiosk-00000002", minutes=11)
    security("m-3", "CLAIM_CREATED", device="kiosk-00000002", minutes=12)
    [s] = client.get("/api/v1/caiu/synthetic-risk-signals", headers=hdr("ho.caiu")).json()["data"]["signals"]
    assert s["context"]["shared_device"] is True and s["advisory_only"] is True


def test_review_outcomes_and_no_automatic_action(ctx):
    client, security, raised = ctx
    security("m-4", "MEMBER_SECURITY_REPORT")
    [s] = raised()
    url = f"/api/v1/caiu/synthetic-risk-signals/{s['signal_id']}/reviews"
    assert client.post(url, json={"outcome": "guilty", "note": "not a valid outcome"}, headers=hdr("ho.caiu")).status_code == 422
    assert client.post(url, json={"outcome": "benign", "note": "ok"}, headers=hdr("ho.caiu")).status_code == 400   # note too short
    r = client.post(url, json={"outcome": "needs-more-evidence", "note": "Call the member on the old number"}, headers=hdr("ho.caiu"))
    assert r.status_code == 200 and r.json()["data"]["status"] == "NEEDS_MORE_EVIDENCE" and r.json()["data"]["automatic_actions"] == []
    r = client.post(url, json={"outcome": "benign", "note": "Member confirmed a new phone"}, headers=hdr("ho.caiu"))
    assert r.json()["data"]["status"] == "BENIGN"
    assert client.post(url, json={"outcome": "confirmed", "note": "changing my mind later"}, headers=hdr("ho.caiu")).status_code == 409
    assert client.get("/api/v1/caiu/synthetic-risk-signals", headers=hdr("member")).status_code == 403


def test_reviewed_evidence_does_not_raise_a_second_signal(ctx):
    client, security, raised = ctx
    security("m-5", "LOGIN_NEW_DEVICE", minutes=0)
    security("m-5", "CONTACT_DETAILS_CHANGED", minutes=1)
    security("m-5", "CLAIM_CREATED", minutes=2)
    [s] = raised()
    client.post(f"/api/v1/caiu/synthetic-risk-signals/{s['signal_id']}/reviews",
                json={"outcome": "benign", "note": "Member confirmed a new phone"}, headers=hdr("ho.caiu"))
    security("m-5", "LOGIN", minutes=30)
    security("m-5", "CLAIM_CREATED", minutes=31)          # a later claim, same 24 hours, nothing new happened
    assert len(raised()) == 1
    security("m-5", "LOGIN_NEW_DEVICE", minutes=40)       # a genuinely new pattern still raises
    security("m-5", "CONTACT_DETAILS_CHANGED", minutes=41)
    security("m-5", "CLAIM_CREATED", minutes=42)
    assert len(raised()) == 2


def test_steps_from_different_devices_do_not_combine(ctx):
    _, security, raised = ctx
    security("m-6", "LOGIN_NEW_DEVICE", device="dev-phone-0001", minutes=0)
    security("m-6", "CONTACT_DETAILS_CHANGED", device="dev-laptop-001", minutes=1)
    security("m-6", "CLAIM_CREATED", device="dev-phone-0001", minutes=2)
    assert raised() == []
