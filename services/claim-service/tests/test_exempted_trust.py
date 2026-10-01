"""The synthetic trust settles PF claims and sends Annexure K for a trust-to-EPFO transfer."""
import json
from datetime import date

from epfo_persistence.policy import baseline

from app.domain.claims import eligibility
from tests.test_claims_api import SEED, SUBJECTS, ctx, hdr  # noqa: F401

TRUST_SUBJECT = SEED["exempted_establishment"]["trust_users"][0]["subject"]


def test_only_pf_claim_types_of_an_exempted_member_id_go_to_the_trust():
    account = {"employee_paise": 4_000_000, "employer_paise": 2_000_000,
               "date_of_joining": date(2020, 1, 1), "date_of_exit": None,
               "exemption": {"pf_exempt": True, "status": "ACTIVE", "effective_from": date(2005, 4, 1),
                             "trust_name": "Demo Steel Works Employees' Provident Fund Trust"}}
    blocked = eligibility(account, "ADVANCE_ILLNESS", baseline(), date(2026, 10, 1))
    assert not blocked["eligible"]
    assert any("the trust settles it within 20 days (Condition 12)" in r for r in blocked["reasons"])
    assert eligibility({**account, "exemption": None}, "ADVANCE_ILLNESS", baseline(), date(2026, 10, 1))["eligible"]
    assert not any("with the trust" in r for r in eligibility(
        account, "PENSION_WITHDRAWAL", baseline(), date(2026, 10, 1))["reasons"])


def test_seeded_member_id_uses_the_exemption_copy(ctx):
    client, q, _ = ctx
    assert q("SELECT establishment_id FROM accounts WHERE account_link_id='AL-0915'") == [("EST-DEMO-0004",)]
    rows = client.get("/api/v1/members/me/claims/eligible-types",
                      headers=hdr(SUBJECTS["member-p"], "member")).json()["data"]["accounts"]
    own = next(r for r in rows if r["account_link_id"] == "AL-0915")
    illness = next(r for r in own["types"] if r["claim_type"] == "ADVANCE_ILLNESS")
    assert not illness["eligible"] and any("Condition 12" in r for r in illness["reasons"])
    other = next(r for r in rows if r["account_link_id"] == "AL-0914")
    other_illness = next(r for r in other["types"] if r["claim_type"] == "ADVANCE_ILLNESS")
    assert not any("with the trust" in r for r in other_illness["reasons"])


def _request(deliver, transfer="CASE-TRUST-1", establishment="EST-DEMO-0004"):
    deliver("TrustTransferRequested.v1", {"transfer_id": transfer, "uan": "100000000912",
            "from_account_link_id": "AL-0918", "to_account_link_id": "AL-0919",
            "establishment_id": establishment, "trust_id": "TRUST-DEMO-0004"}, "contribution-service")


def test_request_is_projected_once_and_only_mapped_trust_can_see_it(ctx):
    client, q, deliver = ctx
    _request(deliver)
    _request(deliver)
    assert q("SELECT count(*) FROM annexure_k_requests WHERE transfer_id='CASE-TRUST-1'") == [(1,)]
    rows = client.get("/api/v1/exempted/me/annexure-k-requests", headers=hdr(TRUST_SUBJECT, "exempted.trust")).json()["data"]["requests"]
    assert len(rows) == 1 and rows[0]["state"] == "REQUESTED" and rows[0]["annexure_id"].startswith("AKT-")
    assert client.get("/api/v1/exempted/me/annexure-k-requests", headers=hdr("another-trust", "exempted.trust")).status_code == 403
    _request(deliver, "CASE-OTHER", "EST-OTHER")
    rows = client.get("/api/v1/exempted/me/annexure-k-requests", headers=hdr(TRUST_SUBJECT, "exempted.trust")).json()["data"]["requests"]
    assert len(rows) == 1


