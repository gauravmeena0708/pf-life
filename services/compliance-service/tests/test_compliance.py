"""Phase 2, slice 8a: compliance cases (DA Compliance opens, the office searches), the published defaulter list, and
VISHWAS — the employer applies over open 14B demands (projected from contribution-service), the APFC decides, and an
approval raises one revised demand (DemandRaised.v1)."""
import asyncio
import importlib
import json
from datetime import date
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
            from epfo_persistence.policy import policy_metadata
            await c.run_sync(policy_metadata.create_all)
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


def demand(deliver, demand_id, kind="DAMAGES_14B", amount=1000000, state="OPEN", trrn="T1", wage_month="2026-06", days=90, working="w"):
    deliver("DemandStateChanged.v1", {"demand_id": demand_id, "establishment_id": EST, "kind": kind, "trrn": trrn, "wage_month": wage_month,
                                      "amount_paise": amount, "days_late": days, "state": state, "working": working})


def test_establishment_office_transfer_updates_jurisdiction_but_keeps_open_case(ctx):
    client, q, deliver = ctx
    body = {"establishment_id": EST, "kind": "NON_PAYMENT", "wage_months": ["2026-07"],
            "amount_paise": 1000, "note": "Office transfer test"}
    response = client.post("/api/v1/office/compliance/cases", json=body,
                           headers=hdr(S["ro-da-compliance"], "fo.da_compliance"))
    assert response.status_code == 201, response.text
    payload = {"establishment_id": EST, "from_office_id": "RO-DEMO-01",
               "to_office_id": "RO-DEMO-02", "effective_from": "2026-10-01"}
    deliver("EstablishmentOfficeTransferred.v1", payload)
    deliver("EstablishmentOfficeTransferred.v1", payload)
    assert q(f"SELECT office_id FROM establishments WHERE establishment_id='{EST}'") == [("RO-DEMO-02",)]
    assert q(f"SELECT office_id FROM compliance_cases WHERE establishment_id='{EST}'") == [("RO-DEMO-01",)]   # cases keep their office


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


def test_vishwas_2026_recalculates_old_damages_at_the_monthly_rates(ctx, monkeypatch):
    """VISHWAS, 2026 (G.S.R. 525(E)): defaults before 14 June 2024; 0.25% a month up to two months of default, 0.50% from
    two to under four, 1% beyond; all 7Q interest paid first; open 29 June - 28 December 2026."""
    import app.api.routes as routes
    monkeypatch.setattr(routes, "today", lambda: date(2026, 10, 1))
    client, q, deliver = ctx
    late = lambda amount, days: f"{days} days late on ₹{amount:,}: 14B at 5% a year"  # noqa: E731
    demand(deliver, "DEM-A-14B", amount=1000000, trrn="TA", wage_month="2024-01", days=45, working=late(100000, 45))      # 1.5 months
    demand(deliver, "DEM-B-14B", amount=500000, trrn="TB", wage_month="2023-06", days=200, working=late(50000, 200))     # 6.6 months
    demand(deliver, "DEM-C-14B", amount=300000, trrn="TC", wage_month="2024-08", days=30, working=late(40000, 30))       # after the date
    demand(deliver, "DEM-D-14B", amount=300000, trrn="TD", wage_month="2023-01", days=60, working=late(40000, 60))
    demand(deliver, "DEM-D-07Q", kind="INTEREST_7Q", amount=20000, trrn="TD", wage_month="2023-01", days=60)          # interest unpaid
    sig = hdr(S["emp-signatory"], "employer.signatory", establishment=EST)
    apply = lambda ids: client.post("/api/v1/employers/me/vishwas-applications", json={"demand_ids": ids, "declaration": True}, headers=sig)  # noqa: E731
    assert apply(["DEM-D-07Q"]).status_code == 422                                     # interest is not damages
    assert "before 2024-06-14" in apply(["DEM-C-14B"]).json()["detail"]
    assert "7Q interest" in apply(["DEM-D-14B"]).json()["detail"]
    mine = client.get("/api/v1/employers/me/vishwas-applications", headers=sig).json()["data"]
    by_id = {a["demand_id"]: a for a in mine["assessment"]}
    assert (by_id["DEM-A-14B"]["rate_pct_per_month"], by_id["DEM-B-14B"]["rate_pct_per_month"]) == (0.25, 1.0)
    assert by_id["DEM-A-14B"]["revised_paise"] == 36900 and by_id["DEM-B-14B"]["revised_paise"] == 328700   # ₹1,00,000 x 0.25% x 1.48; ₹50,000 x 1% x 6.58
    r = apply(["DEM-A-14B", "DEM-B-14B"])
    assert r.status_code == 201 and r.json()["data"]["damages_paise"] == 1500000 and r.json()["data"]["estimated_settlement_paise"] == 365600
    app_id = r.json()["data"]["application_id"]
    assert apply(["DEM-A-14B"]).json()["type"] == "/problems/already-applied"
    apfc = S["ro-apfc"]
    [listed] = client.get("/api/v1/office/compliance/vishwas-applications", headers=hdr(apfc, "fo.apfc")).json()["data"]
    assert listed["application_id"] == app_id and listed["proposed_revised_paise"] == 365600
    url = f"/api/v1/office/compliance/vishwas-applications/{app_id}/decisions"
    body = {"decision": "APPROVE", "note": "Dispute settled under the scheme"}
    assert client.post(url, json=body, headers=hdr(apfc, "fo.apfc")).status_code == 428
    step = hdr(apfc, "fo.apfc", {"action": "decide-vishwas", "resource_id": app_id, "amount_paise": 365600})
    done = client.post(url, json=body, headers=step)
    assert done.status_code == 200 and done.json()["data"]["revised_paise"] == 365600, done.json()
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='DemandRaised.v1'")
    p = json.loads(payload)["envelope"]["payload"] if isinstance(payload, str) else payload["envelope"]["payload"]
    assert p["amount_paise"] == 365600 and p["supersedes_demand_ids"] == ["DEM-A-14B", "DEM-B-14B"] and "VISHWAS, 2026" in p["working"]
    assert client.post(url, json=body, headers=step).status_code == 409
    monkeypatch.setattr(routes, "today", lambda: date(2026, 12, 29))                   # the window has closed
    assert "open from" in apply(["DEM-B-14B"]).json()["detail"]


