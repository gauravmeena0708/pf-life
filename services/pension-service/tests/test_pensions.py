"""Pensions under the formula in the rule set: the seeded pensions, a published change proposing revisions
(never reductions), APFC (Pension) approval with arrears, the member's estimate and the public calculator."""
import asyncio
import copy
import importlib
import json
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

ROOT = Path(__file__).resolve().parents[3]
SEED = json.load(open(ROOT / "scripts" / "seed" / "synthetic.json"))
SUBJECTS = SEED["keycloak_subjects"]
PENSIONER, APFC_P, MEMBER_A = SUBJECTS["pensioner-a"], SUBJECTS["ro-pension"], SUBJECTS["member-a"]


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/pension.db")
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
        seed.SEED_FILE = str(ROOT / "scripts" / "seed" / "synthetic.json")
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="pension-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())

    def publish(change, version, effective):
        from app.infra.messaging import dispatch
        from epfo_persistence.consumer import apply_once
        from epfo_persistence.policy import baseline
        doc = copy.deepcopy(baseline())
        change(doc)
        doc.update(rule_version=version, effective_from=effective)
        event = {"event_id": str(uuid.uuid4()), "event_type": "PolicyPublished.v1", "producer": "platform-service",
                 "correlation_id": str(uuid.uuid4()), "payload": {"version_id": version, "rule_version": version, "effective_from": effective,
                                                                  "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc}}
        asyncio.run(apply_once(db.sessions(), event, dispatch))
    yield TestClient(application, raise_server_exceptions=False), q, publish
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "pension-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def months_paid_since(start: date) -> int:
    today = datetime.now(UTC).date()
    return (today.year - start.year) * 12 + today.month - start.month


def test_seeded_pension_follows_the_baseline_formula_and_is_paid_monthly(ctx):
    client, _, _ = ctx
    me = client.get("/api/v1/pensioners/me", headers=hdr(PENSIONER, "pensioner")).json()["data"]
    assert me["monthly_paise"] == 111400 and me["working"] == "₹6,500 x (12 years) / 70"      # ₹1,114
    paid = client.get("/api/v1/pensioners/me/payments", headers=hdr(PENSIONER, "pensioner")).json()["data"]
    assert len(paid) == months_paid_since(date(2023, 6, 1)) and {p["amount_paise"] for p in paid} == {111400}
    assert client.get("/api/v1/pensioners/me", headers=hdr(MEMBER_A, "member")).status_code == 403


def test_a_higher_minimum_pension_revises_pensions_in_payment_with_arrears(ctx):
    client, q, publish = ctx
    today = datetime.now(UTC).date()
    back = date(today.year - (today.month <= 3), (today.month - 4) % 12 + 1, 1)             # the first of three months ago

    def raise_minimum(d):
        d["pension"].update(minimum_pension_paise=150000, revise_in_payment_from=back.isoformat())
    publish(raise_minimum, "demo-rules-2026.8", "2026-12-01")      # the same change carried into a scheduled version first
    publish(raise_minimum, "demo-rules-2026.9", today.isoformat())
    queue = client.get("/api/v1/office/pensions/revisions", headers=hdr(APFC_P, "fo.apfc_pension")).json()["data"]["items"]
    assert [r["ppo_id"] for r in queue] == ["PPO-DEMO-0001"]          # the ₹5,786 pension is above the new minimum
    r = queue[0]
    assert (r["old_monthly_paise"], r["new_monthly_paise"]) == (111400, 150000)
    assert r["arrears_paise"] == 3 * (150000 - 111400)               # the three months already paid since the date
    url = "/api/v1/office/pensions/PPO-DEMO-0001/revisions"
    body = {"revision_id": r["revision_id"], "decision": "APPROVE", "note": "Minimum pension raised"}
    step = {"action": "approve-pension-revision", "resource_id": r["revision_id"]}
    assert client.post(url, json=body, headers=hdr(APFC_P, "fo.apfc_pension")).status_code == 428
    assert client.post(url, json=body, headers=hdr(APFC_P, "fo.apfc_pension", {**step, "amount_paise": 1})).status_code == 403
    done = client.post(url, json=body, headers=hdr(APFC_P, "fo.apfc_pension", {**step, "amount_paise": r["arrears_paise"]}))
    assert done.status_code == 200 and done.json()["data"]["state"] == "APPROVED"
    assert client.post(url, json=body, headers=hdr(APFC_P, "fo.apfc_pension", {**step, "amount_paise": r["arrears_paise"]})).status_code == 409
    me = client.get("/api/v1/pensioners/me", headers=hdr(PENSIONER, "pensioner")).json()["data"]
    assert me["monthly_paise"] == 150000 and me["rule_version"] == "demo-rules-2026.8"   # one revision for the one change
    paid = client.get("/api/v1/pensioners/me/payments", headers=hdr(PENSIONER, "pensioner")).json()["data"]
    assert paid[0]["kind"] == "ARREARS" and paid[0]["amount_paise"] == 3 * 38600

    # A further rise from the same date pays only what the earlier arrears did not cover.
    publish(lambda d: d["pension"].update(minimum_pension_paise=160000, revise_in_payment_from=back.isoformat()), "demo-rules-2026.13", today.isoformat())
    again = client.get("/api/v1/office/pensions/revisions", headers=hdr(APFC_P, "fo.apfc_pension")).json()["data"]["items"]
    assert [(r["old_monthly_paise"], r["new_monthly_paise"], r["arrears_paise"]) for r in again] == [(150000, 160000, 3 * 10000)]
    step2 = {"action": "approve-pension-revision", "resource_id": again[0]["revision_id"], "amount_paise": 30000}
    assert client.post(url, json={**body, "revision_id": again[0]["revision_id"]}, headers=hdr(APFC_P, "fo.apfc_pension", step2)).status_code == 200

    # A lower minimum never reduces a pension in payment; a change that leaves pensions in payment alone proposes nothing.
    publish(lambda d: d["pension"].update(minimum_pension_paise=100000), "demo-rules-2026.10", today.isoformat())

    def new_pensions_only(d):
        d["pension"].update(minimum_pension_paise=200000, applies_to_pensions_in_payment=False)
    publish(new_pensions_only, "demo-rules-2026.11", today.isoformat())
    assert client.get("/api/v1/office/pensions/revisions", headers=hdr(APFC_P, "fo.apfc_pension")).json()["data"]["items"] == []
    assert client.post(url, json=body, headers=hdr(SUBJECTS["member-a"], "member")).status_code == 403


def test_member_estimate_and_public_calculator_use_the_formula_in_force(ctx):
    client, _, publish = ctx
    est = client.get("/api/v1/members/me/pension-eligibility-preview", headers=hdr(MEMBER_A, "member")).json()["data"]
    now, at_58 = est["scenarios"]
    assert now["eligible"] is False and "10 years" in now["reason"]                      # about 4 years so far
    assert at_58["eligible"] is True and at_58["weightage_years"] == 2
    calc = client.post("/api/v1/public/demo-calculations/pension", json={"monthly_salary_paise": 1500000, "service_years": 20, "age_years": 58},
                       headers=hdr("anonymous", "public"))
    assert calc.json()["data"]["monthly_paise"] == 471400                               # ₹15,000 x 22 / 70
    publish(lambda d: d["pension"].update(divisor=60), "demo-rules-2026.12", datetime.now(UTC).date().isoformat())
    calc = client.post("/api/v1/public/demo-calculations/pension", json={"monthly_salary_paise": 1500000, "service_years": 20, "age_years": 58},
                       headers=hdr("anonymous", "public"))
    assert calc.json()["data"]["monthly_paise"] == 550000 and calc.json()["data"]["rule_version"] == "demo-rules-2026.12"
