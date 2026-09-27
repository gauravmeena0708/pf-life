"""grievance-service tests on SQLite: registration and routing, office confidentiality, replies,
evidence, documents, escalation, resolution with step-up and reopening."""
import asyncio
import base64
import importlib
import json
import time
import uuid
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

ROOT = Path(__file__).resolve().parents[3]
SEED = json.load(open(ROOT / "scripts" / "seed" / "synthetic.json"))
S = SEED["keycloak_subjects"]
MEMBER_A, MEMBER_B, PRO, ZO, APFC = S["member-a"], S["member-b"], S["ro-pro"], S["zo-acc"], S["ro-apfc"]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/grievance.db")
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
        seed.SEED_FILE = str(ROOT / "scripts" / "seed" / "synthetic.json")
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="grievance-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def events(event_type):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text("SELECT payload FROM outbox WHERE event_type=:t ORDER BY id"), {"t": event_type})).all()
        return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for (p,) in asyncio.run(run())]
    yield TestClient(application, raise_server_exceptions=False), events
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "grievance-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def member(subject=MEMBER_A):
    return hdr(subject, "member")


def register(client, **kw):
    body = {"category": "CLAIM_DELAY", "subject": "Advance not received",
            "description": "My advance claim was approved but the money has not reached my bank.",
            "linked_claim_id": "CLM-0001", **kw}
    return client.post("/api/v1/members/me/grievances", json=body, headers=member())


def gid_of(r):
    return r.json()["data"]["grievance_id"]


def test_register_routes_to_home_office_and_emits_event(ctx):
    client, events = ctx
    r = register(client)
    assert r.status_code == 201, r.json()
    d = r.json()["data"]
    assert d["state"] == "ROUTED" and d["office_id"] == "RO-DEMO-01" and d["tier"] == "RO"
    assert events("GrievanceRegistered.v1")[0]["linked_claim_id"] == "CLM-0001"
    assert events("NotificationRequested.v1")[0]["template"] == "GRIEVANCE_REGISTERED"


def test_other_member_other_office_and_wrong_role_cannot_read(ctx):
    client, _ = ctx
    gid = gid_of(register(client))
    assert client.get(f"/api/v1/grievances/{gid}", headers=member(MEMBER_B)).status_code == 404
    stranger_pro = hdr(str(uuid.uuid4()), "fo.pro")                           # a PRO of another (unseeded) office
    r = client.get(f"/api/v1/grievances/{gid}", headers=stranger_pro)
    assert r.status_code == 404 and "advance" not in r.text.lower()
    assert client.get(f"/api/v1/grievances/{gid}", headers=hdr(APFC, "fo.apfc")).status_code == 403
    assert client.get(f"/api/v1/grievances/{gid}", headers=hdr(PRO, "fo.pro")).status_code == 200
    assert client.get(f"/api/v1/grievances/{gid}", headers=hdr(ZO, "zo.acc")).status_code == 200   # zone supervises


def test_reply_takes_up_evidence_and_document(ctx):
    client, _ = ctx
    gid = gid_of(register(client))
    r = client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "We are checking with the cash section."},
                    headers=hdr(PRO, "fo.pro"))
    assert r.status_code == 201 and r.json()["data"]["state"] == "IN_PROGRESS"
    r = client.post(f"/api/v1/grievances/{gid}/evidence-links", json={"evidence_refs": ["CLM-0001", "PAY-CLM-0001-1"],
                                                                       "note": "Bank returned the first payment"},
                    headers=hdr(PRO, "fo.pro"))
    assert r.status_code == 201 and r.json()["data"]["entries"][-1]["evidence_refs"] == ["CLM-0001", "PAY-CLM-0001-1"]
    doc = base64.b64encode(b"SYNTHETIC bank statement - no real data").decode()
    r = client.post(f"/api/v1/grievances/{gid}/documents", json={"filename": "statement.txt", "content_type": "text/plain",
                                                                 "content_base64": doc}, headers=member())
    assert r.status_code == 201 and len(r.json()["data"]["sha256"]) == 64
    bad = client.post(f"/api/v1/grievances/{gid}/documents", json={"filename": "x.exe", "content_type": "application/x-msdownload",
                                                                   "content_base64": doc}, headers=member())
    assert bad.status_code == 415


