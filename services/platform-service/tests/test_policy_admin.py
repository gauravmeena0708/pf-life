"""Policy administration: draft → checks and preview → submit → publish with maker-checker and step-up."""
import asyncio
import copy
import importlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

DRAFTER, APPROVER = "00000000-0000-4000-8000-000000000024", "00000000-0000-4000-8000-000000000014"
NEXT_MONTH = (datetime.now(UTC).date().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/platform.db")
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
        from app import seed
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="platform-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def events():
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text("SELECT payload FROM outbox WHERE event_type='PolicyPublished.v1'"))).all()
        return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for (p,) in asyncio.run(run())]
    yield TestClient(application, raise_server_exceptions=__import__("os").environ.get("RAISE") == "1"), events
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None, **extra):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "platform-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID}), **extra}


def drafter(**extra):
    return hdr(DRAFTER, "ho.acc_hq", **extra)


def baseline_doc(client):
    return client.get("/api/v1/ho/config/rule-sets/POL-BASELINE", headers=drafter()).json()["data"]["document"]


def draft(client, change=None, name="demo-rules-2026.2", effective=NEXT_MONTH):
    doc = copy.deepcopy(baseline_doc(client))
    (change or (lambda d: d["contribution"].update(eps_wage_ceiling_paise=2500000, edli_wage_ceiling_paise=2500000)))(doc)
    return client.post("/api/v1/ho/config/rule-sets", json={"base_version_id": "POL-BASELINE", "rule_version": name,
                       "effective_from": effective, "change_note": "Wage ceiling raised to ₹25,000", "document": doc}, headers=drafter())


def test_ceiling_change_shows_changes_and_worked_examples(ctx):
    client, _ = ctx
    r = draft(client)
    assert r.status_code == 201, r.json()
    d = r.json()["data"]
    assert d["status"] == "DRAFT" and d["checks"] == []
    paths = {c["path"]: (c["before"], c["after"]) for c in d["changes"]}
    assert paths["contribution.eps_wage_ceiling_paise"] == (1500000, 2500000)
    row = next(x for x in d["preview"]["contribution"] if x["monthly_wages"] == "₹20,000")
    assert row["before"]["employer_eps"] == "₹1,250" and row["after"]["employer_eps"] == "₹1,666"


def test_publish_needs_submission_different_person_and_step_up(ctx):
    client, events = ctx
    vid = draft(client).json()["data"]["version_id"]
    decide = f"/api/v1/ho/config/rule-sets/{vid}/decisions"
    body = {"decision": "APPROVE", "note": "Approved as per the notified ceiling"}
    step = {"action": "publish-policy", "resource_id": vid, "resource_version": 1}
    assert client.post(decide, json=body, headers=hdr(APPROVER, "ho.cpfc", step)).status_code == 409     # not submitted
    r = client.post(f"/api/v1/ho/config/rule-sets/{vid}/submissions", headers=drafter())
    assert r.status_code == 200 and r.json()["data"]["status"] == "SUBMITTED"
    step = {"action": "publish-policy", "resource_id": vid, "resource_version": 2}
    assert client.post(decide, json=body, headers=hdr(APPROVER, "ho.cpfc")).status_code == 428
    assert client.post(decide, json=body, headers=drafter()).status_code == 403                         # drafter role
    assert client.post(decide, json=body, headers=hdr(DRAFTER, "ho.cpfc", step)).status_code == 403      # same person
    r = client.post(decide, json=body, headers=hdr(APPROVER, "ho.cpfc", step))
    assert r.status_code == 200 and r.json()["data"]["status"] == "SCHEDULED"
    [event] = events()
    assert event["rule_version"] == "demo-rules-2026.2" and event["effective_from"] == NEXT_MONTH
    assert event["document"]["contribution"]["eps_wage_ceiling_paise"] == 2500000 and len(event["document_sha256"]) == 64
    listing = client.get("/api/v1/ho/config/rule-sets", headers=hdr(APPROVER, "ho.cpfc")).json()["data"]["items"]
    assert {i["rule_version"]: i["status"] for i in listing} == {"demo-rules-2026.2": "SCHEDULED", "demo-rules-2026.1": "IN_FORCE"}
    public = client.get("/api/v1/public/policy/current", headers=hdr("anonymous", "public")).json()["data"]
    assert public["contribution"]["eps_wage_ceiling_paise"] == 1500000 and public["scheduled"][0]["effective_from"] == NEXT_MONTH


