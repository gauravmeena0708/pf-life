"""claim-service tests on SQLite with real routes, signed tokens and the event handlers called directly."""
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
SUBJECTS = SEED["keycloak_subjects"]
MEMBER_A, MEMBER_B = SUBJECTS["member-a"], SUBJECTS["member-b"]
CASHIER = SUBJECTS["ro-cashier"]
JOURNEY_B_AMOUNT = 60000000    # ₹6,00,000: above the auto limit, in the DA → SS → APFC band


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/claim.db")
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
    epfo_auth.configure(audience="claim-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())

    def deliver(event_type, payload, producer):
        from app.infra.messaging import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "producer": producer,
                 "correlation_id": str(uuid.uuid4()), "payload": payload}
        return asyncio.run(apply_once(db.sessions(), event, dispatch)), event
    yield TestClient(application, raise_server_exceptions=False), q, deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None, **extra):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "claim-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID}), **extra}


def member(subject=MEMBER_A, step_up=None, **extra):
    return hdr(subject, "member", step_up, **extra)


def create(client, amount=JOURNEY_B_AMOUNT, account="AL-0001", subject=MEMBER_A, claim_type="ADVANCE_ILLNESS"):
    return client.post("/api/v1/members/me/claims", json={"account_link_id": account, "claim_type": claim_type,
                                                           "amount_paise": amount}, headers=member(subject))


def confirm(client, created, subject=MEMBER_A):
    c = created["confirmation"]
    return client.post(f"/api/v1/members/me/claims/{created['claim_id']}/confirmations", headers=member(
        subject, {"action": c["action"], "resource_id": c["resource_id"], "resource_version": c["resource_version"],
                  "amount_paise": c["amount_paise"]}))


def events(q, event_type=None):
    rows = [(r[0], json.loads(r[1]) if isinstance(r[1], str) else r[1]) for r in q("SELECT event_type, payload FROM outbox ORDER BY id")]
    return [p["envelope"]["payload"] for t, p in rows if event_type is None or t == event_type] if event_type else [t for t, _ in rows]


def test_eligible_types_use_opening_balance_and_explain_rules(ctx):
    client, *_ = ctx
    r = client.get("/api/v1/members/me/claims/eligible-types", headers=member())
    assert r.status_code == 200
    body = r.json()["data"]
    account = body["accounts"][0]
    assert account["account_link_id"] == "AL-0001" and account["balance"]["total_paise"] == 600000000
    types = {t["claim_type"]: t for t in account["types"]}
    assert types["ADVANCE_ILLNESS"]["eligible"] and types["ADVANCE_ILLNESS"]["max_amount_paise"] == 100000000   # capped at ₹10,00,000
    assert not types["FINAL_SETTLEMENT"]["eligible"] and types["FINAL_SETTLEMENT"]["reasons"]
    assert body["illustrative_only"] is True


def test_non_member_is_forbidden(ctx):
    client, *_ = ctx
    assert client.get("/api/v1/members/me/claims", headers=hdr(CASHIER, "fo.cash")).status_code == 403


def test_create_shows_summary_route_and_confirmation_binding(ctx):
    client, *_ = ctx
    r = create(client)
    assert r.status_code == 201, r.json()
    d = r.json()["data"]
    assert d["state"] == "AWAITING_CONFIRMATION"
    assert "₹6,00,000" in d["summary"] and "Assistant PF commissioner" in d["summary"]
    assert d["rules_applied"]["route"] == "REVIEW"
    assert d["confirmation"] == {"action": "confirm-claim", "resource_id": d["claim_id"], "resource_version": 1,
                                 "amount_paise": JOURNEY_B_AMOUNT}


def test_amount_above_limit_and_other_members_account_are_refused(ctx):
    client, *_ = ctx
    over = create(client, amount=100000001)
    assert over.status_code == 422 and over.json()["max_amount_paise"] == 100000000
    assert create(client, account="AL-0001", subject=MEMBER_B).status_code == 404   # member B names A's account


