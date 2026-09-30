"""payment-simulator tests on SQLite: payment intent rules, signed callbacks, replay, idempotency, mock bank."""
import asyncio
import importlib
import json
import time
import uuid

import jwt
import pytest
from sqlalchemy import insert, text

from tests.conftest import JWKS, KEY, KID

EST = "EST-DEMO-0001"
TRRN = "TRRN0000000000001"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/pay.db")
    monkeypatch.setenv("MOCK_BANK_DELAY_SECONDS", "0")
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    import app.api.routes as routes
    routes.settings = config.settings
    from app.infra.models import Base
    from app.infra.tables import metadata, payables

    async def setup():
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            await c.run_sync(metadata.create_all)
            await c.execute(insert(payables).values(trrn=TRRN, establishment_id=EST, filing_id="F1", total_paise=500000, status="DUE"))
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    app = create_app()
    epfo_auth.configure(audience="payment-simulator", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())
    yield TestClient(app, raise_server_exceptions=False), routes, q, config
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    routes.settings = config.settings
    db._engine = None


def hdr(grants=("payment.initiate",), step_up=None, establishment=EST, key=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "payment-simulator", "sub": "signatory-1", "stakeholder": "employer.signatory",
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
              "grants": list(grants), "establishment_id": establishment}
    if step_up is not None:
        claims["step_up"] = step_up
    h = {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}
    if key:
        h["Idempotency-Key"] = key
    return h


STEP = {"action": "pay-challan", "resource_id": TRRN, "amount_paise": 500000}


def pay(client, **kw):
    return client.post(f"/api/v1/employers/me/challans/{TRRN}/payment-intents", json={"channel": "NET_BANKING"}, headers=hdr(**kw))


def test_requires_idempotency_key_grant_and_step_up(ctx):
    client, *_ = ctx
    assert pay(client).status_code == 400
    assert pay(client, key="k", grants=()).status_code == 403
    assert pay(client, key="k").status_code == 428
    assert pay(client, key="k", step_up={**STEP, "amount_paise": 1}).status_code == 403


def test_other_establishment_gets_404(ctx):
    client, *_ = ctx
    assert pay(client, key="k", step_up=STEP, establishment="EST-OTHER").status_code == 404


def test_cash_channel_is_definition_pending(ctx):
    client, *_ = ctx
    r = client.post(f"/api/v1/employers/me/challans/{TRRN}/payment-intents", json={"channel": "BANK_COUNTER"},
                    headers=hdr(key="k", step_up=STEP))
    assert r.status_code == 501


def test_retry_with_same_key_returns_same_payment(ctx):
    client, routes, q, _ = ctx
    first = pay(client, key="same", step_up=STEP)
    second = pay(client, key="same", step_up=STEP)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["data"]["payment_id"] == second.json()["data"]["payment_id"]
    assert len(q("SELECT * FROM payment_intents")) == 1
    third = pay(client, key="different", step_up=STEP)
    assert third.status_code == 409  # already pending: no double payment


def test_mock_bank_confirms_once_and_emits_event(ctx):
    client, routes, q, _ = ctx
    pay(client, key="k", step_up=STEP)
    assert asyncio.run(routes.process_due_payments()) == 1
    assert asyncio.run(routes.process_due_payments()) == 0
    assert q("SELECT status FROM payables")[0][0] == "PAID"
    events = q("SELECT event_type, payload FROM outbox")
    assert [e[0] for e in events] == ["PaymentConfirmed.v1"]
    payload = json.loads(events[0][1])["envelope"]["payload"]
    assert payload["purpose"] == "CHALLAN" and payload["reference_id"] == TRRN and payload["mock"] is True


def test_callback_signature_replay_and_duplicate(ctx):
    client, routes, q, config = ctx
    pid = pay(client, key="k", step_up=STEP).json()["data"]["payment_id"]
    from app.domain.bank import sign
    body = json.dumps({"payment_id": pid, "bank_reference": "B1"}).encode()
    ts, nonce = str(int(time.time())), "n-1"
    good = {"x-bank-timestamp": ts, "x-bank-nonce": nonce,
            "x-bank-signature": sign(config.settings.mock_bank_hmac_secret, ts, nonce, body), **hdr()}
    bad = {**good, "x-bank-signature": "0" * 64, "x-bank-nonce": "n-2"}
    url = "/api/v1/integrations/mock-bank/payment-confirmations"
    assert client.post(url, content=body, headers=bad).status_code == 401
    assert client.post(url, content=body, headers=good).status_code == 200
    assert client.post(url, content=body, headers=good).status_code == 409  # replayed nonce
    ts2, n3 = str(int(time.time())), "n-3"
    again = {**good, "x-bank-timestamp": ts2, "x-bank-nonce": n3,
             "x-bank-signature": sign(config.settings.mock_bank_hmac_secret, ts2, n3, body)}
    r = client.post(url, content=body, headers=again)  # new nonce, same payment: idempotent, no second event
    assert r.status_code == 200 and r.json()["data"]["duplicate"] is True
    assert len(q("SELECT * FROM outbox")) == 1


