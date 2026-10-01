"""Change request decisions, signed registration feeds, and optional seed links."""
import asyncio
import hashlib
import hmac

import pytest
from sqlalchemy import select

from app.infra.tables import contractors, establishments, grants
from tests.test_employer_api import EST, SEED, SUBJECTS, api as base_api, owner, token

SIGNATORY = SUBJECTS["emp-signatory"]
APFC = SUBJECTS["ro-apfc"]


@pytest.fixture
def api(base_api):
    response = base_api.post("/api/v1/employers/me/signatories/authorisations",
                             json={"username": "emp-signatory", "grants": ["ecr.approve", "ecr.submit"]},
                             headers=owner({"action": "authorise-signatory", "resource_id": EST}))
    assert response.status_code == 201
    return base_api


def signer(action="request-establishment-change"):
    return token(SIGNATORY, "employer.signatory", step_up={"action": action, "resource_id": EST} if action else None)


def officer(req_id):
    return token(APFC, "fo.apfc", establishment=None,
                 step_up={"action": "decide-establishment-change", "resource_id": req_id})


def decide(api, request, decision="APPROVE"):
    req = request if isinstance(request, dict) else request.json()["data"]
    return api.post(f"/api/v1/office/establishments/{EST}/change-requests/{req['request_id']}/decisions",
                    json={"decision": decision, "note": "Evidence checked by officer"}, headers=officer(req["request_id"]))


def test_voluntary_coverage_rules_and_decision(api):
    url = "/api/v1/employers/voluntary-coverage-requests"
    body = {"employees": 10, "employees_consenting": 6, "effective_from": "2026-09-01", "reason": "Workers voted for voluntary coverage"}
    first = api.post(url, json=body, headers=signer())
    assert first.status_code == 201
    assert api.post(url, json=body, headers=signer()).status_code == 409
    pending = api.get("/api/v1/employers/me/change-requests", headers=signer()).json()["data"][0]
    assert pending["kind"] == "VOLUNTARY_COVERAGE"
    assert decide(api, pending).status_code == 200
    assert api.post(url, json=body, headers=signer()).status_code == 409
    assert "VOLUNTARY" in str(api.get("/api/v1/employers/me/configuration", headers=signer()).json())


def test_voluntary_coverage_validation(api):
    url = "/api/v1/employers/voluntary-coverage-requests"
    body = {"employees": 20, "employees_consenting": 20, "effective_from": "2026-09-01", "reason": "Workers voted for voluntary coverage"}
    response = api.post(url, json=body, headers=signer())
    assert response.status_code == 409 and response.json()["type"] == "/problems/covered-compulsorily"
    body.update(employees=10, employees_consenting=5)
    assert api.post(url, json=body, headers=signer()).status_code == 422
    body["employees_consenting"] = 11
    assert api.post(url, json=body, headers=signer()).status_code == 422


def test_closure_approval_event_and_rejection_no_op(api):
    url = "/api/v1/employers/me/closure-requests"
    body = {"closed_on": "2026-09-30", "reason": "BUSINESS_DISCONTINUED", "last_wage_month": "2026-09",
            "note": "Operations ended after the last wage period"}
    assert api.post(url, json=body, headers=signer(None)).status_code == 428                  # no step-up
    assert api.post(url, json=body, headers=signer()).status_code == 403                      # a step-up for another action
    assert api.post(url, json={**body, "last_wage_month": "2026-10"}, headers=signer("request-closure")).status_code == 422
    first = api.post(url, json=body, headers=signer("request-closure"))
    assert first.status_code == 201
    assert api.post(url, json=body, headers=signer("request-closure")).status_code == 409
    assert decide(api, first, "REJECT").json()["data"]["state"] == "REJECTED"
    assert "EstablishmentClosed.v1" not in api.outbox_events()
    second = api.post(url, json=body, headers=signer("request-closure"))
    assert decide(api, second).json()["data"]["state"] == "APPROVED"
    assert "EstablishmentClosed.v1" in api.outbox_events()
    assert api.post(url, json=body, headers=signer("request-closure")).status_code == 409


