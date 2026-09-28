"""TDS on withdrawals under the policy in force on the payment date: the rate with a verified PAN, a changed
rate applied to the next payment, a Form 15G waiver, and no TDS on advances. Member C (synthetic) left
employment on 2026-06-30 after about 3½ years, so a final settlement of ₹60,000 is taxable."""
from datetime import UTC, datetime

from tests.test_claims_api import CASHIER, SUBJECTS, _publish, confirm, create, ctx, events, hdr, member  # noqa: F401

MEMBER_C = SUBJECTS["member-c"]
AMOUNT = 6000000                                   # ₹60,000: above the ₹50,000 threshold, settled automatically


def pay(client, deliver, claim_id, key):
    deliver("ClaimDebitPosted.v1", {"journal_id": f"J-{claim_id}", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": AMOUNT}]}, "contribution-service")
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": AMOUNT}
    r = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={"demo_scenario": "SUCCESS"},
                    headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": key}))
    assert r.status_code == 200, r.json()
    deliver("PaymentConfirmed.v1", {"payment_id": r.json()["data"]["payment_id"], "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                    "reference_id": claim_id, "amount_paise": r.json()["data"]["net_paise"], "mock": True}, "payment-simulator")
    return r.json()["data"]


def final_settlement(client):
    created = create(client, amount=AMOUNT, account="AL-0006", subject=MEMBER_C, claim_type="FINAL_SETTLEMENT")
    assert created.status_code == 201, created.json()
    assert "Income tax may be deducted at source (TDS)" in created.json()["data"]["summary"]
    confirmed = confirm(client, created.json()["data"], subject=MEMBER_C).json()["data"]
    assert confirmed["state"] == "AUTO_APPROVED"
    return confirmed["claim_id"]


def test_tds_follows_the_policy_in_force_on_the_payment_date(ctx):
    client, q, deliver = ctx
    first = final_settlement(client)
    paid = pay(client, deliver, first, "k1")
    assert (paid["tds_paise"], paid["net_paise"]) == (600000, 5400000)          # 10% with a verified PAN
    assert events(q, "PaymentInstructed.v1")[-1]["amount_paise"] == 5400000       # the bank pays the net amount
    deducted = events(q, "TaxDeducted.v1")
    assert len(deducted) == 1 and deducted[0]["rate_bp"] == 1000 and deducted[0]["rule_version"] == "demo-rules-2026.1"
    view = client.get(f"/api/v1/members/me/claims/{first}", headers=member(MEMBER_C)).json()["data"]
    assert view["state"] == "SETTLED" and view["tax"]["basis"] == "10% with a verified PAN."
    assert "Income tax of ₹6,000 withheld" in view["timeline"][-2]["note"]
    settled = [n for n in events(q, "NotificationRequested.v1") if n["template"] == "CLAIM_SETTLED"]
    assert settled[-1]["params"]["amount_paise"] == 5400000

    # The TDS rate with a PAN is cut to 5% from today: the next payment uses it; the first one keeps its tax.
    def cut(d):
        d["tds"]["rate_with_pan_bp"] = 500
    _publish(deliver, cut, effective=datetime.now(UTC).date().isoformat())
    second = final_settlement(client)
    paid = pay(client, deliver, second, "k2")
    assert (paid["tds_paise"], paid["net_paise"]) == (300000, 5700000)
    assert events(q, "TaxDeducted.v1")[-1]["rule_version"] == "demo-rules-2026.9"
    assert client.get(f"/api/v1/members/me/claims/{first}", headers=member(MEMBER_C)).json()["data"]["tax"]["tds_paise"] == 600000

    # Form 15G for this financial year waives TDS; a second declaration is refused.
    url = "/api/v1/members/me/tax/form-15g-15h"
    assert client.post(url, json={"form": "15G", "declaration": True}, headers=member(MEMBER_C)).status_code == 201
    assert client.post(url, json={"form": "15H", "declaration": True}, headers=member(MEMBER_C)).status_code == 409
    third = final_settlement(client)
    paid = pay(client, deliver, third, "k3")
    assert (paid["tds_paise"], paid["net_paise"]) == (0, AMOUNT)
    assert len(events(q, "TaxDeducted.v1")) == 2


def test_advances_are_not_taxed_at_source(ctx):
    client, q, deliver = ctx
    claim_id = confirm(client, create(client, amount=AMOUNT).json()["data"]).json()["data"]["claim_id"]
    assert pay(client, deliver, claim_id, "k1")["tds_paise"] == 0
    assert events(q, "TaxDeducted.v1") == []