def test_escalation_moves_tier_and_only_that_tier_resolves(ctx):
    client, events = ctx
    gid = gid_of(register(client))
    r = client.post(f"/api/v1/grievances/{gid}/escalations", json={"reason": "No reply for two weeks"}, headers=member())
    assert r.status_code == 200 and r.json()["data"]["tier"] == "ZO" and r.json()["data"]["state"] == "ESCALATED"
    assert events("GrievanceEscalated.v1")[0] == {"grievance_id": gid, "from_tier": "RO", "to_tier": "ZO", "office_id": "ZO-DEMO-01"}
    pro_reply = client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "hello"}, headers=hdr(PRO, "fo.pro"))
    assert pro_reply.status_code == 403                                           # the RO no longer handles it
    r = client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "The zone is looking into it."}, headers=hdr(ZO, "zo.acc"))
    assert r.json()["data"]["state"] == "IN_PROGRESS"
    version = r.json()["data"]["version"]
    url = f"/api/v1/grievances/{gid}/resolution"
    body = {"resolution": "Payment re-issued and credited on 27 Sept."}
    assert client.post(url, json=body, headers=hdr(ZO, "zo.acc")).status_code == 428
    r = client.post(url, json=body, headers=hdr(ZO, "zo.acc", {"action": "resolve-grievance", "resource_id": gid,
                                                               "resource_version": version}))
    assert r.status_code == 200 and r.json()["data"]["state"] == "RESOLVED"
    assert events("GrievanceResolved.v1")[0]["tier"] == "ZO" and events("GrievanceResolved.v1")[0]["within_sla"] is True


def test_reopen_only_after_resolution(ctx):
    client, _ = ctx
    gid = gid_of(register(client))
    assert client.post(f"/api/v1/grievances/{gid}/reopen-requests", json={"reason": "Still not paid"},
                       headers=member()).status_code == 409
    client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "Checking"}, headers=hdr(PRO, "fo.pro"))
    v = client.get(f"/api/v1/grievances/{gid}", headers=member()).json()["data"]["version"]
    client.post(f"/api/v1/grievances/{gid}/resolution", json={"resolution": "Paid on 27 Sept by NEFT."},
                headers=hdr(PRO, "fo.pro", {"action": "resolve-grievance", "resource_id": gid, "resource_version": v}))
    r = client.post(f"/api/v1/grievances/{gid}/reopen-requests", json={"reason": "Still not paid"}, headers=member())
    assert r.status_code == 200 and r.json()["data"]["state"] == "REOPEN_REQUESTED"


def test_top_tier_cannot_escalate_further(ctx):
    client, _ = ctx
    gid = gid_of(register(client))
    client.post(f"/api/v1/grievances/{gid}/escalations", json={"reason": "No reply"}, headers=member())
    client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "Zone here"}, headers=hdr(ZO, "zo.acc"))
    assert client.post(f"/api/v1/grievances/{gid}/escalations", json={"reason": "Still no answer"},
                       headers=member()).json()["data"]["tier"] == "HO"
    client_state = client.get(f"/api/v1/grievances/{gid}", headers=member()).json()["data"]
    assert client_state["state"] == "ESCALATED"
    assert client.post(f"/api/v1/grievances/{gid}/escalations", json={"reason": "Again please"},
                       headers=member()).status_code == 409


def test_member_list_is_own_only(ctx):
    client, _ = ctx
    register(client)
    assert len(client.get("/api/v1/members/me/grievances", headers=member()).json()["data"]) == 1
    assert client.get("/api/v1/members/me/grievances", headers=member(MEMBER_B)).json()["data"] == []
