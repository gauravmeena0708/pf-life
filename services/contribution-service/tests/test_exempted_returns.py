"""Exempt trust return arithmetic, evaluator, seeded history and office actions."""
from datetime import date

import pytest

from tests.test_ecr_api import SEED, ctx, hdr  # noqa: F401


EX = SEED["exempted_establishment"]["establishment_id"]
SUBJECT = SEED["exempted_establishment"]["trust_users"][0]["subject"]
SOURCE = SEED["trust_returns"]["returns"][1]


def payload(month="2026-09", **changes):
    body = {**SOURCE, "wage_month": month, "pending_reasons": "Awaiting bank details"}
    body.update(changes)
    return body


def trust_headers():
    return hdr(SUBJECT, "exempted.trust", [], establishment=None)


def office_headers(office="RO-DEMO-01", step_up=None, stakeholder="fo.exemption"):
    # hdr's extras are headers; the office claim belongs in the signed JWT.
    import time
    import uuid
    import jwt
    from tests.conftest import KEY, KID
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "contribution-service", "sub": "officer-1",
              "stakeholder": stakeholder, "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()),
              "correlation_id": str(uuid.uuid4()), "office_id": office}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_evaluator_parts_and_edge_cases():
    from app.api.exempted_returns_routes import ReturnInput, evaluate, validate
    from epfo_observability import Problem
    body = ReturnInput(**payload(transfers=[{"date": "2026-10-15", "amount_paise": SOURCE["due_paise"] // 2},
                                 {"date": "2026-10-22", "amount_paise": SOURCE["due_paise"] // 2}]))
    settings = {"return_due_day": 15, "investment_threshold_pct": 70}
    parts, due, late, pending = evaluate(body, settings, 850)
    assert parts == {"transfer_before_due_date": 50.0, "investment": 94.3,
                     "remittance": 100.0, "interest_declared": 100.0,
                     "claim_settlement": 52.6, "audit_of_accounts": 100.0}
    assert (due, late, pending) == (0, 7, 12)
    zero = ReturnInput(**payload(due_paise=0, employee_share_paise=0, employer_share_paise=0,
                                 transfers=[], claims_opening=0, claims_received=0, claims_within_days=0,
                                 claims_beyond_days=0, pending_reasons=None, investible_corpus_paise=0,
                                 invested_paise=0, accounts_audited=False, interest_rate_declared_bp=425))
    parts, due, late, pending = evaluate(zero, settings, 850)
    assert parts == {"transfer_before_due_date": 100.0, "investment": 0.0, "remittance": 100.0,
                     "interest_declared": 50.0, "claim_settlement": 100.0, "audit_of_accounts": 0.0}
    assert (due, late, pending) == (0, 0, 0)
    for invalid in (payload(joined=4), payload(due_paise=1), payload(pending_reasons=None),
                    payload(transfers=[{"date": "2026-06-01", "amount_paise": 1}])):
        with pytest.raises(Problem):
            validate(ReturnInput(**invalid), date(2005, 4, 1))


def test_seeded_returns_and_ranking(ctx):
    client, q = ctx
    own = client.get("/api/v1/exempted/me/returns", headers=trust_headers())
    assert own.status_code == 200, own.json()
    rows = own.json()["data"]["returns"]
    assert [r["wage_month"] for r in rows] == ["2026-08", "2026-07", "2026-06"]
    july = rows[1]
    assert july["late_transfer_days"] == 7
    assert {f["code"] for f in july["flags"]} >= {"CLAIMS_LATE"}
    assert "NO_RETURNS" not in {f["code"] for f in rows[2]["flags"]}          # online returns start with the first one filed
    assert july["parts"]["transfer_before_due_date"] == 0.0
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='TrustReturnFiled.v1'")[0][0] == 0      # a seeded history publishes nothing
    office = client.get(f"/api/v1/office/exempted/{EX}/returns", headers=office_headers())
    assert office.status_code == 200 and len(office.json()["data"]["returns"]) == 3
    assert client.get(f"/api/v1/office/exempted/{EX}/returns", headers=office_headers("OTHER")).status_code == 403
    ranking = client.get("/api/v1/office/exempted/rankings?month=2026-05", headers=office_headers())
    assert ranking.status_code == 200, ranking.json()
    missing = next(r for r in ranking.json()["data"]["rankings"] if r["establishment_id"] == EX)
    assert missing["score"] == 0 and "NO_RETURN" in missing["flags"] and "NO_RETURNS" not in missing["flags"]   # before the first online return
    assert client.get("/api/v1/exempted/me/returns", headers=office_headers()).status_code == 403


def test_revision_flags_and_step_up(ctx):
    client, q = ctx
    url = "/api/v1/exempted/me/returns"
    body = payload(claims_beyond_days=0, claims_within_days=38, pending_reasons=None,
                   transfers=[{"date": "2026-10-15", "amount_paise": SOURCE["due_paise"]}])
    first = client.post(url, json=body, headers=trust_headers())
    assert first.status_code == 201, first.json()
    assert client.post(url, json=body, headers=trust_headers()).status_code == 409
    revised = client.post(url, json={**body, "revised": True, "claims_beyond_days": 1,
                                    "claims_within_days": 36, "pending_reasons": None}, headers=trust_headers())
    assert revised.status_code == 422
    revised = client.post(url, json={**body, "revised": True, "claims_beyond_days": 1,
                                    "claims_within_days": 36, "pending_reasons": "Awaiting bank details"}, headers=trust_headers())
    assert revised.status_code == 201, revised.json()
    item = revised.json()["data"]
    assert item["version"] == 2 and "CLAIMS_LATE" in {f["code"] for f in item["flags"]}
    assert q(f"SELECT state FROM trust_returns WHERE return_id='{first.json()['data']['return_id']}'")[0][0] == "SUPERSEDED"
    flag = next(f for f in item["flags"] if f["code"] == "CLAIMS_LATE")
    action_url = f"/api/v1/office/exempted/{EX}/flags/{flag['flag_id']}/actions"
    action = {"action": "ADVICE", "note": "Please correct"}
    assert client.post(action_url, json=action, headers=office_headers()).status_code == 428
    step = {"action": "action-trust-flag", "resource_id": flag["flag_id"]}
    assert client.post(action_url, json=action, headers=office_headers(step_up=step)).status_code == 422
    done = client.post(action_url, json={"action": "SHOW_CAUSE_NOTICE", "note": "Explain late claims"},
                       headers=office_headers(step_up=step))
    assert done.status_code == 200, done.json()
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='TrustFlagActioned.v1'")[0][0] == 1
    assert client.post(action_url, json=action, headers=trust_headers()).status_code == 403
    # a further revision cannot erase the show-cause, nor raise the same flag again
    third = client.post(url, json={**body, "revised": True, "claims_beyond_days": 2, "claims_within_days": 35,
                                   "pending_reasons": "Awaiting bank details"}, headers=trust_headers())
    assert third.status_code == 201, third.json()
    late = [f for f in third.json()["data"]["flags"] if f["code"] == "CLAIMS_LATE"]
    assert len(late) == 1 and late[0]["action"] == "SHOW_CAUSE_NOTICE"
    listed = client.get(url, headers=trust_headers()).json()["data"]["returns"]
    september = [r for r in listed if r["wage_month"] == "2026-09"]
    assert [(r["version"], r["state"]) for r in september] == [(3, "FILED"), (2, "SUPERSEDED"), (1, "SUPERSEDED")]
    assert september[1]["flags"] == []


def test_three_low_scores_and_reconciliation(ctx, monkeypatch):
    client, _ = ctx
    import app.api.exempted_returns_routes as routes

    async def passbook(_session, _account, _exemption, *, commit=False):
        return {"balance": {"employee_paise": 1, "employer_paise": 1}}

    monkeypatch.setattr(routes, "trust_section", passbook)
    for month in ("2026-06", "2026-07", "2026-08"):
        year, m = map(int, month.split("-"))
        transfer_date = f"{year + (m == 12)}-{m % 12 + 1:02d}-16"
        body = payload(month, revised=True, transfers=[{"date": transfer_date, "amount_paise": 1}],
                       investible_corpus_paise=100, invested_paise=0, interest_rate_declared_bp=0,
                       claims_within_days=0, claims_beyond_days=1, accounts_audited=False,
                       member_balances_total_paise=999)
        response = client.post("/api/v1/exempted/me/returns", json=body, headers=trust_headers())
        assert response.status_code == 201, response.json()
    codes = {f["code"] for f in response.json()["data"]["flags"]}
    assert codes >= {"LOW_SCORE", "PF_DUES_DEFAULT", "CLAIMS_LATE", "INTEREST_BELOW_EPFO", "RECONCILIATION"}
    assert client.get("/api/v1/office/exempted/rankings?month=2026-08", headers=office_headers(stakeholder="ho.exemption")).status_code == 200
    assert client.post("/api/v1/exempted/me/returns", json=payload("2026-10"), headers=office_headers()).status_code == 403


def test_three_months_without_a_return_after_the_first_one_is_category_a(ctx):
    """NO_RETURNS counts from the trust's first online return: here returns stop after May and resume in September."""
    client, q = ctx
    import asyncio
    import app.infra.db as db
    from sqlalchemy import text

    async def make_gap():
        async with db.engine().begin() as c:
            await c.execute(text("DELETE FROM trust_returns WHERE establishment_id=:e AND wage_month IN ('2026-07','2026-08')"), {"e": EX})
            await c.execute(text("UPDATE trust_returns SET wage_month='2026-05' WHERE establishment_id=:e AND wage_month='2026-06'"), {"e": EX})
    asyncio.run(make_gap())
    body = payload("2026-09", transfers=[{"date": date.today().isoformat(), "amount_paise": SOURCE["due_paise"]}])
    filed = client.post("/api/v1/exempted/me/returns", json=body, headers=trust_headers())
    assert filed.status_code in (200, 201), filed.json()
    assert "NO_RETURNS" in {f["code"] for f in filed.json()["data"]["flags"]}          # June, July and August missing
