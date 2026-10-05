"""P2.19: Aadhaar-less international worker KYC uses a current passport."""
from datetime import date, timedelta

from tests.test_member_api import SEED, api, token  # noqa: F401
from tests.test_onboarding import hdr, signatory

ELENA = SEED["keycloak_subjects"]["worker-expat"]


def test_international_member_can_submit_passport_and_expiry_controls_readiness(api):
    path = "/api/v1/members/me/kyc/passport"
    body = {"number": "X1234567", "country": "United States", "expiry": (date.today() + timedelta(days=365)).isoformat()}
    member_id = next(m["member_id"] for m in SEED["members"] if m["uan"] == "100000000907")
    r = api.post(path, headers=hdr(ELENA, "member", step_up={"action": "seed-kyc", "resource_id": member_id}, establishment=None), json=body)
    assert r.status_code == 201, r.json()
    assert "X1234567" not in str(r.json())
    request_id = r.json()["data"]["request_id"]
    approved = api.post(f"/api/v1/employers/me/kyc-approvals/{request_id}/decisions",
                        headers=signatory({"action": "approve-kyc", "resource_id": request_id}),
                        json={"decision": "APPROVE", "note": "Passport document inspected"})
    assert approved.status_code == 200, approved.json()
    status = api.get("/api/v1/members/me/account-status", headers=token(ELENA)).json()["data"]
    assert "KYC_AADHAAR_MISSING" not in {b["code"] for b in status["accounts"][0]["blockers"]}


def test_expired_passport_is_refused(api):
    member_id = next(m["member_id"] for m in SEED["members"] if m["uan"] == "100000000907")
    r = api.post("/api/v1/members/me/kyc/passport", headers=hdr(ELENA, "member", step_up={"action": "seed-kyc", "resource_id": member_id}, establishment=None), json={
        "number": "X1234567", "country": "United States", "expiry": (date.today() - timedelta(days=1)).isoformat()})
    assert r.status_code == 422


def test_domestic_member_cannot_replace_aadhaar_with_passport(api):
    r = api.post("/api/v1/members/me/kyc/passport", headers=token(SEED["keycloak_subjects"]["member-b"]), json={
        "number": "X1234567", "country": "United States", "expiry": (date.today() + timedelta(days=365)).isoformat()})
    assert r.status_code == 403
