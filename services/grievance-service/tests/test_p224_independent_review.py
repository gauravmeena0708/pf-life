"""P2.24 illustrative review of a closed grievance."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_grievance_api import PRO, SEED, ZO, ctx, gid_of, hdr, member, register

REVIEWER = next(s["subject"] for s in SEED["office_staff"] if s["stakeholder"] == "zo.rpfc1")


def closed(client):
    gid = gid_of(register(client))
    reply = client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "We checked the payment."}, headers=hdr(PRO, "fo.pro"))
    assert reply.status_code == 201, reply.text
    resolved = client.post(f"/api/v1/grievances/{gid}/resolution", json={"resolution": "Payment sent to the registered bank."},
        headers=hdr(PRO, "fo.pro", {"action": "resolve-grievance", "resource_id": gid,
                              "resource_version": reply.json()["data"]["version"]}))
    assert resolved.status_code == 200, resolved.text
    result = client.post(f"/api/v1/grievances/{gid}/feedback", json={"rating": 3, "satisfied": True}, headers=member())
    assert result.status_code == 201 and result.json()["data"]["state"] == "CLOSED", result.text
    return gid


def request(client, gid):
    return client.post(f"/api/v1/members/me/grievances/{gid}/reviews",
                       json={"reason": "The payment still has not reached my bank."}, headers=member())


def test_within_30_days_once_and_member_sees_deadlines(ctx):
    client, _ = ctx
    gid = closed(client)
    made = request(client, gid)
    assert made.status_code == 201, made.text
    assert made.json()["data"]["state"] == "PENDING"
    assert made.json()["data"]["request_deadline"] and made.json()["data"]["decision_due_at"]
    assert request(client, gid).status_code == 409
    shown = client.get(f"/api/v1/members/me/grievances/{gid}/review", headers=member())
    assert shown.status_code == 200 and shown.json()["data"]["reason"] == "The payment still has not reached my bank."
    assert client.get(f"/api/v1/members/me/grievances/{gid}/review", headers=hdr("other-member", "member")).status_code == 404


def test_after_30_days_is_refused(ctx):
    client, _ = ctx
    gid = closed(client)
    from app.infra.db import engine
    async def backdate():
        async with engine().begin() as connection:
            await connection.execute(text("UPDATE grievance_entries SET at=:at WHERE grievance_id=:gid AND state='CLOSED'"),
                                     {"at": datetime.now(UTC) - timedelta(days=31), "gid": gid})
    asyncio.run(backdate())
    assert request(client, gid).status_code == 409


def test_zonal_office_that_made_the_decision_cannot_review_its_own_case(ctx):
    client, _ = ctx
    gid = gid_of(register(client))
    assert client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "The regional office is checking."},
                       headers=hdr(PRO, "fo.pro")).status_code == 201
    assert client.post(f"/api/v1/grievances/{gid}/escalations", json={"reason": "The regional review was not sufficient."},
                       headers=hdr(PRO, "fo.pro")).status_code == 200
    zonal_reply = client.post(f"/api/v1/grievances/{gid}/messages", json={"body": "The zone checked the payment."},
                              headers=hdr(ZO, "zo.acc"))
    assert zonal_reply.status_code == 201
    resolved = client.post(f"/api/v1/grievances/{gid}/resolution", json={"resolution": "Payment re-issued by the zonal office."},
        headers=hdr(ZO, "zo.acc", {"action": "resolve-grievance", "resource_id": gid,
                                    "resource_version": zonal_reply.json()["data"]["version"]}))
    assert resolved.status_code == 200, resolved.text
    assert client.post(f"/api/v1/grievances/{gid}/feedback", json={"rating": 4, "satisfied": True}, headers=member()).status_code == 201
    assert request(client, gid).status_code == 201
    listed = client.get("/api/v1/office/grievance-reviews", headers=hdr(REVIEWER, "zo.rpfc1"))
    assert listed.status_code == 200 and all(r["grievance_id"] != gid for r in listed.json()["data"])
    decision = client.post(f"/api/v1/office/grievance-reviews/{gid}/decisions",
        json={"outcome": "UPHELD", "reasons": "The zonal office cannot review its own decision."},
        headers=hdr(REVIEWER, "zo.rpfc1"))
    assert decision.status_code == 404


@pytest.mark.parametrize("outcome", ["UPHELD", "FRESH_DECISION"])
def test_original_office_refused_both_outcomes_visible(ctx, outcome):
    client, _ = ctx
    gid = closed(client)
    assert request(client, gid).status_code == 201
    queue = "/api/v1/office/grievance-reviews"
    assert client.get(queue, headers=hdr(PRO, "fo.pro")).status_code == 403
    listed = client.get(queue, headers=hdr(REVIEWER, "zo.rpfc1"))
    assert listed.status_code == 200 and any(r["grievance_id"] == gid for r in listed.json()["data"]), listed.text
    url = f"{queue}/{gid}/decisions"
    body = {"outcome": outcome, "reasons": "The bank evidence warrants this outcome."}
    assert client.post(url, json=body, headers=hdr(PRO, "fo.pro")).status_code == 403
    decided = client.post(url, json=body, headers=hdr(REVIEWER, "zo.rpfc1"))
    assert decided.status_code == 200 and decided.json()["data"]["outcome"] == outcome, decided.text
    assert client.post(url, json=body, headers=hdr(REVIEWER, "zo.rpfc1")).status_code == 409
    shown = client.get(f"/api/v1/members/me/grievances/{gid}/review", headers=member())
    assert shown.json()["data"]["reasons"] == body["reasons"]
    if outcome == "FRESH_DECISION":
        assert client.get(f"/api/v1/grievances/{gid}", headers=member()).json()["data"]["state"] == "REOPEN_REQUESTED"
