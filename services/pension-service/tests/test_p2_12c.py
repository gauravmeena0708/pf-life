"""Office higher pension steps, special cases and limited reporting."""
import asyncio
import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.test_higher_pension import DUES, UAN, employer, hdr, submit, validation_body
from tests.test_pensions import SUBJECTS, ctx  # noqa: F401

APFC = SUBJECTS["ro-pension"]
ACCOUNTS = SUBJECTS["do-caseworker"]
DA = SUBJECTS["ro-da-pension"]
LIST_OFFICER = SUBJECTS["ro-pension-disbursement"]
ACTUARY = SUBJECTS["ho-actuarial"]
BASE = "/api/v1/office/pensions/higher-pension-options"


def validated(client):
    option = submit(client)
    oid = option["option_id"]
    response = client.post(f"/api/v1/employers/me/higher-pension-options/{oid}/validations", json=validation_body(),
                           headers=employer({"action": "validate-higher-pension", "resource_id": oid, "amount_paise": DUES}))
    assert response.status_code == 200, response.text
    return oid


def decide(client, oid, decision="APPROVE"):
    return client.post(f"{BASE}/{oid}/decisions", json={"decision": decision, "note": "Payroll evidence reviewed"},
                       headers=hdr(APFC, "fo.apfc_pension", {"action": "decide-higher-pension", "resource_id": oid,
                                                               "amount_paise": DUES}))


def transfer(client, oid, key="transfer-1"):
    headers = hdr(ACCOUNTS, "fo.da_accounts", {"action": "transfer-higher-pension-dues", "resource_id": oid,
                                                "amount_paise": DUES})
    headers["Idempotency-Key"] = key
    return client.post(f"{BASE}/{oid}/ledger-transfers", headers=headers)


def event_payload(q, event_type):
    return [json.loads(row[0])["envelope"]["payload"] for row in q(
        f"SELECT payload FROM outbox WHERE event_type='{event_type}'")]


def test_decisions_are_guarded_scoped_and_notify(ctx):
    client, q, _ = ctx
    oid = validated(client)
    url = f"{BASE}/{oid}/decisions"
    body = {"decision": "APPROVE", "note": "Payroll evidence reviewed"}
    assert client.post(url, json=body, headers=hdr(APFC, "fo.apfc_pension")).status_code == 428
    assert client.post(url, json=body, headers=hdr(ACCOUNTS, "fo.da_accounts")).status_code == 403
    response = decide(client, oid)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "APPROVED"
    assert "PF" in response.json()["data"]["next_step"]
    assert event_payload(q, "HigherPensionOptionDecided.v1") == [
        {"option_id": oid, "uan": UAN, "account_link_id": "AL-0907", "decision": "APPROVE", "dues_paise": DUES}]
    assert event_payload(q, "NotificationRequested.v1")[-1]["template"] == "HIGHER_PENSION_APPROVED"
    assert decide(client, oid).status_code == 409
    assert transfer(client, oid).status_code == 200


def test_rejection_and_transfer_state_guards(ctx):
    client, q, _ = ctx
    oid = validated(client)
    assert transfer(client, oid).status_code == 409
    assert decide(client, oid, "REJECT").json()["data"]["state"] == "REJECTED_BY_OFFICE"
    assert transfer(client, oid).status_code == 409
    assert event_payload(q, "NotificationRequested.v1")[-1]["template"] == "HIGHER_PENSION_REJECTED_BY_OFFICE"


@pytest.mark.parametrize("status,state", [("POSTED", "DUES_TRANSFERRED"),
                                          ("INSUFFICIENT_BALANCE", "TRANSFER_FAILED")])
def test_transfer_consumer_is_idempotent(ctx, status, state):
    client, q, _ = ctx
    oid = validated(client)
    assert decide(client, oid).status_code == 200
    url = f"{BASE}/{oid}/ledger-transfers"
    assert client.post(url, headers=hdr(APFC, "fo.apfc_pension")).status_code == 403
    assert client.post(url, headers=hdr(ACCOUNTS, "fo.da_accounts")).status_code == 400
    first = transfer(client, oid)
    assert first.status_code == 200, first.text
    assert transfer(client, oid).json()["data"] == first.json()["data"]                  # the replay returns the stored data
    assert transfer(client, oid, "different-key").status_code == 409
    assert event_payload(q, "HigherPensionDuesTransferRequested.v1") == [
        {"option_id": oid, "uan": UAN, "account_link_id": "AL-0907", "amount_paise": DUES}]
    from app.infra.messaging import dispatch
    from app.infra.db import sessions
    from epfo_persistence.consumer import apply_once
    event = {"event_id": str(uuid.uuid4()), "event_type": "HigherPensionTransferPosted.v1",
             "producer": "contribution-service", "correlation_id": str(uuid.uuid4()),
             "payload": {"option_id": oid, "status": status,
                         "posted_paise": DUES if status == "POSTED" else 0,
                         "journal_id": "J-1" if status == "POSTED" else None}}
    asyncio.run(apply_once(sessions(), event, dispatch))
    asyncio.run(apply_once(sessions(), event, dispatch))
    assert q(f"SELECT state FROM higher_pension_options WHERE option_id='{oid}'") == [(state,)]
    assert event_payload(q, "NotificationRequested.v1")[-1]["template"] == "HIGHER_PENSION_" + state
    if state == "TRANSFER_FAILED":
        assert "VDR" in client.get(f"/api/v1/members/me/higher-pension-options/{oid}",
                                   headers=hdr(SUBJECTS["member-h"], "member")).json()["data"]["next_step"]


