"""Phase 2, slice 8a: compliance cases (DA Compliance opens, the office searches), the published defaulter list, and
VISHWAS — the employer applies over open 14B demands (projected from contribution-service), the APFC decides, and an
approval raises one revised demand (DemandRaised.v1)."""
import asyncio
import importlib
import json
import time
import uuid
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

SEED = json.load(open(Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"))
S = SEED["keycloak_subjects"]
EST = SEED["establishment"]["establishment_id"]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/compliance.db")
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
        seed.SEED_FILE = str(Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json")
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    app = create_app()
    epfo_auth.configure(audience="compliance-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def deliver(event_type, payload):
        from app.infra.messaging import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "correlation_id": str(uuid.uuid4()), "payload": payload}
        asyncio.run(apply_once(db.sessions(), event, dispatch))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())
    yield TestClient(app, raise_server_exceptions=False), q, deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None, establishment=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "compliance-service", "sub": subject, "stakeholder": stakeholder, "iat": now, "exp": now + 60,
              "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if establishment:
        claims["establishment_id"] = establishment
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def demand(deliver, demand_id, kind="DAMAGES_14B", amount=1000000, state="OPEN"):
    deliver("DemandStateChanged.v1", {"demand_id": demand_id, "establishment_id": EST, "kind": kind, "trrn": "T1", "wage_month": "2026-06",
                                      "amount_paise": amount, "days_late": 90, "state": state, "working": "w"})


def test_cases_opened_searched_and_published(ctx):
    client, q, _ = ctx
    da = hdr(S["ro-da-compliance"], "fo.da_compliance")
    body = {"establishment_id": EST, "kind": "NON_PAYMENT", "wage_months": ["2026-07"], "amount_paise": 1152500,
            "note": "Return filed but not paid for July"}
    r = client.post("/api/v1/office/compliance/cases", json=body, headers=da)
    assert r.status_code == 201 and r.json()["data"]["legal_name"].startswith("Synthetic Textiles"), r.json()
    assert client.post("/api/v1/office/compliance/cases", json=body, headers=da).json()["type"] == "/problems/case-open"
    assert client.post("/api/v1/office/compliance/cases", json={**body, "wage_months": ["July"]}, headers=da).status_code == 422
    [c] = client.get("/api/v1/office/compliance/cases?type=NON_PAYMENT&status=OPEN", headers=da).json()["data"]
    assert client.get(f"/api/v1/office/compliance/cases/{c['case_id']}", headers=hdr(S["ro-apfc"], "fo.apfc")).json()["data"]["history"][0]["action"] == "OPENED"
    assert client.post("/api/v1/office/compliance/cases", json=body, headers=hdr(S["member-a"], "member")).status_code == 403
    listed = client.get("/api/v1/public/defaulting-establishments", headers=hdr("anon", "public")).json()["data"]
    assert [e["establishment_id"] for e in listed["establishments"]] == [EST] and listed["label"] == "SYNTHETIC_DEMO"


def test_vishwas_application_approved_raises_one_revised_demand(ctx):
    client, q, deliver = ctx
    demand(deliver, "DEM-A-14B", amount=1000000)
    demand(deliver, "DEM-B-14B", amount=500000)
    demand(deliver, "DEM-A-07Q", kind="INTEREST_7Q", amount=200000)
    sig = hdr(S["emp-signatory"], "employer.signatory", establishment=EST)
    assert client.post("/api/v1/employers/me/vishwas-applications", json={"demand_ids": ["DEM-A-07Q"], "declaration": True},
                       headers=sig).status_code == 422                       # 7Q interest is not covered
    r = client.post("/api/v1/employers/me/vishwas-applications", json={"demand_ids": ["DEM-A-14B", "DEM-B-14B"], "declaration": True}, headers=sig)
    assert r.status_code == 201 and r.json()["data"]["damages_paise"] == 1500000 and r.json()["data"]["estimated_settlement_paise"] == 450000
    app_id = r.json()["data"]["application_id"]
    assert client.post("/api/v1/employers/me/vishwas-applications", json={"demand_ids": ["DEM-A-14B"], "declaration": True},
                       headers=sig).json()["type"] == "/problems/already-applied"
    apfc = S["ro-apfc"]
    [listed] = client.get("/api/v1/office/compliance/vishwas-applications", headers=hdr(apfc, "fo.apfc")).json()["data"]
    assert listed["application_id"] == app_id
    url = f"/api/v1/office/compliance/vishwas-applications/{app_id}/decisions"
    body = {"decision": "APPROVE", "note": "Dispute settled under the scheme"}
    assert client.post(url, json=body, headers=hdr(apfc, "fo.apfc")).status_code == 428
    done = client.post(url, json=body, headers=hdr(apfc, "fo.apfc", {"action": "decide-vishwas", "resource_id": app_id, "amount_paise": 450000}))
    assert done.status_code == 200 and done.json()["data"]["revised_paise"] == 450000, done.json()
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='DemandRaised.v1'")
    p = json.loads(payload)["envelope"]["payload"] if isinstance(payload, str) else payload["envelope"]["payload"]
    assert p["amount_paise"] == 450000 and p["supersedes_demand_ids"] == ["DEM-A-14B", "DEM-B-14B"]
    assert client.post(url, json=body, headers=hdr(apfc, "fo.apfc", {"action": "decide-vishwas", "resource_id": app_id, "amount_paise": 450000})).status_code == 409
