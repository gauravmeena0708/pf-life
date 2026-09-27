"""contribution-service API tests on SQLite: prepare → validate → approve → submit, with grants,
step-up binding, separation of duties, If-Match and idempotent resubmission."""
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
EST = SEED["establishment"]["establishment_id"]
PREPARER, SIGNATORY = SEED["keycloak_subjects"]["emp-preparer"], SEED["keycloak_subjects"]["emp-signatory"]
MONTH = "2026-08"


def ecr_line(uan, name, wages=15000):
    ee, eps = round(wages * 0.12), round(min(wages, 15000) * 0.0833)
    return "#~#".join(map(str, [uan, name, wages, wages, min(wages, 15000), min(wages, 15000), ee, eps, ee - eps, 0, 0]))


GOOD = "\n".join(ecr_line(m["uan"], m["name"]) for m in SEED["members"][:3])


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/contribution.db")
    monkeypatch.setenv("SEED_FILE", str(ROOT / "scripts" / "seed" / "synthetic.json"))
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base

    async def setup():
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            from epfo_persistence.policy import policy_metadata
            await c.run_sync(policy_metadata.create_all)
        from app.seed import seed
        await seed()
        async with db.engine().begin() as c:
            await c.execute(text("UPDATE establishments SET status='VERIFIED' WHERE id=:e"), {"e": EST})
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="contribution-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())
    yield TestClient(application, raise_server_exceptions=False), q
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, grants, step_up=None, establishment=EST, **extra):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "contribution-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
              "grants": list(grants), "establishment_id": establishment}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID}), **extra}


def preparer(**kw):
    return hdr(PREPARER, "employer.operator", ["ecr.prepare"], **kw)


def signatory(step_up=None, **kw):
    return hdr(SIGNATORY, "employer.signatory", ["ecr.approve", "ecr.submit", "payment.initiate"], step_up, **kw)


def upload(client, content=GOOD, **kw):
    return client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": content},
                       headers=preparer(**kw))


def approved(client):
    r = upload(client).json()["data"]
    f, total = r["filing"], r["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    step = {"action": "approve-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", json={"decision": "APPROVE"},
                       headers=signatory(step)).status_code == 200
    return f, total


def test_upload_needs_prepare_grant(ctx):
    client, _ = ctx
    r = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": GOOD},
                    headers=hdr(PREPARER, "employer.operator", []))
    assert r.status_code == 403 and r.json()["type"] == "/problems/missing-grant"


def test_member_cannot_upload(ctx):
    client, _ = ctx
    r = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": GOOD},
                    headers=hdr(SIGNATORY, "member", ["ecr.prepare"]))
    assert r.status_code == 403


def test_valid_upload_is_validated_and_emits_event(ctx):
    client, q = ctx
    r = upload(client)
    assert r.status_code == 201, r.json()
    data = r.json()["data"]
    assert data["filing"]["state"] == "VALIDATED" and data["validation_report"]["summary"]["rows"] == 3
    assert [e[0] for e in q("SELECT event_type FROM outbox")] == ["ECRValidated.v1"]


def test_invalid_upload_reports_every_row_with_a_fix(ctx):
    client, _ = ctx
    bad = GOOD.replace("#~#1800#~#", "#~#1799#~#") + "\n" + ecr_line("999999999999", "NOBODY")
    report = upload(client, content=bad).json()["data"]["validation_report"]
    assert report["valid"] is False
    rows = {i["row"] for i in report["issues"]}
    assert len(rows) >= 2, report["issues"]  # did not stop at the first bad row
    assert all(i.get("fix") for i in report["issues"])


def test_preparer_cannot_approve_own_filing(ctx):
    client, _ = ctx
    f = upload(client).json()["data"]["filing"]
    both = hdr(PREPARER, "employer.signatory", ["ecr.prepare", "ecr.approve"],
               {"action": "approve-ecr", "resource_id": f["filing_id"]})
    r = client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", json={"decision": "APPROVE"}, headers=both)
    assert r.status_code == 403 and r.json()["type"] == "/problems/self-approval"


def test_approval_needs_step_up_bound_to_amount(ctx):
    client, _ = ctx
    r = upload(client).json()["data"]
    f, total = r["filing"], r["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    url = f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals"
    assert client.post(url, json={"decision": "APPROVE"}, headers=signatory()).status_code == 428
    wrong = {"action": "approve-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total + 1}
    assert client.post(url, json={"decision": "APPROVE"}, headers=signatory(wrong)).status_code == 403


def test_submit_rules_and_idempotent_resubmit(ctx):
    client, q = ctx
    f, total = approved(client)
    url = f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions"
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(url, headers=signatory(step, **{"If-Match": str(f["version"])})).status_code == 400  # no key
    assert client.post(url, headers=signatory(step, **{"Idempotency-Key": "k0", "If-Match": "99"})).status_code == 412
    first = client.post(url, headers=signatory(step, **{"Idempotency-Key": "k1", "If-Match": str(f["version"])}))
    again = client.post(url, headers=signatory(step, **{"Idempotency-Key": "k1", "If-Match": str(f["version"])}))
    assert first.status_code == 201 and again.status_code == 201
    assert first.json()["data"]["trrn"] == again.json()["data"]["trrn"]
    assert first.json()["data"]["total_paise"] == total
    assert len(q(f"SELECT * FROM challans WHERE filing_id='{f['filing_id']}'")) == 1
    assert [e[0] for e in q("SELECT event_type FROM outbox")].count("ECRSubmitted.v1") == 1
    other_key = client.post(url, headers=signatory(step, **{"Idempotency-Key": "k2", "If-Match": str(f["version"])}))
    assert other_key.status_code == 409  # already submitted: never a second challan


def test_other_establishment_sees_nothing(ctx):
    client, _ = ctx
    f = upload(client).json()["data"]["filing"]
    r = client.get(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}", headers=preparer(establishment="EST-OTHER"))
    assert r.status_code == 404


def test_same_month_cannot_be_filed_twice_after_submission(ctx):
    client, _ = ctx
    f, total = approved(client)
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                headers=signatory(step, **{"Idempotency-Key": "k", "If-Match": str(f["version"])}))
    r = upload(client)
    assert r.status_code == 409 and r.json()["type"] == "/problems/wage-month-already-filed"


def test_member_passbook_shows_filed_but_unpaid(ctx):
    client, _ = ctx
    f, total = approved(client)
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                headers=signatory(step, **{"Idempotency-Key": "k", "If-Match": str(f["version"])}))
    member = SEED["members"][0]
    r = client.get("/api/v1/members/me/passbook", headers=hdr(member["subject"], "member", [], establishment=None))
    assert r.status_code == 200, r.json()
    pending = r.json()["data"]["pending"]
    assert pending and pending[0]["wage_month"] == MONTH and "awaiting payment" in pending[0]["message"]
    assert client.get("/api/v1/members/me/passbook", headers=preparer()).status_code == 403


