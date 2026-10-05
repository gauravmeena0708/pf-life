"""P2.19c: Returned payments after a bank merger.

When a payment is returned with a reason meaning the IFSC no longer exists (merged bank),
look the old IFSC up in a small seeded table of merged-bank IFSC successors (e.g. the 2019-2020
public-sector bank amalgamations — use clearly synthetic codes), re-route the payment to the
successor IFSC once, record the remapping, and notify the member; if no successor is known,
fall back to the existing return handling. Tests.
"""
from tests.test_claims_api import CASHIER, MEMBER_A, S_APFC, SUBJECTS, ctx, events, hdr, member


def _setup_instructed_claim(client, deliver, ifsc="SYNB0001234", last4="1234"):
    # Create and confirm a claim
    res = client.post("/api/v1/members/me/claims", json={
        "account_link_id": "AL-0001",
        "claim_type": "ADVANCE_ILLNESS",
        "amount_paise": 5000000,
    }, headers=member(MEMBER_A))
    claim_id = res.json()["data"]["claim_id"]
    conf = res.json()["data"]["confirmation"]
    client.post(f"/api/v1/members/me/claims/{claim_id}/confirmations", headers=member(
        MEMBER_A, {"action": conf["action"], "resource_id": conf["resource_id"],
                   "resource_version": conf["resource_version"], "amount_paise": conf["amount_paise"]}))

    # Set payee_ifsc on claim
    from app.infra.db import engine
    from sqlalchemy import text
    import asyncio
    async def set_ifsc():
        async with engine().begin() as conn:
            await conn.execute(text("UPDATE claims SET payee_ifsc = :ifsc, payee_account_last4 = :last4 WHERE claim_id = :id"),
                               {"ifsc": ifsc, "last4": last4, "id": claim_id})
    asyncio.run(set_ifsc())

    # Ledger debit posted
    deliver("ClaimDebitPosted.v1", {"journal_id": f"J-{claim_id}", "claim_id": claim_id, "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": 5000000}]}, "contribution-service")

    # Payment instruction
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": 5000000}
    instructed = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={"demo_scenario": "RETURN"},
                             headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": f"pay-{claim_id}-1"}))
    pid = instructed.json()["data"]["payment_id"]
    return claim_id, pid


def test_payment_returned_merged_bank_ifsc_rerouted_to_successor(ctx):
    """Returned payment with discontinued IFSC from merged bank is re-routed once to successor IFSC."""
    client, q, deliver = ctx

    claim_id, pid = _setup_instructed_claim(client, deliver, ifsc="SYNB0001234", last4="1234")

    # Bank returns payment due to discontinued/merged IFSC
    deliver("PaymentReturned.v1", {
        "payment_id": pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference": claim_id, "return_reason": "IFSC_NOT_FOUND_MERGED_BANK", "mock": True
    }, "payment-simulator")

    claim_row = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member(MEMBER_A)).json()["data"]

    # Must be re-routed once: payment state is PAYMENT_PENDING (new payment attempt issued)
    assert claim_row["state"] == "PAYMENT_PENDING"
    # New PaymentInstructed.v1 event was published
    instructed_events = events(q, "PaymentInstructed.v1")
    assert len(instructed_events) >= 2
    new_pid = instructed_events[-1]["payment_id"]
    assert new_pid != pid
    assert instructed_events[-1]["attempt"] == 2

    # Notification sent to member about re-routing
    notifications = events(q, "NotificationRequested.v1")
    assert any(n.get("template") == "PAYMENT_REROUTED_BANK_MERGER" for n in notifications)

    # Remapping recorded in timeline / table
    timeline = claim_row["timeline"]
    notes = " ".join(t["note"] for t in timeline)
    assert "CNRB0001234" in notes or "successor" in notes.lower() or "re-routed" in notes.lower()

    # If the re-routed payment also returns, it must NOT re-route again: falls back to PAYMENT_RETURNED
    deliver("PaymentReturned.v1", {
        "payment_id": new_pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference": claim_id, "return_reason": "IFSC_NOT_FOUND_MERGED_BANK", "mock": True
    }, "payment-simulator")

    final_claim = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member(MEMBER_A)).json()["data"]
    assert final_claim["state"] == "PAYMENT_RETURNED"


def test_payment_returned_unknown_ifsc_falls_back_to_existing_return_handling(ctx):
    """When no successor IFSC is known, falls back to existing PAYMENT_RETURNED handling."""
    client, q, deliver = ctx

    claim_id, pid = _setup_instructed_claim(client, deliver, ifsc="UNKN0009999", last4="1234")

    deliver("PaymentReturned.v1", {
        "payment_id": pid, "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
        "reference": claim_id, "return_reason": "IFSC_NOT_FOUND", "mock": True
    }, "payment-simulator")

    claim_row = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member(MEMBER_A)).json()["data"]
    assert claim_row["state"] == "PAYMENT_RETURNED"
    notifications = events(q, "NotificationRequested.v1")
    assert any(n.get("template") == "CLAIM_PAYMENT_RETURNED" for n in notifications)
