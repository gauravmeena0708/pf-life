"""workflow-service tests on SQLite: case opening from events, the approval chain, jurisdiction,
separation of duties, step-up and the cash-section task."""
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

ROOT = Path(__file__).resolve().parents[3]
SEED = json.load(open(ROOT / "scripts" / "seed" / "synthetic.json"))
S = SEED["keycloak_subjects"]
DA, SS, AO, APFC, CASH, PRO = S["do-caseworker"], S["ro-ss"], S["ro-ao"], S["ro-apfc"], S["ro-cashier"], S["ro-pro"]
AMOUNT = 60000000          # ₹6,00,000 → chain DA → SS → APFC


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/workflow.db")
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
    epfo_auth.configure(audience="workflow-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())

    def deliver(event_type, payload, producer="claim-service"):
        from app.infra.messaging import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "producer": producer,
                 "correlation_id": str(uuid.uuid4()), "payload": payload}
        return asyncio.run(apply_once(db.sessions(), event, dispatch))
    yield TestClient(application, raise_server_exceptions=False), q, deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "workflow-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def submitted(deliver, amount=AMOUNT, route="REVIEW", office="RO-DEMO-01", claim_id="CLM-0001"):
    deliver("ClaimSubmitted.v1", {"claim_id": claim_id, "form_type": "31", "amount_paise": amount,
                                  "rule_version": "demo-rules-2026.1", "office_id": office,
                                  "account_link_id": "AL-0001", "route": route})


def queue(client, subject, role):
    return client.get("/api/v1/office/work-queue", headers=hdr(subject, role)).json()["data"]["items"]


def step(case, action="decide-case"):
    return {"action": action, "resource_id": case["case_id"], "resource_version": case["version"],
            "amount_paise": case["amount_paise"]}


def recommend(client, case, subject=DA):
    return client.post(f"/api/v1/office/cases/{case['case_id']}/recommendations",
                       json={"checks": ["KYC verified", "Balance sufficient"], "note": "Documents in order"},
                       headers=hdr(subject, "fo.da_accounts"))


def decide(client, case, subject, role, decision="APPROVE", reason=None, path="decisions"):
    return client.post(f"/api/v1/office/cases/{case['case_id']}/{path}", json={"decision": decision, "reason": reason},
                       headers=hdr(subject, role, step(case)))


def outbox(q):
    return [json.loads(p)["envelope"]["payload"] if isinstance(p, str) else p["envelope"]["payload"]
            for (p,) in q("SELECT payload FROM outbox WHERE event_type='CaseDecisionSubmitted.v1' ORDER BY id")]


def test_review_claim_opens_case_in_da_queue_only(ctx):
    client, _, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    assert case["chain"] == ["fo.da_accounts", "fo.ss", "fo.apfc"] and case["next_action"] == "recommend"
    assert queue(client, SS, "fo.ss") == []


def test_other_office_case_is_invisible(ctx):
    client, _, deliver = ctx
    submitted(deliver, office="RO-ELSEWHERE")
    assert queue(client, DA, "fo.da_accounts") == []
    assert client.get("/api/v1/office/work-queue", headers=hdr(str(uuid.uuid4()), "fo.da_accounts")).status_code == 403


def test_full_chain_with_step_up_and_events(ctx):
    client, q, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    r = recommend(client, case)
    assert r.status_code == 200 and r.json()["data"]["current_role"] == "fo.ss"
    [case] = queue(client, SS, "fo.ss")
    assert client.post(f"/api/v1/office/cases/{case['case_id']}/decisions", json={"decision": "APPROVE"},
                       headers=hdr(SS, "fo.ss")).status_code == 428                  # no step-up
    assert decide(client, case, SS, "fo.ss", path="second-approvals").status_code == 403  # SS cannot call the 2nd level
    r = decide(client, case, SS, "fo.ss")
    assert r.status_code == 200 and r.json()["data"]["current_role"] == "fo.apfc"
    [case] = queue(client, APFC, "fo.apfc")
    assert decide(client, case, APFC, "fo.apfc").status_code == 403                   # APFC must use second-approvals
    r = decide(client, case, APFC, "fo.apfc", path="second-approvals")
    assert r.status_code == 200 and r.json()["data"]["state"] == "AWAITING_PAYMENT"
    assert [(e["decision"], e["approval_level"], e["final"], e["officer_role"]) for e in outbox(q)] == [
        ("RECOMMEND", 0, False, "fo.da_accounts"), ("APPROVE", 1, False, "fo.ss"), ("APPROVE", 2, True, "fo.apfc")]
    [task] = queue(client, CASH, "fo.cash")
    assert task["next_action"] == "instruct-payment"