def _deliver(handler, payload, event_type):
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "correlation_id": str(uuid.uuid4()), "payload": payload}
    return asyncio.run(apply_once(db.sessions(), event, handler)), event


def test_opening_balance_claim_debit_and_settlement_balance_and_show_in_passbook(ctx):
    client, q = ctx
    from app.infra.claims_ledger import on_claim_decision, on_claim_paid
    member = SEED["members"][0]
    decision = {"claim_id": "CLM-1", "decision": "APPROVED", "reason_code": "OFFICER_APPROVED", "rule_version": "r",
                "amount_paise": 400000000, "account_link_id": member["account_link_id"]}  # more than the employee share
    applied, event = _deliver(on_claim_decision, decision, "ClaimDecisionRecorded.v1")
    assert applied
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), event, on_claim_decision)) is False           # redelivery: no second debit
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='ClaimDebitPosted.v1'")
    postings = json.loads(payload)["envelope"]["payload"]["postings"]
    assert [(p["account_code"], p["side"], p.get("share"), p["amount_paise"]) for p in postings] == [
        ("AC01_EPF", "debit", "employee", 360000000), ("AC01_EPF", "debit", "employer", 40000000),
        ("CLAIMS_PAYABLE", "credit", None, 400000000)]
    _deliver(on_claim_paid, {"payment_id": "PAY-CLM-1-1", "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                             "reference_id": "CLM-1", "amount_paise": 400000000, "mock": True}, "PaymentConfirmed.v1")
    for (debit, credit) in q("SELECT SUM(CASE WHEN side='debit' THEN amount_paise ELSE 0 END), "
                             "SUM(CASE WHEN side='credit' THEN amount_paise ELSE 0 END) FROM journal_lines GROUP BY journal_id"):
        assert debit == credit                                                                   # every journal balances
    book = client.get("/api/v1/members/me/passbook", headers=hdr(member["subject"], "member", [], establishment=None)).json()["data"]
    entries = book["accounts"][0]["entries"]
    assert [e["kind"] for e in entries] == ["OPENING_BALANCE", "WITHDRAWAL"]
    assert entries[0]["running_balance_paise"] == 600000000 and entries[-1]["running_balance_paise"] == 200000000


def test_claim_above_ledger_balance_is_refused(ctx):
    from app.infra.claims_ledger import on_claim_decision
    with pytest.raises(ValueError):
        _deliver(on_claim_decision, {"claim_id": "CLM-2", "decision": "APPROVED", "reason_code": "x", "rule_version": "r",
                                     "amount_paise": 10**12, "account_link_id": SEED["members"][0]["account_link_id"]},
                 "ClaimDecisionRecorded.v1")


def test_wage_ceiling_change_applies_from_its_wage_month(ctx):
    client, q = ctx
    import copy
    from epfo_persistence.policy import baseline, on_policy_published
    doc = copy.deepcopy(baseline())
    doc["contribution"].update(eps_wage_ceiling_paise=2500000, edli_wage_ceiling_paise=2500000)
    doc.update(rule_version="demo-rules-2026.2", effective_from="2026-10-01")
    _deliver(on_policy_published, {"version_id": "POL-1", "rule_version": "demo-rules-2026.2", "effective_from": "2026-10-01",
                                   "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc}, "PolicyPublished.v1")
    m = SEED["members"][0]
    ee, eps = 2400, round(20000 * 0.0833)                           # ₹20,000 wages, all of it under the new ceiling
    line = "#~#".join(map(str, [m["uan"], m["name"], 20000, 20000, 20000, 20000, ee, eps, ee - eps, 0, 0]))

    def file_for(month):
        return client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": month, "format": "ECR_TXT", "content": line},
                           headers=preparer()).json()["data"]
    september, october = file_for("2026-09"), file_for("2026-10")
    assert september["filing"]["rule_version"] == "demo-rules-2026.1" and september["validation_report"]["valid"] is False
    assert any(i["code"] == "E-EPS-CEILING" for i in september["validation_report"]["issues"])
    assert october["filing"]["rule_version"] == "demo-rules-2026.2" and october["validation_report"]["valid"] is True, october["validation_report"]["issues"]
