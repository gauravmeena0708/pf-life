"""member-service Journey D: contact change with step-up, security reports, reviewed account recovery."""
import time
import uuid

import jwt

from tests.conftest import KEY, KID
from tests.test_member_api import MEMBER_A, MEMBER_B, SEED, api  # noqa: F401  (fixture)

ANALYST = SEED["keycloak_subjects"]["security-analyst"]
MEMBER_ID = SEED["members"][0]["member_id"]


def hdr(subject, stakeholder="member", step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "member-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


NEW = {"mobile": "9876500000", "email": "someone@example.org"}


def change(api, subject=MEMBER_A, member_id=MEMBER_ID):
    return api.patch("/api/v1/members/me/contact-details", json=NEW,
                     headers=hdr(subject, step_up={"action": "change-contact", "resource_id": member_id}))


def test_contact_change_needs_step_up_and_stores_only_masked_values(api):
    assert api.patch("/api/v1/members/me/contact-details", json=NEW, headers=hdr(MEMBER_A)).status_code == 428
    r = change(api)
    assert r.status_code == 200 and r.json()["data"]["mobile_masked"] == "******0000"
    me = api.get("/api/v1/members/me", headers=hdr(MEMBER_A)).json()["data"]
    assert me["mobile_masked"] == "******0000" and "9876500000" not in str(me) and me["email_masked"] == "s***@example.org"
    bad = api.patch("/api/v1/members/me/contact-details", json={**NEW, "mobile": "12345"},
                    headers=hdr(MEMBER_A, step_up={"action": "change-contact", "resource_id": MEMBER_ID}))
    assert bad.status_code == 400


def test_security_report(api):
    r = api.post("/api/v1/members/me/security-reports", json={"kind": "NOT_ME", "description": "I did not change my mobile"},
                 headers=hdr(MEMBER_A))
    assert r.status_code == 201 and r.json()["data"]["report_id"].startswith("SEC-")


def test_recovery_is_reviewed_and_restores_verified_contact(api):
    original = api.get("/api/v1/members/me", headers=hdr(MEMBER_A)).json()["data"]["mobile_masked"]
    change(api)                                                      # someone changed the contact details
    url = "/api/v1/members/me/account-recovery-requests"
    body = {"reason": "My mobile number was changed by someone else"}
    assert api.post(url, json=body, headers=hdr(MEMBER_A)).status_code == 428
    r = api.post(url, json=body, headers=hdr(MEMBER_A, step_up={"action": "request-recovery", "resource_id": MEMBER_ID}))
    assert r.status_code == 201 and r.json()["data"]["state"] == "PENDING_REVIEW"
    request_id = r.json()["data"]["request_id"]
    assert api.get("/api/v1/members/me", headers=hdr(MEMBER_A)).json()["data"]["mobile_masked"] == "******0000"  # nothing yet
    queue = api.get("/api/v1/security/account-recovery-requests", headers=hdr(ANALYST, "ho.security")).json()["data"]
    assert queue[0]["restore_to"]["mobile_masked"] == original and queue[0]["current"]["mobile_masked"] == "******0000"
    assert api.get("/api/v1/security/account-recovery-requests", headers=hdr(MEMBER_A)).status_code == 403
    decide = f"/api/v1/security/account-recovery-requests/{request_id}/decisions"
    decision = {"decision": "APPROVE", "note": "Member verified on a call to the old number"}
    assert api.post(decide, json=decision, headers=hdr(ANALYST, "ho.security")).status_code == 428
    r = api.post(decide, json=decision, headers=hdr(ANALYST, "ho.security", {"action": "decide-recovery", "resource_id": request_id}))
    assert r.status_code == 200 and r.json()["data"]["state"] == "APPROVED"
    assert api.get("/api/v1/members/me", headers=hdr(MEMBER_A)).json()["data"]["mobile_masked"] == original
    again = api.post(decide, json=decision, headers=hdr(ANALYST, "ho.security", {"action": "decide-recovery", "resource_id": request_id}))
    assert again.status_code == 409


def test_only_one_pending_recovery(api):
    url = "/api/v1/members/me/account-recovery-requests"
    step = {"action": "request-recovery", "resource_id": SEED["members"][1]["member_id"]}
    assert api.post(url, json={"reason": "Lost my phone last week"}, headers=hdr(MEMBER_B, step_up=step)).status_code == 201
    assert api.post(url, json={"reason": "Lost my phone last week"}, headers=hdr(MEMBER_B, step_up=step)).status_code == 409