def test_member_b_cannot_read_member_a_claim(ctx):
    client, *_ = ctx
    claim_id = create(client).json()["data"]["claim_id"]
    r = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member(MEMBER_B))
    assert r.status_code == 404 and "claim_id" not in r.text.replace(claim_id, "")
    assert client.get("/api/v1/members/me/claims", headers=member(MEMBER_B)).json()["data"] == []


def test_confirmation_needs_step_up_bound_to_amount_and_version(ctx):
    client, *_ = ctx
    d = create(client).json()["data"]
    url = f"/api/v1/members/me/claims/{d['claim_id']}/confirmations"
    assert client.post(url, headers=member()).status_code == 428
    wrong = {**d["confirmation"], "amount_paise": 1}
    assert client.post(url, headers=member(step_up=wrong)).status_code == 403


def test_review_route_emits_claim_submitted(ctx):
    client, q, _ = ctx
    r = confirm(client, create(client).json()["data"])
    assert r.status_code == 200 and r.json()["data"]["state"] == "UNDER_REVIEW"
    [submitted] = events(q, "ClaimSubmitted.v1")
    assert submitted["route"] == "REVIEW" and submitted["office_id"] == "RO-DEMO-01"
    assert [n["template"] for n in events(q, "NotificationRequested.v1")] == ["CLAIM_SUBMITTED", "CLAIM_UNDER_REVIEW"]
    again = {"claim_id": submitted["claim_id"], "confirmation": {"action": "confirm-claim", "resource_id": submitted["claim_id"],
                                                                 "resource_version": 3, "amount_paise": JOURNEY_B_AMOUNT}}
    assert confirm(client, again).status_code == 409     # confirming twice never submits twice


def test_small_claim_is_auto_approved(ctx):
    client, q, _ = ctx
    r = confirm(client, create(client, amount=5000000).json()["data"])
    assert r.json()["data"]["state"] == "AUTO_APPROVED"
    assert events(q, "ClaimDecisionRecorded.v1")[0]["decision"] == "AUTO_APPROVED"


def test_second_open_claim_of_same_type_is_refused(ctx):
    client, *_ = ctx
    create(client)
    r = create(client, amount=1000000)
    assert r.status_code == 409 and r.json()["type"] == "/problems/claim-already-open"


def _approved_claim(client, deliver):
    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]
    base = {"case_id": "CASE-1", "claim_id": claim_id, "officer_subject": "x", "reason": None, "next_role": None}
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts",
                                         "approval_level": 0, "final": False}, "workflow-service")
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "APPROVE", "officer_role": "fo.ss",
                                         "approval_level": 1, "final": False}, "workflow-service")
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "APPROVE", "officer_role": "fo.apfc",
                                         "approval_level": 2, "final": True, "reason": "Documents in order"}, "workflow-service")
    return claim_id