def test_transfer_validation_rejection_and_approval(api):
    url = "/api/v1/employers/me/office-transfer-requests"
    body = {"to_office_id": "RO-DEMO-02", "reason": "Administrative jurisdiction changed", "effective_from": "2026-09-01"}
    assert api.post(url, json={**body, "to_office_id": "RO-DEMO-01"}, headers=signer("request-office-transfer")).status_code == 409
    assert api.post(url, json={**body, "to_office_id": "RO-UNKNOWN"}, headers=signer("request-office-transfer")).status_code == 422
    first = api.post(url, json=body, headers=signer("request-office-transfer"))
    assert first.status_code == 201
    assert decide(api, first, "REJECT").json()["data"]["state"] == "REJECTED"
    assert "EstablishmentOfficeTransferred.v1" not in api.outbox_events()
    second = api.post(url, json=body, headers=signer("request-office-transfer"))
    assert decide(api, second).json()["data"]["state"] == "APPROVED"
    assert "EstablishmentOfficeTransferred.v1" in api.outbox_events()


def test_signed_feeds_are_idempotent_and_reject_duplicate_pan(api):
    address = {"line1": "12 Industrial Estate", "city": "Delhi", "district": "Delhi", "pincode": "110001"}
    feeds = [
        ("mca", "ext.mca", "cin", "U12345DL2026PLC123456", "company_name", "Demo MCA Industries", "incorporated_on", "MCA_SPICE", "dev-mca-spice", "AAACD1234K"),
        ("shram-suvidha", "ext.shram_suvidha", "lin", "1234567890", "establishment_name", "Demo Shram Industries", "registered_on", "SHRAM_SUVIDHA", "dev-shram-suvidha", "AAASD1234K"),
    ]
    for path, role, key, ref, name_key, name, date_key, source, secret, pan in feeds:
        body = {key: ref, name_key: name, date_key: "2026-09-01", "pan": pan, "address": address}
        message = f"{ref}|{name}|{pan}|2026-09-01"
        body["signature"] = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        url = f"/api/v1/integrations/{path}/registrations"
        auth = token(f"feed-{path}", role, establishment=None)
        assert api.post(url, json={**body, "signature": "0" * 64}, headers=auth).status_code == 401
        first = api.post(url, json=body, headers=auth)
        assert first.status_code == 201 and first.json()["data"]["source"] == source
        repeat = api.post(url, json=body, headers=auth)
        assert repeat.status_code == 200 and repeat.json()["data"]["request_id"] == first.json()["data"]["request_id"]
        duplicate = {**body, key: ref + "X"}
        duplicate["signature"] = hmac.new(secret.encode(), f"{ref}X|{name}|{pan}|2026-09-01".encode(), hashlib.sha256).hexdigest()
        assert api.post(url, json=duplicate, headers=auth).status_code == 409
        listed = api.get("/api/v1/office/establishment-registrations",
                         headers=token(APFC, "fo.apfc", establishment=None)).json()["data"]
        assert any(r["request_id"] == first.json()["data"]["request_id"] for r in listed)


def test_seed_principal_grant_and_contractor_link(api):
    from app import seed
    from app.infra.db import sessions

    async def check():
        await seed.main()  # idempotent
        async with sessions()() as session:
            principal = SEED["principal_employer"]
            grant = (await session.execute(select(grants).where(grants.c.subject == principal["subject"]))).mappings().one()
            link = (await session.execute(select(contractors).where(
                contractors.c.principal_establishment_id == principal["establishment_id"]))).mappings().one()
            contractor = (await session.execute(select(establishments).where(
                establishments.c.establishment_id == link["contractor_establishment_id"]))).mappings().one()
            return grant, link, contractor

    grant, link, contractor = asyncio.run(check())
    assert grant["kind"] == "OWNER" and grant["status"] == "ACTIVE"
    assert link["contractor_registration_number"] == contractor["registration_number"]
    assert link["contractor_name"] == contractor["legal_name"]
    result = api.get(f"/internal/actors/{grant['subject']}/grants",
                     headers=token("gateway", "system.gateway", establishment=None))
    assert any(e["establishment_id"] == grant["establishment_id"] for e in result.json()["data"]["establishments"])