def test_return_scenario_emits_payment_returned(ctx):
    client, routes, q, _ = ctx
    client.post(f"/api/v1/employers/me/challans/{TRRN}/payment-intents",
                json={"channel": "NET_BANKING", "demo_scenario": "RETURN"}, headers=hdr(key="r", step_up=STEP))
    asyncio.run(routes.process_due_payments())
    assert [e[0] for e in q("SELECT event_type FROM outbox")] == ["PaymentReturned.v1"]
    assert q("SELECT status FROM payables")[0][0] == "FAILED"


def test_claim_settlement_from_payment_instruction_confirms_once(ctx):
    client, routes, q, _ = ctx
    event = {"event_type": "PaymentInstructed.v1", "payload": {
        "claim_id": "CLM-1", "payment_id": "PAY-CLM-1-1", "amount_paise": 60000000, "attempt": 1, "demo_scenario": "SUCCESS"}}

    async def deliver():
        import app.infra.db as db
        async with db.sessions()() as s, s.begin():
            await routes.dispatch(s, event)
    asyncio.run(deliver())
    asyncio.run(deliver())                              # duplicate instruction: still one intent
    assert len(q("SELECT * FROM payment_intents")) == 1
    assert asyncio.run(routes.process_due_payments()) == 1
    [(payload,)] = q("SELECT payload FROM outbox")
    p = json.loads(payload)["envelope"]["payload"]
    assert (p["purpose"], p["reference_type"], p["reference_id"], p["amount_paise"]) == (
        "CLAIM_SETTLEMENT", "claim", "CLM-1", 60000000)
    assert q("SELECT status FROM payables")[0][0] == "DUE"   # challans untouched


def test_claim_return_names_the_claim(ctx):
    client, routes, q, _ = ctx

    async def deliver():
        import app.infra.db as db
        async with db.sessions()() as s, s.begin():
            await routes.dispatch(s, {"event_type": "PaymentInstructed.v1", "payload": {
                "claim_id": "CLM-2", "payment_id": "PAY-CLM-2-1", "amount_paise": 100, "attempt": 1, "demo_scenario": "RETURN"}})
    asyncio.run(deliver())
    routes_done = asyncio.run(routes.process_due_payments())
    [(payload,)] = q("SELECT payload FROM outbox")
    p = json.loads(payload)["envelope"]["payload"]
    assert routes_done == 1 and p["reference"] == "CLM-2" and p["purpose"] == "CLAIM_SETTLEMENT"


def _dispatch(routes, event):
    async def run():
        import app.infra.db as db
        async with db.sessions()() as s, s.begin():
            await routes.dispatch(s, event)
    asyncio.run(run())


def test_a_stuck_payment_is_rejected_by_the_office_and_paid_again(ctx):
    client, routes, q, _ = ctx
    r = client.post(f"/api/v1/employers/me/challans/{TRRN}/payment-intents", json={"channel": "NET_BANKING", "demo_scenario": "STUCK"},
                    headers=hdr(key="k1", step_up=STEP))
    assert r.status_code == 202
    assert asyncio.run(routes.process_due_payments()) == 0                       # the bank never answers
    _dispatch(routes, {"event_type": "ChallanStatusChanged.v1", "payload": {"trrn": TRRN, "status": "PAYMENT_REJECTED", "reason": "stuck"}})
    assert q("SELECT status FROM payment_intents") == [("REJECTED",)] and q("SELECT status FROM payables")[0][0] == "FAILED"
    assert pay(client, key="k2", step_up=STEP).status_code == 202                   # paid again


def test_direct_challans_become_payable_and_cancelled_ones_cannot_be_paid(ctx):
    client, routes, q, _ = ctx
    _dispatch(routes, {"event_type": "ChallanGenerated.v1", "payload": {"trrn": "TRRN0000000000099", "establishment_id": EST,
                                                                         "kind": "DIRECT_ADMIN", "total_paise": 50000, "reference_id": "TRRN0000000000099"}})
    assert q("SELECT total_paise, status FROM payables WHERE trrn='TRRN0000000000099'") == [(50000, "DUE")]
    _dispatch(routes, {"event_type": "ChallanStatusChanged.v1", "payload": {"trrn": TRRN, "status": "CANCELLED", "reason": "wrong month"}})
    r = pay(client, key="k3", step_up=STEP)
    assert r.status_code == 409 and r.json()["type"] == "/problems/challan-cancelled"