def test_officer_chain_moves_claim_to_approved_and_duplicate_events_apply_once(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    d = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert d["state"] == "APPROVED"
    assert [t["state"] for t in d["timeline"]] == ["AWAITING_CONFIRMATION", "SUBMITTED", "UNDER_REVIEW", "RECOMMENDED",
                                                  "AWAITING_NEXT_APPROVAL", "APPROVED"]
    assert d["timeline"][3]["by"] == "Dealing assistant (accounts)"
    applied, event = deliver("ClaimDebitPosted.v1", {"journal_id": "J1", "claim_id": claim_id, "postings": [
        {"account_code": "AC01_EPF", "side": "debit", "amount_paise": JOURNEY_B_AMOUNT, "account_link_id": "AL-0001", "share": "employee"},
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": JOURNEY_B_AMOUNT}]}, "contribution-service")
    assert applied
    from app.infra.messaging import dispatch  # noqa: F401  (the same event again is a no-op through the inbox)
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), event, dispatch)) is False
    assert q("SELECT employee_paise FROM accounts WHERE account_link_id='AL-0001'")[0][0] == 360000000 - JOURNEY_B_AMOUNT


def test_payment_needs_debit_step_up_and_idempotency_then_settles(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    url = f"/api/v1/office/claims/{claim_id}/payment-instructions"
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    assert client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", step)).status_code == 400
    early = client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "k0"}))
    assert early.status_code == 409 and early.json()["type"] == "/problems/ledger-debit-pending"
    deliver("ClaimDebitPosted.v1", {"journal_id": "J1", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": JOURNEY_B_AMOUNT}]}, "contribution-service")
    assert client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", **{"Idempotency-Key": "k1"})).status_code == 428
    first = client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "k1"}))
    again = client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "k1"}))
    assert first.status_code == 200 and again.json()["data"] == first.json()["data"]
    assert len(events(q, "PaymentInstructed.v1")) == 1
    other = client.post(url, json={}, headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "k2"}))
    assert other.status_code == 409          # already PAYMENT_PENDING: never a second payment
    pid = first.json()["data"]["payment_id"]
    deliver("PaymentConfirmed.v1", {"payment_id": pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                    "reference_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT, "mock": True}, "payment-simulator")
    d = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert d["state"] == "SETTLED" and "CLAIM_SETTLED" in [n["template"] for n in events(q, "NotificationRequested.v1")]


def test_return_then_reissue(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    deliver("ClaimDebitPosted.v1", {"journal_id": "J1", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": JOURNEY_B_AMOUNT}]}, "contribution-service")
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    pid = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={"demo_scenario": "RETURN"},
                      headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "a"})).json()["data"]["payment_id"]
    deliver("PaymentReturned.v1", {"payment_id": pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                   "reference": claim_id, "return_reason": "MOCK_ACCOUNT_CLOSED", "mock": True}, "payment-simulator")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "PAYMENT_RETURNED"
    r = client.post(f"/api/v1/office/claims/{claim_id}/reissues", json={},
                    headers=hdr(CASHIER, "fo.cash", {**step, "action": "reissue-payment"}, **{"Idempotency-Key": "b"}))
    assert r.status_code == 200 and r.json()["data"]["attempt"] == 2 and r.json()["data"]["payment_id"].endswith("-2")
    # A late confirmation for the first (returned) payment must not settle the re-issued one.
    deliver("PaymentConfirmed.v1", {"payment_id": pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                    "reference_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT, "mock": True}, "payment-simulator")
    assert client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]["state"] == "PAYMENT_PENDING"


def test_cashier_of_other_office_sees_not_found(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    stranger = hdr(str(uuid.uuid4()), "fo.cash", {"action": "instruct-payment", "resource_id": claim_id,
                                                   "amount_paise": JOURNEY_B_AMOUNT}, **{"Idempotency-Key": "z"})
    assert client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={}, headers=stranger).status_code == 403


def test_open_risk_signal_sends_small_claim_to_officer_without_accusing(ctx):
    client, q, deliver = ctx
    deliver("RiskSignalRaised.v1", {"signal_id": "RSK-1", "detection_type": "NEW_DEVICE_CONTACT_CHANGE_CLAIM",
                                    "rule_version": "r", "evidence_refs": ["e1"], "subject_ref": MEMBER_A,
                                    "explanation": "x"}, "intelligence-service")
    r = confirm(client, create(client, amount=5000000).json()["data"])          # ₹50,000 would normally be automatic
    d = r.json()["data"]
    assert d["state"] == "UNDER_REVIEW" and "not an accusation" in d["timeline"][-1]["note"]
    assert events(q, "ClaimSubmitted.v1")[0]["advisory_signal_id"] == "RSK-1"


def test_benign_review_restores_automatic_settlement(ctx):
    client, q, deliver = ctx
    deliver("RiskSignalRaised.v1", {"signal_id": "RSK-2", "detection_type": "X", "rule_version": "r", "evidence_refs": [],
                                    "subject_ref": MEMBER_A, "explanation": "x"}, "intelligence-service")
    deliver("RiskSignalReviewed.v1", {"signal_id": "RSK-2", "subject_ref": MEMBER_A, "outcome": "BENIGN"}, "intelligence-service")
    r = confirm(client, create(client, amount=5000000).json()["data"])
    assert r.json()["data"]["state"] == "AUTO_APPROVED"
    assert events(q, "ClaimSubmitted.v1")[0]["advisory_signal_id"] is None


def test_frozen_account_blocks_new_claims_confirmation_and_payment(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    deliver("ClaimDebitPosted.v1", {"journal_id": "J1", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": JOURNEY_B_AMOUNT}]}, "contribution-service")
    uan = SEED["members"][0]["uan"]
    deliver("AccountFrozen.v1", {"target_type": "member", "target_id": uan, "category": "B", "order_ref": "ORD-1"}, "member-service")
    r = create(client, amount=100000)                                               # DENY-15
    assert r.status_code == 403 and r.json()["type"] == "/problems/account-frozen"
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    r = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={},
                    headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "f1"}))   # DENY-22
    assert r.status_code == 409 and r.json()["type"] == "/problems/account-frozen"
    deliver("AccountDefrozen.v1", {"target_type": "member", "target_id": uan, "order_ref": "CASE-1"}, "member-service")
    r = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={},
                    headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "f2"}))
    assert r.status_code == 200