def test_vishwas_2026_reads_the_defaults_of_a_damages_order():
    """A damages order lists its defaults with the automatic damages at the band's yearly rate; the amount paid late is
    worked back from them, and each default is recalculated at its own monthly rate."""
    from epfo_persistence.policy import baseline, late_payment_charges, section
    from app.api.routes import vishwas_terms
    rules = baseline()
    auto = lambda arrears, days: late_payment_charges(arrears, date(2015, 7, 15), date(2015, 7, 15) + __import__("datetime").timedelta(days=days), rules)["damages_14b_paise"]  # noqa: E731
    lines = [{"demand_id": "X1", "wage_month": "2015-06", "days_late": 4097, "auto_paise": auto(1000000, 4097), "levied_paise": 1},
             {"demand_id": "X2", "wage_month": "2023-11", "days_late": 50, "auto_paise": auto(4000000, 50), "levied_paise": 1}]
    order = {"demand_id": "D14B-CMP-1", "amount_paise": 99999900, "trrn": "TRRN-X", "wage_month": "2015-06", "working": json.dumps(lines)}
    a = vishwas_terms(order, set(), section(rules, "vishwas"), section(rules, "late_payment"), date(2026, 10, 1))
    assert a["eligible"], a["reasons"]
    long_one, short_one = (x["arrears_paise"] for x in a["defaults"])
    assert long_one == 1000000 and abs(short_one - 4000000) <= 1000      # the damages were rounded to a rupee: ₹273.97 → ₹274
    assert [x["rate_pct_per_month"] for x in a["defaults"]] == [1.0, 0.25]       # 134.7 months; 1.6 months
    assert a["revised_paise"] == sum(x["revised_paise"] for x in a["defaults"])
    later = vishwas_terms({**order, "working": json.dumps([{**lines[1], "wage_month": "2024-06"}])}, set(), section(rules, "vishwas"),
                          section(rules, "late_payment"), date(2026, 10, 1))
    assert not later["eligible"] and "before 2024-06-14" in later["reasons"][0]
    owed = vishwas_terms(order, {"2023-11"}, section(rules, "vishwas"), section(rules, "late_payment"), date(2026, 10, 1))
    assert "7Q interest" in " ".join(owed["reasons"])
