"""employer-service API tests on SQLite with real routes and real signed internal tokens."""
import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

SEED = json.load(open(Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"))
SUBJECTS = SEED["keycloak_subjects"]
OWNER, PREPARER, SIGNATORY = SUBJECTS["emp-owner"], SUBJECTS["emp-preparer"], SUBJECTS["emp-signatory"]
EST = SEED["establishment"]["establishment_id"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/employer.db")
    monkeypatch.setenv("SEED_FILE", str(Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"))
    import importlib

    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base
    from app.infra.tables import metadata

    async def setup():
        async with db.engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(metadata.create_all)
        from app import seed
        seed.SEED_FILE = os.environ["SEED_FILE"]
        await seed.main()
    asyncio.run(setup())

    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="employer-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def outbox_events():
        async def q():
            async with db.engine().connect() as c:
                return [r[0] for r in (await c.execute(text("SELECT event_type FROM outbox"))).all()]
        return asyncio.run(q())
    client = TestClient(application, raise_server_exceptions=os.environ.get("RAISE") == "1")
    client.outbox_events = outbox_events
    yield client
    monkeypatch.undo()          # restore DATABASE_URL etc., then rebuild settings from the real environment
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def token(subject, stakeholder, grants=(), establishment=EST, step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "employer-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
              "grants": list(grants)}
    if establishment:
        claims["establishment_id"] = establishment
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


OWNER_GRANTS = ["establishment.manage", "operators.manage", "signatories.manage"]


def owner(step_up=None):
    return token(OWNER, "employer.owner", OWNER_GRANTS, step_up=step_up)


def test_verification_with_mock_registry_emits_event(api):
    bad = api.post("/api/v1/employers/registration-requests/REQ-DEMO-0001/verification-evidence",
                   json={"pan": "ZZZPZ9999Z"}, headers=owner())
    assert bad.status_code == 200 and bad.json()["data"]["state"] == "REJECTED" and bad.json()["data"]["fix"]
    ok = api.post("/api/v1/employers/registration-requests/REQ-DEMO-0001/verification-evidence",
                  json={"pan": SEED["establishment"]["pan"], "gstin": SEED["establishment"]["gstin"]}, headers=owner())
    assert ok.status_code == 200 and ok.json()["data"]["state"] == "VERIFIED" and ok.json()["data"]["mock"] is True
    assert "EmployerVerified.v1" in api.outbox_events()
    again = api.post("/api/v1/employers/registration-requests/REQ-DEMO-0001/verification-evidence",
                     json={"pan": SEED["establishment"]["pan"]}, headers=owner())
    assert again.status_code == 409
    me = api.get("/api/v1/employers/me", headers=owner())
    assert me.json()["data"]["status"] == "VERIFIED"


def test_other_owner_cannot_see_request(api):
    r = api.get("/api/v1/employers/registration-requests/REQ-DEMO-0001",
                headers=token(str(uuid.uuid4()), "employer.owner", establishment=None))
    assert r.status_code == 404


def test_invite_needs_grant_and_step_up(api):
    body = {"username": "emp-preparer", "grants": ["ecr.prepare"]}
    no_step = api.post("/api/v1/employers/me/operators/invitations", json=body, headers=owner())
    assert no_step.status_code == 428
    wrong_step = api.post("/api/v1/employers/me/operators/invitations", json=body,
                          headers=owner({"action": "invite-operator", "resource_id": "EST-OTHER"}))
    assert wrong_step.status_code == 403
    not_owner = api.post("/api/v1/employers/me/operators/invitations", json=body,
                         headers=token(PREPARER, "employer.operator", ["ecr.prepare"],
                                       step_up={"action": "invite-operator", "resource_id": EST}))
    assert not_owner.status_code == 403
    ok = api.post("/api/v1/employers/me/operators/invitations", json=body,
                  headers=owner({"action": "invite-operator", "resource_id": EST}))
    assert ok.status_code == 201 and ok.json()["data"]["grants"] == ["ecr.prepare"]


def test_operator_cannot_receive_approval_rights(api):
    r = api.post("/api/v1/employers/me/operators/invitations",
                 json={"username": "emp-preparer", "grants": ["ecr.prepare", "ecr.approve"]},
                 headers=owner({"action": "invite-operator", "resource_id": EST}))
    assert r.status_code == 422 and "ecr.approve" in r.json()["title"]


def test_signatory_cannot_also_be_operator(api):
    step = {"action": "authorise-signatory", "resource_id": EST}
    assert api.post("/api/v1/employers/me/signatories/authorisations",
                    json={"username": "emp-signatory", "grants": ["ecr.approve", "ecr.submit"]},
                    headers=owner(step)).status_code == 201
    r = api.post("/api/v1/employers/me/operators/invitations",
                 json={"username": "emp-signatory", "grants": ["ecr.prepare"]},
                 headers=owner({"action": "invite-operator", "resource_id": EST}))
    assert r.status_code == 409 and r.json()["type"] == "/problems/separation-of-duties"


def test_no_self_grant(api):
    r = api.post("/api/v1/employers/me/signatories/authorisations",
                 json={"username": "emp-owner", "grants": ["ecr.approve"]},
                 headers=owner({"action": "authorise-signatory", "resource_id": EST}))
    assert r.status_code == 422


def test_revocation_returns_gateway_payload_and_grants_endpoint_updates(api):
    grant = api.post("/api/v1/employers/me/operators/invitations",
                     json={"username": "emp-preparer", "grants": ["ecr.prepare"]},
                     headers=owner({"action": "invite-operator", "resource_id": EST})).json()["data"]["grant_id"]
    gw = token("gateway", "system.gateway", establishment=None)
    before = api.get(f"/internal/actors/{PREPARER}/grants", headers=gw).json()["data"]["establishments"]
    assert before == [{"establishment_id": EST, "grants": ["ecr.prepare"]}]
    r = api.post(f"/api/v1/employers/me/operators/{grant}/revocations", json={"reason": "left the company"},
                 headers=owner({"action": "revoke-operator", "resource_id": grant}))
    assert r.status_code == 200
    rev = r.json()["data"]["revocation"]
    assert rev == {"subject": PREPARER, "establishment_id": EST, "grant_id": grant, "scope": "grant"}
    assert "EmployerOperatorRevoked.v1" in api.outbox_events()
    assert api.get(f"/internal/actors/{PREPARER}/grants", headers=gw).json()["data"]["establishments"] == []


def test_internal_grants_endpoint_is_gateway_only(api):
    assert api.get(f"/internal/actors/{OWNER}/grants", headers=owner()).status_code == 403


def test_public_search_minimal_fields(api):
    r = api.get("/api/v1/public/establishments", params={"query": "synthetic"}, headers=token("anonymous", "public", establishment=None))
    assert r.status_code == 200
    item = r.json()["data"][0]
    assert set(item) == {"establishment_id", "legal_name", "registration_number", "office_id", "pincode", "city",
                         "district", "establishment_type", "industry_group", "exemption_status", "status"}
    assert not {"pan", "gstin", "verified_at"} & set(item)  # public master fields only, never identifiers


def test_establishment_freeze_is_recorded_and_shown_to_the_employer(api):
    import asyncio
    import uuid

    import app.infra.db as db
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once
    payload = {"process": "establishment_freeze", "instance_id": "CASE-F1", "subject_ref": EST, "from_state": None, "to_state": "FROZEN",
               "operation": "freeze", "title": "Freeze of an establishment", "terminal": False, "visible_to_member": False,
               "actor_subject": "rpfc", "actor_role": "zo.rpfc1", "data": {"category": "B", "order_ref": "ZO/FIA/7", "reason": "Ghost members"}}

    def deliver(p):
        event = {"event_id": str(uuid.uuid4()), "event_type": "ProcessTransitioned.v1", "correlation_id": str(uuid.uuid4()), "payload": p}
        asyncio.run(apply_once(db.sessions(), event, dispatch))
    deliver(payload)
    me = api.get("/api/v1/employers/me", headers=owner()).json()["data"]
    assert me["frozen"] is True and me["freeze"]["order_ref"] == "ZO/FIA/7"
    deliver({**payload, "from_state": "FROZEN", "to_state": "ACTIVE", "operation": "defreeze", "terminal": True})
    assert api.get("/api/v1/employers/me", headers=owner()).json()["data"]["frozen"] is False
