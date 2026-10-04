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
    DELIVER["fn"] = deliver
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


def submitted(deliver, amount=AMOUNT, route="REVIEW", office="RO-DEMO-01", claim_id="CLM-0001", signal=None):
    deliver("ClaimSubmitted.v1", {"claim_id": claim_id, "form_type": "31", "amount_paise": amount,
                                  "rule_version": "demo-rules-2026.1", "office_id": office,
                                  "account_link_id": "AL-0001", "route": route, "advisory_signal_id": signal})


def queue(client, subject, role):
    return client.get("/api/v1/office/work-queue", headers=hdr(subject, role)).json()["data"]["items"]


def step(case, action="decide-case"):
    return {"action": action, "resource_id": case["case_id"], "resource_version": case["version"],
            "amount_paise": case["amount_paise"]}


DELIVER: dict = {}


def docket(case, role):
    """The officer generates the Claim Approval Docket in claim-service (CADGenerated.v1 reaches the work queue)."""
    DELIVER["fn"]("CADGenerated.v1", {"claim_id": case["claim_id"], "cad_id": f"CAD-{uuid.uuid4().hex[:8]}", "net_payable_paise": 1,
                                      "tds_paise": 0, "rule_version": "r", "static_data_version": "s", "officer_role": role})


def recommend(client, case, subject=DA, recommendation="APPROVE", with_docket=True, code=None):
    if with_docket:
        docket(case, "fo.da_accounts")
    return client.post(f"/api/v1/office/cases/{case['case_id']}/recommendations",
                       json={"checks": ["KYC verified", "Balance sufficient"], "note": "Documents in order",
                             "recommendation": recommendation, "account_status": "OPERATIVE", **({"reason_code": code} if code else {})},
                       headers=hdr(subject, "fo.da_accounts", {"action": "recommend-case", "resource_id": case["case_id"],
                                                               "resource_version": case["version"]}))