def test_same_person_cannot_recommend_and_approve(ctx):
    client, _, deliver = ctx
    submitted(deliver, amount=1000000)                  # ₹10,000 → DA → SS
    [case] = queue(client, DA, "fo.da_accounts")
    recommend(client, case)
    case = client.get(f"/api/v1/office/cases/{case['case_id']}", headers=hdr(DA, "fo.da_accounts")).json()["data"]
    r = decide(client, case, DA, "fo.ss")               # the recommender, holding a checker role
    assert r.status_code == 403 and r.json()["type"] == "/problems/separation-of-duties"


def test_reject_and_return_need_a_reason_and_return_restarts_round(ctx):
    client, q, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    recommend(client, case)
    [case] = queue(client, SS, "fo.ss")
    assert decide(client, case, SS, "fo.ss", "RETURN").status_code == 422
    r = decide(client, case, SS, "fo.ss", "RETURN", "Bank proof unreadable")
    assert r.status_code == 200 and r.json()["data"]["current_role"] == "fo.da_accounts" and r.json()["data"]["round"] == 2
    [case] = queue(client, DA, "fo.da_accounts")
    assert recommend(client, case).status_code == 200    # the same DA may act again in the new round
    [case] = queue(client, SS, "fo.ss")
    r = decide(client, case, SS, "fo.ss", "REJECT", "Not eligible")
    assert r.status_code == 200 and r.json()["data"]["state"] == "REJECTED"
    assert outbox(q)[-1]["final"] is True and outbox(q)[-1]["decision"] == "REJECT"


def test_auto_approved_claim_goes_straight_to_cash_and_payment_events_close_it(ctx):
    client, _, deliver = ctx
    submitted(deliver, amount=5000000, route="AUTO")
    assert queue(client, DA, "fo.da_accounts") == []
    deliver("ClaimDecisionRecorded.v1", {"claim_id": "CLM-0001", "decision": "AUTO_APPROVED", "reason_code": "X",
                                         "rule_version": "r", "amount_paise": 5000000, "account_link_id": "AL-0001"})
    [task] = queue(client, CASH, "fo.cash")
    deliver("PaymentInstructed.v1", {"claim_id": "CLM-0001", "payment_id": "P1", "amount_paise": 5000000,
                                     "attempt": 1, "demo_scenario": "RETURN"})
    assert queue(client, CASH, "fo.cash") == []
    deliver("PaymentReturned.v1", {"payment_id": "P1", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                   "reference": "CLM-0001", "return_reason": "X", "mock": True}, "payment-simulator")
    [task] = queue(client, CASH, "fo.cash")
    assert task["next_action"] == "reissue"


def test_pro_assigns_only_to_holder_of_current_role(ctx):
    client, _, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    bad = client.post(f"/api/v1/office/cases/{case['case_id']}/assignments", json={"assignee_username": "ro-ss"},
                      headers=hdr(PRO, "fo.pro"))
    assert bad.status_code == 422
    ok = client.post(f"/api/v1/office/cases/{case['case_id']}/assignments", json={"assignee_username": "do-caseworker"},
                     headers=hdr(PRO, "fo.pro"))
    assert ok.status_code == 200 and ok.json()["data"]["assignee_subject"] == DA


def test_public_offices_and_hrm_me(ctx):
    client, *_ = ctx
    offices = client.get("/api/v1/public/offices", headers=hdr("anonymous", "public")).json()["data"]
    assert offices[0]["office_id"] == "RO-DEMO-01"
    me = client.get("/api/v1/hrm/me", headers=hdr(APFC, "fo.apfc")).json()["data"]
    assert me["role"] == "fo.apfc" and me["office"]["office_id"] == "RO-DEMO-01"
