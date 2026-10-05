"""P2.19a: Attachment orders refused under EPF Act s.10.

A member's balance, a nominee's amount, pension and EDLI cannot be attached under any
court decree for the member's debt (EPF Act s.10). An office endpoint records received
attachment/garnishee orders and returns a refusal with the s.10 reason (and an exception
only for orders under the EPF Act itself — maintenance orders are NOT exempt in the POC:
refuse, citing s.10). Payments are never diverted.
"""
from datetime import date
from tests.test_claims_api import CASHIER, MEMBER_A, S_APFC, SUBJECTS, ctx, events, hdr, member


def test_attachment_order_court_decree_refused_under_epf_act_s10(ctx):
    """A civil court attachment order against a member's balance is refused under EPF Act s.10."""
    client, q, deliver = ctx
    legal_officer = SUBJECTS["ro-apfc"]

    order = {
        "order_number": "EXEC-COURT-2026-99",
        "court_name": "City Civil Court, Delhi",
        "order_date": "2026-09-15",
        "order_type": "COURT_DECREE",
        "amount_paise": 15000000,
        "target_uan": "100000000001",
        "debtor_name": "RAHUL SHARMA",
        "note": "Execution petition in commercial suit",
    }
    res = client.post("/api/v1/office/attachment-orders", json=order, headers=hdr(legal_officer, "fo.apfc"))
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["status"] == "REFUSED"
    assert "EPF Act s.10" in data["section"] or "Section 10" in data["refusal_reason"]
    assert data["payments_diverted"] is False
    assert data["target_uan"] == "100000000001"


def test_attachment_order_maintenance_refused_under_epf_act_s10(ctx):
    """A maintenance order is NOT exempt in the POC and must be refused citing s.10."""
    client, q, deliver = ctx
    legal_officer = SUBJECTS["ro-apfc"]

    order = {
        "order_number": "FAMILY-MAINT-2026-12",
        "court_name": "Family Court, Mumbai",
        "order_date": "2026-09-20",
        "order_type": "MAINTENANCE_ORDER",
        "amount_paise": 5000000,
        "target_uan": "100000000001",
        "debtor_name": "RAHUL SHARMA",
        "note": "Maintenance decree under personal law",
    }
    res = client.post("/api/v1/office/attachment-orders", json=order, headers=hdr(legal_officer, "fo.apfc"))
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["status"] == "REFUSED"
    assert "Section 10" in data["refusal_reason"] or "EPF Act s.10" in data["refusal_reason"]
    assert data["payments_diverted"] is False


def test_attachment_order_epf_act_recovery_accepted(ctx):
    """An order under the EPF Act itself (EPFO recovery) is the sole exception and accepted."""
    client, q, deliver = ctx
    legal_officer = SUBJECTS["ro-apfc"]

    order = {
        "order_number": "EPFO-RC-2026-44",
        "court_name": "Recovery Officer, Regional Office Delhi North",
        "order_date": "2026-10-01",
        "order_type": "EPF_ACT_RECOVERY",
        "amount_paise": 2000000,
        "target_uan": "100000000001",
        "debtor_name": "RAHUL SHARMA",
        "note": "Recovery of erroneous credit under EPF Act",
    }
    res = client.post("/api/v1/office/attachment-orders", json=order, headers=hdr(legal_officer, "fo.apfc"))
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["status"] == "ACCEPTED"
    assert data["refusal_reason"] is None


def test_attachment_order_refused_does_not_divert_claim_payment(ctx):
    """Even when an attachment order is received, the claim payment is not diverted."""
    client, q, deliver = ctx
    legal_officer = SUBJECTS["ro-apfc"]

    # Member files a claim
    res = client.post("/api/v1/members/me/claims", json={
        "account_link_id": "AL-0001",
        "claim_type": "ADVANCE_ILLNESS",
        "amount_paise": 5000000,
    }, headers=member(MEMBER_A))
    assert res.status_code == 201
    claim = res.json()["data"]
    claim_id = claim["claim_id"]

    # Confirm claim (auto settles within auto limit)
    conf = claim["confirmation"]
    step = {"action": conf["action"], "resource_id": conf["resource_id"],
            "resource_version": conf["resource_version"], "amount_paise": conf["amount_paise"]}
    confirmed = client.post(f"/api/v1/members/me/claims/{claim_id}/confirmations", headers=member(MEMBER_A, step))
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["state"] == "AUTO_APPROVED"

    # Attachment order received against this claim
    order = {
        "order_number": "EXEC-2026-77",
        "court_name": "Senior Civil Judge Court",
        "order_date": "2026-10-02",
        "order_type": "COURT_DECREE",
        "amount_paise": 5000000,
        "target_uan": "100000000001",
        "claim_id": claim_id,
        "debtor_name": "RAHUL SHARMA",
    }
    att_res = client.post("/api/v1/office/attachment-orders", json=order, headers=hdr(legal_officer, "fo.apfc"))
    assert att_res.status_code == 201
    assert att_res.json()["data"]["status"] == "REFUSED"
    assert att_res.json()["data"]["payments_diverted"] is False

    # Ledger debit posted
    deliver("ClaimDebitPosted.v1", {"journal_id": "J-ATT", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": 5000000}]}, "contribution-service")

    # Payment instructed: claim pays to the member's account as normal
    p_step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": 5000000}
    instructed = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={"demo_scenario": "SUCCESS"},
                             headers=hdr(CASHIER, "fo.cash", p_step, **{"Idempotency-Key": "att-pay-1"}))
    assert instructed.status_code == 200
    assert instructed.json()["data"]["net_paise"] == 5000000
    # Payment went to the member, not diverted
    assert instructed.json()["data"]["state"] == "PAYMENT_PENDING"