def test_submission_replay_state_guard_and_reconciliation(ctx):
    client, q, deliver = ctx
    _request(deliver)
    annexure = q("SELECT annexure_id FROM annexure_k_requests WHERE transfer_id='CASE-TRUST-1'")[0][0]
    url = "/api/v1/exempted/me/annexure-k-submissions"
    body = {"annexure_id": annexure, "employee_paise": 120000, "employer_paise": 80000,
            "service_from": "2020-01-01", "service_to": "2026-06-30", "breaks_months": 2}
    trust = hdr(TRUST_SUBJECT, "exempted.trust", **{"Idempotency-Key": "submit-1"})
    assert client.post(url, json=body, headers=hdr(TRUST_SUBJECT, "exempted.trust")).status_code == 400
    assert client.post(url, json=body, headers=hdr("another-trust", "exempted.trust", **{"Idempotency-Key": "other"})).status_code == 403
    first = client.post(url, json=body, headers=trust)
    assert first.status_code == 201 and first.json()["data"]["state"] == "SUBMITTED"
    assert client.post(url, json=body, headers=trust).json()["data"] == first.json()["data"]                # the replay returns the stored data
    assert client.post(url, json=body, headers=hdr(TRUST_SUBJECT, "exempted.trust", **{"Idempotency-Key": "submit-2"})).status_code == 409
    reco = f"/api/v1/office/exempted/annexure-k/{annexure}/reconciliations"
    da = SUBJECTS["do-caseworker"]
    assert client.post(reco, json={"receipt_ref": "R1", "received_paise": 199999},
                       headers=hdr(da, "fo.da_accounts")).status_code == 428
    step = {"action": "reconcile-trust-annexure-k", "resource_id": annexure, "amount_paise": 200000}
    mismatch = client.post(reco, json={"receipt_ref": "R1", "received_paise": 199999},
                           headers=hdr(da, "fo.da_accounts", step))
    assert mismatch.status_code == 200 and mismatch.json()["data"]["difference_paise"] == -1
    assert mismatch.json()["data"]["state"] == "MISMATCH"
    assert q("SELECT count(*) FROM outbox WHERE event_type='TrustAnnexureKReconciled.v1'") == [(0,)]
    matched = client.post(reco, json={"receipt_ref": "R2", "received_paise": 200000},
                          headers=hdr(da, "fo.da_accounts", step))
    assert matched.status_code == 200 and matched.json()["data"]["state"] == "MATCHED"
    assert client.post(reco, json={"receipt_ref": "R2", "received_paise": 200000},
                       headers=hdr(da, "fo.da_accounts", step)).status_code == 409
    payload = json.loads(q("SELECT payload FROM outbox WHERE event_type='TrustAnnexureKReconciled.v1'")[0][0])["envelope"]["payload"]
    assert payload == {"annexure_id": annexure, "transfer_id": "CASE-TRUST-1", "to_account_link_id": "AL-0919",
                       "employee_paise": 120000, "employer_paise": 80000, "service_from": "2020-01-01",
                       "service_to": "2026-06-30", "breaks_months": 2}



def test_the_office_lists_the_trusts_annexure_k_awaiting_reconciliation(ctx):
    client, q, deliver = ctx
    _request(deliver)
    annexure = q("SELECT annexure_id FROM annexure_k_requests WHERE transfer_id='CASE-TRUST-1'")[0][0]
    da = hdr(SUBJECTS["do-caseworker"], "fo.da_accounts")
    url = "/api/v1/office/exempted/annexure-k"
    assert client.get(url, headers=da).json()["data"]["annexure_k"] == []                    # requested, not yet submitted
    client.post("/api/v1/exempted/me/annexure-k-submissions", json={"annexure_id": annexure, "employee_paise": 120000, "employer_paise": 80000,
                "service_from": "2020-01-01", "service_to": "2026-06-30", "breaks_months": 2},
                headers=hdr(TRUST_SUBJECT, "exempted.trust", **{"Idempotency-Key": "submit-list"}))
    [item] = client.get(url, headers=da).json()["data"]["annexure_k"]
    assert item["annexure_id"] == annexure and item["submitted_total_paise"] == 200000
    assert client.get(url, headers=hdr(TRUST_SUBJECT, "exempted.trust")).status_code == 403