def test_a_draft_that_fails_checks_cannot_be_submitted(ctx):
    client, _ = ctx
    bad = draft(client, change=lambda d: d["claims"]["approval_bands"][-1].update(upto_paise=10))
    assert bad.status_code == 201 and bad.json()["data"]["checks"]
    r = client.post(f"/api/v1/ho/config/rule-sets/{bad.json()['data']['version_id']}/submissions", headers=drafter())
    assert r.status_code == 422 and any("no upper limit" in p for p in r.json()["problems"])


def test_new_claim_type_per_type_matrix_and_auto_settlement_preview(ctx):
    client, _ = ctx

    def change(d):
        d["claims"]["types"]["ADVANCE_HOUSING"] = {
            "form_type": "31", "label": "Advance for building a house", "plain_rule": "Up to 90% of your balance after 5 years of service.",
            "requires_active_employment": True, "min_service_months": 60, "max_from": "total_balance", "max_pct_bp": 9000,
            "once_every_months": 120, "auto_settle_up_to_paise": None,
            "approval_bands": [{"upto_paise": None, "chain": ["fo.da_accounts", "fo.ao", "fo.apfc"]}]}
        d["claims"]["types"]["FINAL_SETTLEMENT"]["auto_settle_up_to_paise"] = None      # final settlements always reviewed
    d = draft(client, change=change, name="demo-rules-2026.3").json()["data"]
    assert d["checks"] == []
    rows = {(c["claim_type"], c["amount"]): c for c in d["preview"]["claims"]}
    assert rows[("ADVANCE_HOUSING", "₹20,000")] == {"claim_type": "ADVANCE_HOUSING", "amount": "₹20,000",
                                                    "before": "not offered", "after": "DA → AO → APFC"}
    assert rows[("FINAL_SETTLEMENT", "₹20,000")]["before"] == "automatic"
    assert rows[("FINAL_SETTLEMENT", "₹20,000")]["after"] == "DA → SS"
    assert ("ADVANCE_ILLNESS", "₹20,000") not in rows                                     # unchanged rows are not listed


def test_backdating_and_editing_rules(ctx):
    client, _ = ctx
    assert draft(client, effective="2020-01-01").status_code == 422
    d = draft(client).json()["data"]
    url = f"/api/v1/ho/config/rule-sets/{d['version_id']}"
    assert client.put(url, json={"change_note": "Ceiling raised to ₹25,000 (corrected)"}, headers=drafter()).status_code == 412
    r = client.put(url, json={"change_note": "Ceiling raised to ₹25,000 (corrected)"}, headers=drafter(**{"If-Match": "1"}))
    assert r.status_code == 200 and r.json()["data"]["version"] == 2
    assert client.get("/api/v1/ho/config/rule-sets", headers=hdr("x", "member")).status_code == 403


def test_an_earlier_version_cannot_be_published_under_a_scheduled_later_one(ctx):
    client, _ = ctx
    later = draft(client, name="demo-rules-2026.5", effective=(datetime.now(UTC).date() + timedelta(days=60)).isoformat()).json()["data"]
    client.post(f"/api/v1/ho/config/rule-sets/{later['version_id']}/submissions", headers=drafter())
    step = {"action": "publish-policy", "resource_id": later["version_id"], "resource_version": 2}
    assert client.post(f"/api/v1/ho/config/rule-sets/{later['version_id']}/decisions", json={"decision": "APPROVE",
                       "note": "Scheduled ceiling change"}, headers=hdr(APPROVER, "ho.cpfc", step)).status_code == 200
    earlier = draft(client, name="demo-rules-2026.4", effective=(datetime.now(UTC).date() + timedelta(days=5)).isoformat()).json()["data"]
    r = client.post(f"/api/v1/ho/config/rule-sets/{earlier['version_id']}/submissions", headers=drafter())
    assert r.status_code == 409 and r.json()["type"] == "/problems/later-version-scheduled"