def _publish(deliver, change, version="demo-rules-2026.9", effective="2026-01-01"):
    import copy
    from epfo_persistence.policy import baseline
    doc = copy.deepcopy(baseline())
    change(doc)
    doc.update(rule_version=version, effective_from=effective)
    deliver("PolicyPublished.v1", {"version_id": "POL-T", "rule_version": version, "effective_from": effective,
                                   "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc}, "platform-service")


HOUSING = {"form_type": "31", "label": "Advance for building a house", "plain_rule": "Up to 90% of your balance after 3 years of service.",
           "requires_active_employment": True, "min_service_months": 36, "max_from": "total_balance", "max_pct_bp": 9000,
           "once_every_months": 120, "auto_settle_up_to_paise": None,
           "approval_bands": [{"upto_paise": None, "chain": ["fo.da_accounts", "fo.ao", "fo.apfc"]}]}


def test_published_policy_adds_retires_and_routes_claim_types(ctx):
    client, q, deliver = ctx
    before = create(client, amount=100000).json()["data"]                     # made under the baseline rules

    def change(d):
        d["claims"]["types"]["ADVANCE_HOUSING"] = HOUSING
        d["claims"]["types"]["ADVANCE_ILLNESS"]["retired"] = True
    _publish(deliver, change)
    types = {t["claim_type"]: t for t in client.get("/api/v1/members/me/claims/eligible-types", headers=member()).json()["data"]["accounts"][0]["types"]}
    assert "ADVANCE_ILLNESS" not in types and types["ADVANCE_HOUSING"]["eligible"]
    assert types["ADVANCE_HOUSING"]["max_amount_paise"] == 600000000 * 9000 // 10000
    assert create(client, amount=100000).status_code == 422                     # retired type: no new claims
    r = client.post("/api/v1/members/me/claims", json={"account_link_id": "AL-0001", "claim_type": "ADVANCE_HOUSING",
                                                        "amount_paise": 100000}, headers=member())
    d = r.json()["data"]
    assert r.status_code == 201 and d["rule_version"] == "demo-rules-2026.9"
    assert d["rules_applied"]["route"] == "REVIEW"                              # always reviewed, even ₹1,000
    assert d["rules_applied"]["approval_chain"] == ["Dealing assistant (accounts)", "Accounts officer", "Assistant PF commissioner"]
    assert confirm(client, d).json()["data"]["state"] == "UNDER_REVIEW"
    again = client.post("/api/v1/members/me/claims", json={"account_link_id": "AL-0001", "claim_type": "ADVANCE_HOUSING",
                                                            "amount_paise": 100000}, headers=member())
    assert again.status_code in (409, 422)                                      # once every 120 months (or already open)
    # The claim prepared before the change keeps its own rules: still automatic under the baseline.
    assert before["rule_version"] == "demo-rules-2026.1"
    assert confirm(client, before).json()["data"]["state"] == "AUTO_APPROVED"


def test_a_future_policy_does_not_apply_before_its_date(ctx):
    client, q, deliver = ctx
    _publish(deliver, lambda d: d["claims"]["types"]["ADVANCE_ILLNESS"].update(retired=True), effective="2099-01-01")
    assert create(client, amount=100000).status_code == 201