def decide(client, case, subject, role, decision="APPROVE", reason=None, path="decisions", with_docket=True, code=None):
    if with_docket:
        docket(case, role)
    return client.post(f"/api/v1/office/cases/{case['case_id']}/{path}", json={"decision": decision, "reason": reason, **({"reason_code": code} if code else {})},
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
    no_docket = client.post(f"/api/v1/office/cases/{case['case_id']}/decisions", json={"decision": "APPROVE"}, headers=hdr(SS, "fo.ss", step(case)))
    assert no_docket.status_code == 409 and no_docket.json()["type"] == "/problems/docket-required"   # CAD at each level
    docket(case, "fo.ss")
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
    r = decide(client, case, SS, "fo.ss", "REJECT", "Not eligible")          # an intermediate level cannot reject
    assert r.status_code == 200 and r.json()["data"]["current_role"] == "fo.da_accounts" and r.json()["data"]["state"] == "IN_REVIEW"
    assert "Rejection recommended" in r.json()["data"]["data"]["returned_for_rejection"] and outbox(q)[-1]["decision"] == "RETURN"
    [case] = queue(client, DA, "fo.da_accounts")
    assert recommend(client, case, recommendation="REJECT").status_code == 200   # re-forwarded as "Recommend to Reject"
    [case] = queue(client, SS, "fo.ss")
    assert decide(client, case, SS, "fo.ss", "APPROVE").json()["type"] == "/problems/decision-not-offered"
    r = decide(client, case, SS, "fo.ss", "REJECT", "Agree: not eligible")    # concurs and forwards
    assert r.json()["data"]["current_role"] == "fo.apfc"
    [case] = queue(client, APFC, "fo.apfc")
    assert decide(client, case, APFC, "fo.apfc", "APPROVE", path="second-approvals").json()["type"] == "/problems/decision-not-offered"
    r = decide(client, case, APFC, "fo.apfc", "REJECT", "Not eligible under para 68", path="second-approvals")
    assert r.status_code == 200 and r.json()["data"]["state"] == "REJECTED"
    assert outbox(q)[-1]["final"] is True and outbox(q)[-1]["decision"] == "REJECT" and outbox(q)[-1]["recommendation"] == "REJECT"
    assert outbox(q)[-1]["reason_code"] == "OTHER"                  # no reason chosen: the officer's note says what to do


def test_a_rejection_carries_the_rule_sets_reason_and_its_fix(ctx):
    """P2.23b: the initiator recommends rejection for a reason of the rule set; the final level keeps it (or changes it);
    the decision carries it, so the member is shown what fixes it."""
    client, q, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    view = client.get(f"/api/v1/office/cases/{case['case_id']}", headers=hdr(DA, "fo.da_accounts")).json()["data"]
    assert {"BANK_DETAILS", "OTHER"} <= {r["code"] for r in view["rejection_reasons"]} and all(r["fix"] for r in view["rejection_reasons"])
    assert recommend(client, case, recommendation="REJECT", code="NO_SUCH_REASON").status_code == 422
    r = recommend(client, case, recommendation="REJECT", code="BANK_DETAILS")
    assert r.status_code == 200 and r.json()["data"]["data"]["rejection_code"] == "BANK_DETAILS"
    [case] = queue(client, SS, "fo.ss")
    decide(client, case, SS, "fo.ss", "REJECT", "Cheque shows another name")
    [case] = queue(client, APFC, "fo.apfc")
    r = decide(client, case, APFC, "fo.apfc", "REJECT", "The account is not the member's", path="second-approvals")
    assert r.status_code == 200 and outbox(q)[-1]["reason_code"] == "BANK_DETAILS"


def test_the_initiator_stops_and_restarts_a_claim(ctx):
    client, _, deliver = ctx
    submitted(deliver)
    [case] = queue(client, DA, "fo.da_accounts")
    url = f"/api/v1/office/cases/{case['case_id']}"
    assert client.post(f"{url}/stops", json={"reason": "short"}, headers=hdr(DA, "fo.da_accounts")).status_code == 400
    stopped = client.post(f"{url}/stops", json={"reason": "Court case on the member ID pending"}, headers=hdr(DA, "fo.da_accounts")).json()["data"]
    assert stopped["state"] == "STOPPED" and queue(client, DA, "fo.da_accounts") == []
    assert [c["case_id"] for c in client.get("/api/v1/office/stopped-cases", headers=hdr(DA, "fo.da_accounts")).json()["data"]] == [case["case_id"]]
    back = client.post(f"{url}/restarts", headers=hdr(DA, "fo.da_accounts")).json()["data"]
    assert back["state"] == "IN_REVIEW" and back["current_role"] == "fo.da_accounts"
    [case] = queue(client, DA, "fo.da_accounts")
    assert recommend(client, case).status_code == 200


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
    assert queue(client, CASH, "fo.cash") == []                                # the member corrects the bank details first
    base = {"claim_id": "CLM-0001", "reason": "", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 5000000,
            "rule_version": "demo-rules-2026.1", "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"}
    deliver("ClaimStateChanged.v1", {**base, "from_state": "PAYMENT_RETURNED", "to_state": "CORRECTION_PENDING"})
    [task] = queue(client, APFC, "fo.apfc")
    assert task["next_action"] == "approve-redisbursement"
    deliver("ClaimStateChanged.v1", {**base, "from_state": "CORRECTION_PENDING", "to_state": "REISSUE_APPROVED"})
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


ZO_ACC = S["zo-acc"]


def test_grievance_case_follows_registration_escalation_and_resolution(ctx):
    client, _, deliver = ctx
    deliver("GrievanceRegistered.v1", {"grievance_id": "GRV-1", "category": "CLAIM_DELAY", "office_id": "RO-DEMO-01",
                                       "linked_claim_id": "CLM-0001"}, "grievance-service")
    [case] = queue(client, PRO, "fo.pro")
    assert case["kind"] == "GRIEVANCE" and case["grievance_id"] == "GRV-1" and case["next_action"] == "handle-grievance"
    deliver("GrievanceEscalated.v1", {"grievance_id": "GRV-1", "from_tier": "RO", "to_tier": "ZO",
                                      "office_id": "ZO-DEMO-01"}, "grievance-service")
    assert queue(client, PRO, "fo.pro") == []
    [case] = queue(client, ZO_ACC, "zo.acc")
    assert case["chain"] == ["fo.pro", "zo.acc"]
    deliver("GrievanceResolved.v1", {"grievance_id": "GRV-1", "office_id": "RO-DEMO-01", "tier": "ZO",
                                     "within_sla": True}, "grievance-service")
    assert queue(client, ZO_ACC, "zo.acc") == []


def test_case_shows_advisory_signal(ctx):
    client, _, deliver = ctx
    submitted(deliver, amount=1000000, signal="RSK-1")
    [case] = queue(client, DA, "fo.da_accounts")
    assert case["advisory_signal_id"] == "RSK-1"


def test_case_uses_the_chain_of_the_claims_rule_version_and_type(ctx):
    client, _, deliver = ctx
    import copy
    from epfo_persistence.policy import baseline
    doc = copy.deepcopy(baseline())
    doc["claims"]["types"]["ADVANCE_HOUSING"] = {
        "form_type": "31", "label": "House", "plain_rule": "x", "max_from": "total_balance",
        "approval_bands": [{"upto_paise": None, "chain": ["fo.da_accounts", "fo.ao", "fo.apfc"]}]}
    doc["claims"]["settlement_sla_days"] = 7
    doc.update(rule_version="demo-rules-2026.9", effective_from="2026-01-01")
    deliver("PolicyPublished.v1", {"version_id": "POL-T", "rule_version": "demo-rules-2026.9", "effective_from": "2026-01-01",
                                   "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc}, "platform-service")
    deliver("ClaimSubmitted.v1", {"claim_id": "CLM-H", "form_type": "31", "amount_paise": 100000, "rule_version": "demo-rules-2026.9",
                                  "office_id": "RO-DEMO-01", "account_link_id": "AL-0001", "route": "REVIEW",
                                  "advisory_signal_id": None, "claim_type": "ADVANCE_HOUSING"})
    [case] = queue(client, DA, "fo.da_accounts")
    assert case["chain"] == ["fo.da_accounts", "fo.ao", "fo.apfc"] and case["rule_version"] == "demo-rules-2026.9"



def test_freeze_holds_the_case_and_defreeze_restarts_under_the_stricter_chain(ctx):
    client, _, deliver = ctx
    submitted(deliver)                                                        # ₹6,00,000 → DA → SS → APFC
    [case] = queue(client, DA, "fo.da_accounts")
    recommend(client, case)
    base = {"claim_id": "CLM-0001", "claim_type": "ADVANCE_ILLNESS", "amount_paise": AMOUNT, "rule_version": "demo-rules-2026.1",
            "office_id": "RO-DEMO-01", "account_link_id": "AL-0001"}
    deliver("ClaimStateChanged.v1", {**base, "from_state": "RECOMMENDED", "to_state": "ON_HOLD_FROZEN", "reason": "ACCOUNT_FROZEN"})
    assert queue(client, SS, "fo.ss") == []                                   # paused
    deliver("ClaimStateChanged.v1", {**base, "from_state": "ON_HOLD_FROZEN", "to_state": "UNDER_REVIEW", "reason": "DEFROZEN_APPROVALS_VOID"})
    [case] = queue(client, DA, "fo.da_accounts")
    assert case["chain"] == ["fo.da_accounts", "fo.ao", "fo.apfc", "fo.oic"] and case["round"] == 2
    assert recommend(client, case).status_code == 200                         # a new round: the same DA may act again