def test_special_10d_case_validation_and_one_open_case(ctx):
    client, q, _ = ctx
    url = "/api/v1/office/pensions/special-10d-cases"
    body = {"uan": UAN, "missing": ["SERVICE_PERIOD", "WAGES"],
            "details": "Old service and wage records are incomplete.",
            "evidence": [{"kind": "SERVICE_RECORD", "ref": "SR-1"}]}
    assert client.post(url, json=body, headers=hdr(APFC, "fo.apfc_pension")).status_code == 403
    invalid = client.post(url, json={**body, "missing": []}, headers=hdr(DA, "fo.da_pension"))
    assert invalid.status_code == 400                                   # the shared handler answers schema errors with 400
    response = client.post(url, json=body, headers=hdr(DA, "fo.da_pension"))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["state"] == "OPEN" and len(data["checklist"]) == 2 and "APFC" in data["next_step"]
    assert client.post(url, json=body, headers=hdr(DA, "fo.da_pension")).status_code == 409
    assert q("SELECT COUNT(*) FROM special_10d_cases") == [(1,)]
    assert q("SELECT COUNT(*) FROM audit_local WHERE action='pension.special_10d_opened'") == [(1,)]


def test_disbursement_lists_are_monthly_and_office_scoped(ctx):
    client, q, _ = ctx
    month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    url = f"/api/v1/office/pensions/disbursement-lists?month={month}"
    assert client.get(url, headers=hdr(APFC, "fo.apfc_pension")).status_code == 403
    assert client.get(url.replace(month, "2026-13"), headers=hdr(LIST_OFFICER, "fo.pension_disbursement")).status_code == 422
    response = client.get(url, headers=hdr(LIST_OFFICER, "fo.pension_disbursement"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    expected = q(f"SELECT COUNT(*), SUM(amount_paise) FROM pension_payments WHERE month='{month}' AND kind='MONTHLY'")
    assert data["totals"] == {"pensioners": expected[0][0], "amount_paise": int(expected[0][1])}
    assert data["banks"][0]["bank"] == "DEMO" and "name_masked" in data["banks"][0]["items"][0]
    assert client.get("/api/v1/office/pensions/disbursement-lists", headers=hdr(LIST_OFFICER, "fo.pension_disbursement")).json()["data"]["month"] == month


def test_actuarial_extract_has_no_direct_identifiers(ctx):
    client, q, _ = ctx
    oid = validated(client)
    url = "/api/v1/ho/actuarial/extracts?as_of=2026-09-30"
    assert client.get(url, headers=hdr(APFC, "fo.apfc_pension")).status_code == 403
    response = client.get(url, headers=hdr(ACTUARY, "ho.actuarial"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert {r["category"] for r in data["rows"]} == {"PENSIONER", "HIGHER_PENSION_OPTION"}
    assert all(set(r) == {"record_id", "category", "age_years", "gender", "pension_start_year",
                          "monthly_pension_paise", "service_months", "status"} for r in data["rows"])
    assert all(len(r["record_id"]) == 16 for r in data["rows"])
    raw = json.dumps(data)
    assert UAN not in raw and oid not in raw and "PPO-DEMO" not in raw and "GOPAL" not in raw
    assert data["aggregates"] and data["rule_version"]
    assert q("SELECT COUNT(*) FROM audit_local WHERE action='pension.actuarial_extract'") == [(1,)]


def test_the_office_lists_its_options_by_state(ctx):
    client, q, _ = ctx
    oid = validated(client)
    listed = client.get("/api/v1/office/pensions/higher-pension-options?state=VALIDATED", headers=hdr(APFC, "fo.apfc_pension")).json()["data"]
    assert [o["option_id"] for o in listed] == [oid]
    assert client.get("/api/v1/office/pensions/higher-pension-options?state=APPROVED", headers=hdr(APFC, "fo.apfc_pension")).json()["data"] == []
    assert client.get("/api/v1/office/pensions/higher-pension-options", headers=hdr(ACCOUNTS, "fo.da_accounts")).status_code == 200
    assert client.get("/api/v1/office/pensions/higher-pension-options", headers=hdr(DA, "fo.da_pension")).status_code == 403
