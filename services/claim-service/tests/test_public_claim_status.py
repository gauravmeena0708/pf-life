"""Public claim progress requires matching UAN and a confirmed claim."""
import pytest

from tests.test_claims_api import MEMBER_A, SEED, confirm, create, ctx, hdr

UAN = next(m["uan"] for m in SEED["members"] if m.get("subject") == MEMBER_A)
URL = "/api/v1/public/claims/status-lookups"


def lookup(client, claim_id, **changes):
    return client.post(URL, headers=hdr("anonymous", "public"), json={
        "challenge_id": "demo-challenge", "answer": 7, "claim_id": claim_id,
        "uan": UAN, "otp": "123456", **changes,
    })


def test_confirmed_claim_public_progress_contains_no_amount(ctx):
    client, *_ = ctx
    response = create(client)
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    response = confirm(client, created)
    assert response.status_code == 200, response.text
    state = response.json()["data"]["state"]
    response = lookup(client, created["claim_id"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["claim_id"] == created["claim_id"] and data["state"] == state == "UNDER_REVIEW"
    assert data["steps"] and data["steps"][-1]["state"] == state
    assert all(set(step) == {"at", "state"} for step in data["steps"])
    assert "amount_paise" not in response.text


@pytest.mark.parametrize("changes, status", [({"uan": "999999999999"}, 404), ({"otp": "000000"}, 422)])
def test_public_lookup_rejects_wrong_uan_and_invalid_otp(ctx, changes, status):
    client, *_ = ctx
    response = create(client)
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    assert confirm(client, created).status_code == 200
    response = lookup(client, created["claim_id"], **changes)
    assert response.status_code == status, response.text


def test_unconfirmed_claim_is_not_publicly_visible(ctx):
    client, *_ = ctx
    response = create(client)
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    assert created["state"] == "AWAITING_CONFIRMATION"
    assert lookup(client, created["claim_id"]).status_code == 404
