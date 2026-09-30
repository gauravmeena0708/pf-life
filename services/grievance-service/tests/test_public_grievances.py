"""Public grievance privacy and complainant/officer follow-up workflows."""
import asyncio
import hashlib
import json
import re

import pytest
from sqlalchemy import text

from tests.test_grievance_api import (
    SEED, ctx, gid_of, hdr, member, register,
)

PRO = next(p["subject"] for p in SEED["office_staff"]
           if p["stakeholder"] == "fo.pro" and p["office_id"] == "RO-DEMO-01")
MOBILE = "9876543210"
DESCRIPTION = "My pension payment has not reached my registered bank account."


def q(sql):
    from app.infra.db import engine

    async def read():
        async with engine().connect() as connection:
            return (await connection.execute(text(sql))).mappings().all()
    return asyncio.run(read())


def intake(client, **changes):
    return client.post("/api/v1/public/grievances", headers=hdr("anonymous", "public"), json={
        "challenge_id": "demo-challenge", "answer": 7, "name": "Demo Pensioner",
        "mobile": MOBILE, "otp": "123456", "complainant_type": "PENSIONER",
        "category": "CLAIM_DELAY", "subject": "Pension payment delayed",
        "description": DESCRIPTION, **changes,
    })


def resolve(client, gid):
    response = client.post(f"/api/v1/grievances/{gid}/messages",
                           json={"body": "The office has checked the payment."}, headers=hdr(PRO, "fo.pro"))
    assert response.status_code == 201, response.text
    version = response.json()["data"]["version"]
    response = client.post(f"/api/v1/grievances/{gid}/resolution",
                           json={"resolution": "Payment reissued and credited to the bank."},
                           headers=hdr(PRO, "fo.pro", {"action": "resolve-grievance",
                                                      "resource_id": gid, "resource_version": version}))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "RESOLVED"


@pytest.mark.parametrize("changes", [
    {"otp": "000000"}, {"complainant_type": "UNKNOWN"}, {"category": "UNKNOWN"},
])
def test_public_intake_rejects_invalid_input_without_registering(ctx, changes):
    client, events = ctx
    response = intake(client, **changes)
    assert response.status_code == 422, response.text
    assert q("SELECT grievance_id FROM grievances") == []
    assert events("GrievanceRegistered.v1") == []


def test_public_intake_routes_and_stores_only_hashed_mobile(ctx):
    client, events = ctx
    response = intake(client)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    gid = data["registration_no"]
    assert re.fullmatch(r"GRV-[0-9A-F]{8}", gid)
    assert data["state"] == "ROUTED"
    [event] = events("GrievanceRegistered.v1")
    assert event["grievance_id"] == gid
    assert event["office_id"] == data["office_id"]
    [stored] = q("SELECT * FROM grievances")
    assert stored["mobile_last4"] == MOBILE[-4:]
    assert stored["mobile_hash"] == hashlib.sha256(f"epfo-demo-grievance|{MOBILE}".encode()).hexdigest()
    for table in ("grievances", "grievance_entries", "outbox", "audit_local"):
        assert MOBILE not in json.dumps([dict(row) for row in q(f"SELECT * FROM {table}")], default=str)


def test_public_lookup_checks_mobile_and_omits_description(ctx):
    client, _ = ctx
    registered = intake(client)
    assert registered.status_code == 201, registered.text
    body = {"challenge_id": "demo-challenge", "answer": 7, "otp": "123456",
            "registration_no": registered.json()["data"]["registration_no"], "mobile": MOBILE}
    response = client.post("/api/v1/public/grievances/status-lookups", json=body, headers=hdr("anonymous", "public"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "ROUTED"
    assert [step["state"] for step in data["steps"]] == ["REGISTERED", "ROUTED"]
    assert "description" not in response.text and DESCRIPTION not in response.text
    response = client.post("/api/v1/public/grievances/status-lookups", json={**body, "mobile": "9876543211"},
                           headers=hdr("anonymous", "public"))
    assert response.status_code == 404, response.text


def test_member_reminders_are_limited_to_one_per_day_and_open_grievances(ctx):
    client, _ = ctx
    registered = register(client)
    assert registered.status_code == 201, registered.text
    gid = gid_of(registered)
    url = f"/api/v1/grievances/{gid}/reminders"
    response = client.post(url, json={"note": "Please check the payment."}, headers=member())
    assert response.status_code == 201, response.text
    assert response.json()["data"]["reminders"] == 1
    assert client.post(url, json={}, headers=member()).status_code == 429
    assert q("SELECT reminders FROM grievances")[0]["reminders"] == 1
    resolve(client, gid)
    assert client.post(url, json={}, headers=member()).status_code == 409


@pytest.mark.parametrize("satisfied, state", [(True, "CLOSED"), (False, "RESOLVED")])
def test_feedback_requires_resolution_is_single_use_and_closes_if_satisfied(ctx, satisfied, state):
    client, events = ctx
    registered = register(client)
    assert registered.status_code == 201, registered.text
    gid = gid_of(registered)
    url = f"/api/v1/grievances/{gid}/feedback"
    body = {"rating": 4 if satisfied else 2, "satisfied": satisfied, "comment": "Payment checked."}
    assert client.post(url, json=body, headers=member()).status_code == 409
    assert events("GrievanceFeedbackGiven.v1") == []
    resolve(client, gid)
    response = client.post(url, json=body, headers=member())
    assert response.status_code == 201, response.text
    assert response.json()["data"]["state"] == state
    [event] = events("GrievanceFeedbackGiven.v1")
    assert event == {"grievance_id": gid, "office_id": "RO-DEMO-01",
                     "rating": body["rating"], "satisfied": satisfied}
    assert client.post(url, json=body, headers=member()).status_code == 409
    assert len(events("GrievanceFeedbackGiven.v1")) == 1


def test_office_transfer_moves_ownership_and_revokes_old_office_access(ctx):
    client, events = ctx
    registered = register(client)
    assert registered.status_code == 201, registered.text
    gid = gid_of(registered)
    headers = hdr(PRO, "fo.pro")
    url = f"/api/v1/grievances/{gid}/office-transfers"
    body = {"to_office_id": "RO-DEMO-01", "reason": "The member belongs to the other office."}
    assert client.post(url, json=body, headers=headers).status_code == 422
    assert events("GrievanceTransferred.v1") == []
    assert client.get(f"/api/v1/grievances/{gid}", headers=headers).status_code == 200
    response = client.post(url, json={**body, "to_office_id": "RO-DEMO-02"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["office_id"] == "RO-DEMO-02"
    assert q("SELECT office_id FROM grievances")[0]["office_id"] == "RO-DEMO-02"
    [event] = events("GrievanceTransferred.v1")
    assert event == {"grievance_id": gid, "from_office_id": "RO-DEMO-01",
                     "to_office_id": "RO-DEMO-02", "reason": body["reason"]}
    assert client.get(f"/api/v1/grievances/{gid}", headers=hdr(PRO, "fo.pro")).status_code == 404
