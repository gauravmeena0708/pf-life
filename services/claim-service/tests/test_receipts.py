"""Claim receipt and public verification tests."""
import re

from app.api.receipt_routes import receipt_code
from tests.test_claims_api import MEMBER_A, MEMBER_B, confirm, create, ctx, hdr, member

VERIFY_URL = "/api/v1/public/receipts/verifications"


def verify(client, claim_id: str, code: str, **changes):
    return client.post(VERIFY_URL, headers=hdr("anonymous", "public"), json={
        "challenge_id": "demo-challenge",
        "answer": 7,
        "claim_id": claim_id,
        "code": code,
        **changes,
    })


def test_member_gets_receipt_with_code_and_other_member_gets_404(ctx):
    client, *_ = ctx
    response = create(client, subject=MEMBER_A)
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    claim_id = created["claim_id"]

    # Unconfirmed claim: receipt is 404
    receipt_resp = client.get(f"/api/v1/members/me/claims/{claim_id}/receipt", headers=member(MEMBER_A))
    assert receipt_resp.status_code == 404

    # Confirm the claim
    assert confirm(client, created, subject=MEMBER_A).status_code == 200

    # Member A gets the receipt
    receipt_resp = client.get(f"/api/v1/members/me/claims/{claim_id}/receipt", headers=member(MEMBER_A))
    assert receipt_resp.status_code == 200, receipt_resp.text
    receipt = receipt_resp.json()["data"]

    assert receipt["claim_id"] == claim_id
    assert receipt["form_type"] == created["form_type"]
    assert receipt["amount_paise"] == created["amount_paise"]
    assert receipt["claim_label"]
    assert receipt["filed_on"]
    assert receipt["state"]
    assert receipt["member_name"]
    assert receipt["uan_masked"] and receipt["uan_masked"].startswith("********")
    code = receipt["code"]
    assert re.match(r"^[A-Z2-7]{10}$", code)
    assert receipt["verify_path"] == f"/public/receipts/verify?claim={claim_id}&code={code}"

    # Another member gets 404
    other_resp = client.get(f"/api/v1/members/me/claims/{claim_id}/receipt", headers=member(MEMBER_B))
    assert other_resp.status_code == 404


def test_verification_genuine_and_not_genuine(ctx):
    client, *_ = ctx
    response = create(client, subject=MEMBER_A)
    created = response.json()["data"]
    claim_id = created["claim_id"]

    # Before confirmation, public verification returns genuine: false
    code_placeholder = receipt_code(claim_id, created["amount_paise"], "2026-10-04")
    unconfirmed_verify = verify(client, claim_id, code_placeholder)
    assert unconfirmed_verify.status_code == 200
    assert unconfirmed_verify.json()["data"] == {"genuine": False}

    # Confirm the claim
    assert confirm(client, created, subject=MEMBER_A).status_code == 200
    receipt = client.get(f"/api/v1/members/me/claims/{claim_id}/receipt", headers=member(MEMBER_A)).json()["data"]
    code = receipt["code"]

    # Verification with correct code -> genuine: true
    ok_resp = verify(client, claim_id, code)
    assert ok_resp.status_code == 200, ok_resp.text
    data = ok_resp.json()["data"]
    assert data["genuine"] is True
    assert data["claim_id"] == claim_id
    assert data["form_type"] == receipt["form_type"]
    assert data["amount_paise"] == receipt["amount_paise"]
    assert data["filed_on"] == receipt["filed_on"]
    assert data["state"] == receipt["state"]

    # Verification with wrong code -> genuine: false
    wrong_code = ("A" if code[0] != "A" else "B") + code[1:]
    wrong_resp = verify(client, claim_id, wrong_code)
    assert wrong_resp.status_code == 200
    assert wrong_resp.json()["data"] == {"genuine": False}

    # Verification with unknown claim -> genuine: false
    unknown_resp = verify(client, "CLM-FFFFFFFF", code)
    assert unknown_resp.status_code == 200
    assert unknown_resp.json()["data"] == {"genuine": False}


def test_code_changes_if_amount_differs():
    claim_id = "CLM-ABCD1234"
    filed_on = "2026-10-04"
    code1 = receipt_code(claim_id, 10000000, filed_on)
    code2 = receipt_code(claim_id, 20000000, filed_on)
    assert re.match(r"^[A-Z2-7]{10}$", code1)
    assert re.match(r"^[A-Z2-7]{10}$", code2)
    assert code1 != code2
