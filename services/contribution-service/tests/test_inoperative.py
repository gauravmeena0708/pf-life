"""P2.12a: shared eligibility, office approval and demo public lookup."""
import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401

ACCOUNT = "AL-0002"
BASE = "/api/v1/office/accounts/inoperative"
APPROVE = f"/api/v1/office/accounts/{ACCOUNT}/reactivations"
SEARCH = "/api/v1/public/inoperative-accounts/searches"


def sql(statement, params=None):
    import app.infra.db as db

    async def run():
        async with db.engine().begin() as conn:
            result = await conn.execute(text(statement), params or {})
            return result.all() if result.returns_rows else result.rowcount
    return asyncio.run(run())


def listed(response):
    """The accounts this test works on: all but the seeded inoperative ones (MOHAN DEMO's AL-0913, PRIYA DEMO's AL-0914)."""
    return [a for a in response.json()["data"]["accounts"] if a["account_link_id"] not in ("AL-0913", "AL-0914")]


def old_account():
    sql("UPDATE journals SET occurred_at='2020-03-31 23:59:59' WHERE business_key='OPENING-AL-0002'")


def office(role="fo.ao", amount=None):
    step = {"action": "reactivate-account", "resource_id": ACCOUNT, "amount_paise": amount} if amount is not None else None
    return hdr("officer-1", role, [], step, establishment=None)


def verified():
    from app.infra.messaging import handle_inoperative_verified
    payload = {"account_link_id": ACCOUNT, "uan": "100000000002", "co_workers": 2, "verified_by_office": "FO-1"}
    applied, event = _deliver(handle_inoperative_verified, payload, "InoperativeAccountVerified.v1")
    return applied, event


def test_list_rule_flags_and_reactivation(ctx):
    client, q = ctx
    old_account()
    da = hdr("da-1", "fo.da_accounts", [], establishment=None)
    before = client.get(BASE, headers=da)
    assert before.status_code == 200, before.json()
    for role in ("fo.ao", "fo.apfc"):
        assert client.get(BASE, headers=office(role)).status_code == 200
    assert before.json()["data"]["months"] == 36
    account = next(a for a in before.json()["data"]["accounts"] if a["account_link_id"] == ACCOUNT)   # besides the seeded AL-0913
    assert account["account_link_id"] == ACCOUNT and account["verified"] is False and account["reactivated"] is False
    balance = account["balance_paise"]
    from epfo_persistence.policy import baseline
    published = {**baseline(), "rule_version": "inoperative-test", "inoperative_accounts":
                 {**baseline()["inoperative_accounts"], "months_without_credit": 120}}
    sql("INSERT INTO policy_rules (rule_version,effective_from,document) VALUES ('inoperative-test','2026-01-01',:doc)",
        {"doc": json.dumps(published)})
    assert listed(client.get(BASE, headers=da)) == []
    assert listed(client.get(BASE + "?months=36", headers=da))[0]["account_link_id"] == ACCOUNT
    sql("DELETE FROM policy_rules WHERE rule_version='inoperative-test'")
    unverified = client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Checked"}, headers=office(amount=balance))
    assert unverified.status_code == 409 and unverified.json()["type"] == "/problems/not-verified"
    assert unverified.json()["next_step"] == "verification through co-workers"
    applied, event = verified()
    assert applied
    import app.infra.db as db
    from app.infra.messaging import handle_inoperative_verified
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), event, handle_inoperative_verified)) is False
    flagged = listed(client.get(BASE, headers=da))[0]
    assert flagged["verified"] is True
    approved = client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Verified in office"}, headers=office(amount=balance))
    assert approved.status_code == 200, approved.json()
    assert listed(client.get(BASE, headers=da)) == []
    included = listed(client.get(BASE + "?include_reactivated=true", headers=da))
    assert included[0]["reactivated"] is True
    assert client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Again"}, headers=office(amount=balance)).json()["type"] == "/problems/already-reactivated"
    assert len(q("SELECT id FROM outbox WHERE event_type='AccountReactivated.v1'")) == 1
    assert len(q("SELECT id FROM audit_local WHERE action='account.reactivated'")) == 1


def test_not_inoperative_and_ao_band(ctx):
    client, q = ctx
    assert client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Attempt"}, headers=office()).json()["type"] == "/problems/not-inoperative"
    old_account()
    verified()
    sql("UPDATE journal_lines SET amount_paise=60000000 WHERE journal_id=(SELECT id FROM journals WHERE business_key='OPENING-AL-0002') AND account_code='AC01_EPF'")
    da = hdr("da-1", "fo.da_accounts", [], establishment=None)
    amount = listed(client.get(BASE, headers=da))[0]["balance_paise"]
    denied = client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Attempt"}, headers=office(amount=amount))
    assert denied.status_code == 403 and denied.json()["type"] == "/problems/above-your-band"
    assert "APFC" in denied.json()["detail"]
    allowed = client.post(APPROVE, json={"decision": "REACTIVATE", "note": "Approved"}, headers=office("fo.apfc", amount))
    assert allowed.status_code == 200, allowed.json()


def test_public_search_otp_and_expiry(ctx):
    client, q = ctx
    old_account()
    member = next(m for m in SEED["members"] if m["account_link_id"] == ACCOUNT)
    est_name = q("SELECT legal_name FROM establishments WHERE id=(SELECT establishment_id FROM establishment_members WHERE account_link_id='AL-0002')")[0][0]
    public = hdr("anonymous-1", "public", [], establishment=None)
    first = client.post(SEARCH, json={"name": member["name"].upper(), "date_of_birth": member["date_of_birth"],
                                      "establishment_query": est_name[:5].lower()}, headers=public)
    assert first.status_code == 200, first.json()
    data = first.json()["data"]
    assert len(data["matches"]) == 1 and "balance_paise" not in str(data)
    ref = data["matches"][0]["search_ref"]
    wrong = client.post(SEARCH, json={"search_ref": ref, "otp": "000000" if data["demo"]["otp"] != "000000" else "111111"}, headers=public)
    assert wrong.status_code == 422
    unknown = client.post(SEARCH, json={"search_ref": "unknown", "otp": "123456"}, headers=public)
    assert unknown.status_code == 404
    second = client.post(SEARCH, json={"search_ref": ref, "otp": data["demo"]["otp"]}, headers=public)
    assert second.status_code == 200 and second.json()["data"]["balance_paise"] > 0
    assert "Visit your EPFO office" in second.json()["data"]["next_step"]
    sql("UPDATE inoperative_search_refs SET expires_at=:at WHERE search_ref=:r", {"at": datetime.now(UTC) - timedelta(minutes=1), "r": ref})
    expired = client.post(SEARCH, json={"search_ref": ref, "otp": data["demo"]["otp"]}, headers=public)
    assert expired.status_code == 404
    assert len(q("SELECT id FROM audit_local WHERE action LIKE 'inoperative_search.%'")) == 2
