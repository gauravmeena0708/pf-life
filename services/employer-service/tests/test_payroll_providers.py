"""Payroll provider authorisation tests (P2.22)."""
import os
import pytest
from epfo_persistence.contracts import _folder

os.environ["EPFO_EVENT_CONTRACTS"] = "off"
_folder.cache_clear()

from tests.test_employer_api import EST, PREPARER, SIGNATORY, api, owner, token  # noqa: F401 (api fixture)

PROVIDER_ID = "PP-DEMO-1"
PROVIDER_NAME = "Demo Payroll Services"
PROVIDER_SUBJECT = "00000000-0000-4000-8000-000000000082"


def test_payroll_providers_lifecycle(api):
    # 1. list shows the directory
    initial = api.get("/api/v1/employers/me/payroll-providers", headers=owner())
    assert initial.status_code == 200
    data = initial.json()["data"]
    assert any(p["provider_id"] == PROVIDER_ID and p["name"] == PROVIDER_NAME for p in data["available"])
    assert data["authorised"] == []

    # 2. authorise requires step-up (428 without it, 403 with wrong resource)
    body = {"provider_id": PROVIDER_ID}
    no_step = api.post("/api/v1/employers/me/payroll-providers/authorisations", json=body, headers=owner())
    assert no_step.status_code == 428
    assert no_step.json()["type"] == "/problems/step-up-required"

    wrong_step = api.post(
        "/api/v1/employers/me/payroll-providers/authorisations",
        json=body,
        headers=owner({"action": "authorise-payroll-provider", "resource_id": "PP-OTHER"}),
    )
    assert wrong_step.status_code == 403
    assert wrong_step.json()["type"] == "/problems/step-up-mismatch"

    # Authorise with correct step-up
    step_up = {"action": "authorise-payroll-provider", "resource_id": PROVIDER_ID}
    auth_res = api.post("/api/v1/employers/me/payroll-providers/authorisations", json=body, headers=owner(step_up))
    assert auth_res.status_code == 201
    auth_data = auth_res.json()["data"]
    grant_id = auth_data["grant_id"]
    assert auth_data["provider_id"] == PROVIDER_ID
    assert auth_data["name"] == PROVIDER_NAME
    assert auth_data["scopes"] == ["payroll.submit"]
    assert auth_data["status"] == "ACTIVE"
    assert auth_data["granted_at"] is not None
    assert "PayrollProviderAuthorised.v1" in api.outbox_events()

    # List now shows the authorised provider
    listed = api.get("/api/v1/employers/me/payroll-providers", headers=owner()).json()["data"]
    assert len(listed["authorised"]) == 1
    assert listed["authorised"][0]["grant_id"] == grant_id
    assert listed["authorised"][0]["provider_id"] == PROVIDER_ID
    assert listed["authorised"][0]["name"] == PROVIDER_NAME
    assert listed["authorised"][0]["scopes"] == ["payroll.submit"]
    assert listed["authorised"][0]["status"] == "ACTIVE"

    # 3. a second authorisation 409
    dup = api.post("/api/v1/employers/me/payroll-providers/authorisations", json=body, headers=owner(step_up))
    assert dup.status_code == 409
    assert dup.json()["type"] == "/problems/already-authorised"

    # 4. internal grants endpoint returns establishment with ["payroll.submit"] for provider's subject
    gw = token("gateway", "system.gateway", establishment=None)
    grants_res = api.get(f"/internal/actors/{PROVIDER_SUBJECT}/grants", headers=gw)
    assert grants_res.status_code == 200
    establishments = grants_res.json()["data"]["establishments"]
    assert establishments == [{"establishment_id": EST, "grants": ["payroll.submit"]}]

    # 5. revoke (step-up required: 428 without it)
    revoke_body = {"reason": "Changing payroll software vendor"}
    no_revoke_step = api.post(
        f"/api/v1/employers/me/payroll-providers/authorisations/{grant_id}/revocations",
        json=revoke_body,
        headers=owner(),
    )
    assert no_revoke_step.status_code == 428

    revoke_step = {"action": "revoke-payroll-provider", "resource_id": grant_id}
    rev_res = api.post(
        f"/api/v1/employers/me/payroll-providers/authorisations/{grant_id}/revocations",
        json=revoke_body,
        headers=owner(revoke_step),
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.json()["data"]
    assert rev_data["status"] == "REVOKED"
    assert rev_data["revocation"] == {
        "subject": PROVIDER_SUBJECT,
        "establishment_id": EST,
        "grant_id": grant_id,
        "scope": "grant",
    }
    assert "PayrollProviderRevoked.v1" in api.outbox_events()

    # Grants endpoint now returns empty list for this provider
    grants_after = api.get(f"/internal/actors/{PROVIDER_SUBJECT}/grants", headers=gw).json()["data"]["establishments"]
    assert grants_after == []

    # Second revocation is 409
    dup_rev = api.post(
        f"/api/v1/employers/me/payroll-providers/authorisations/{grant_id}/revocations",
        json=revoke_body,
        headers=owner(revoke_step),
    )
    assert dup_rev.status_code == 409

    # List shows status REVOKED
    after_list = api.get("/api/v1/employers/me/payroll-providers", headers=owner()).json()["data"]
    assert len(after_list["authorised"]) == 1
    assert after_list["authorised"][0]["status"] == "REVOKED"


def test_non_owner_refused(api):
    # Operator
    operator_token = token(PREPARER, "employer.operator", ["ecr.prepare"], establishment=EST)
    assert api.get("/api/v1/employers/me/payroll-providers", headers=operator_token).status_code == 403
    assert (
        api.post(
            "/api/v1/employers/me/payroll-providers/authorisations",
            json={"provider_id": PROVIDER_ID},
            headers=operator_token,
        ).status_code
        == 403
    )
    assert (
        api.post(
            f"/api/v1/employers/me/payroll-providers/authorisations/GR-FAKE/revocations",
            json={"reason": "test reason here"},
            headers=operator_token,
        ).status_code
        == 403
    )

    # Signatory
    signatory_token = token(SIGNATORY, "employer.signatory", ["ecr.approve"], establishment=EST)
    assert api.get("/api/v1/employers/me/payroll-providers", headers=signatory_token).status_code == 403
    assert (
        api.post(
            "/api/v1/employers/me/payroll-providers/authorisations",
            json={"provider_id": PROVIDER_ID},
            headers=signatory_token,
        ).status_code
        == 403
    )
    assert (
        api.post(
            f"/api/v1/employers/me/payroll-providers/authorisations/GR-FAKE/revocations",
            json={"reason": "test reason here"},
            headers=signatory_token,
        ).status_code
        == 403
    )
