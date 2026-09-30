"""Issue Tracker callbacks, employer location mappings and HR posting replication."""
import asyncio
import json
import uuid
from datetime import date

from sqlalchemy import select, update

from tests.test_exits import deliver
from tests.test_member_api import SEED, api, token  # noqa: F401 (fixture)
from tests.test_member_processes import outbox
from tests.test_onboarding import hdr, operator

S = SEED["keycloak_subjects"]
UAN = "100000000002"


def issue(kind, uan=UAN, request_id="ITR-TEST", notice=""):
    return {"request_id": request_id, "kind": kind, "target_uan": uan, "order_ref": "RO/ORDER/01", "notice": notice}


def test_issue_tracker_freezes_once_and_defreezes_member(api):
    headers = token(S["member-b"])
    assert api.get("/api/v1/members/me", headers=headers).json()["data"]["account_state"] == "ACTIVE"
    payload = issue("FREEZE_MEMBER")
    assert deliver("IssueTrackerExecuted.v1", payload) is True
    assert api.get("/api/v1/members/me", headers=headers).json()["data"]["account_state"] == "FROZEN"
    assert outbox("AccountFrozen.v1") == [{"target_type": "member", "target_id": UAN,
                                          "category": "ISSUE_TRACKER", "order_ref": payload["order_ref"]}]
    assert deliver("IssueTrackerExecuted.v1", payload) is True  # fresh envelope, same already-applied operation
    assert len(outbox("AccountFrozen.v1")) == 1
    assert deliver("IssueTrackerExecuted.v1", issue("DEFREEZE_MEMBER", request_id="ITR-DEFREEZE")) is True
    assert api.get("/api/v1/members/me", headers=headers).json()["data"]["account_state"] == "ACTIVE"
    assert outbox("AccountDefrozen.v1") == [{"target_type": "member", "target_id": UAN, "order_ref": payload["order_ref"]}]
    assert deliver("IssueTrackerExecuted.v1", issue("DEFREEZE_MEMBER", request_id="ITR-DEFREEZE")) is True
    assert len(outbox("AccountDefrozen.v1")) == 1


def test_issue_tracker_login_notice_is_addressed_and_renders_for_member_a(api):
    from app.domain.notifications import handle_notification_requested, render
    from app.infra.db import sessions
    from epfo_persistence.consumer import apply_once

    payload = issue("LOGIN_NOTICE", "100000000001", "ITR-NOTICE", "Please visit your regional office with the order.")
    assert deliver("IssueTrackerExecuted.v1", payload) is True
    [notice] = outbox("NotificationRequested.v1")
    assert notice == {"recipient_subject": S["member-a"], "template": "OFFICE_NOTICE", "reference_id": "ITR-NOTICE",
                      "params": {"reason": payload["notice"]}}
    title, body = render(notice["template"], notice["reference_id"], notice["params"])
    assert title == "Notice from EPFO"
    assert body == f"{payload['notice']} (reference ITR-NOTICE)"
    event = {"event_id": str(uuid.uuid4()), "event_type": "NotificationRequested.v1", "payload": notice}
    assert asyncio.run(apply_once(sessions(), event, handle_notification_requested)) is True
    assert asyncio.run(apply_once(sessions(), event, handle_notification_requested)) is False
    response = api.get("/api/v1/members/me/notifications", headers=token(S["member-a"]))
    assert response.status_code == 200
    assert [(n["title"], n["body"]) for n in response.json()["data"]] == [(title, body)]
    assert api.get("/api/v1/members/me/notifications", headers=token(S["member-b"])).json()["data"] == []


LOCATION = {"account_link_id": "AL-0001", "branch_code": "BR-01", "district": "  new delhi  ", "pincode": "110001"}
URL = "/api/v1/employers/me/members/100000000001/location-mappings"


def test_operator_maps_location_and_member_list_shows_it(api):
    response = api.post(URL, json=LOCATION, headers=operator())
    assert response.status_code == 200, response.text
    expected = {"branch_code": "BR-01", "district": "NEW DELHI", "pincode": "110001"}
    assert response.json()["data"]["location"] == expected
    listed = api.get("/api/v1/employers/me/members", headers=operator())
    assert listed.status_code == 200
    member = next(m for m in listed.json()["data"] if m["account_link_id"] == "AL-0001")
    assert member["location"] == expected


def test_location_rejects_bad_pincode(api):                   # request validation answers 400 across the POC
    response = api.post(URL, json={**LOCATION, "pincode": "012345"}, headers=operator())
    listed = api.get("/api/v1/employers/me/members", headers=operator()).json()["data"]
    assert next(m for m in listed if m["account_link_id"] == "AL-0001")["location"] is None
    assert response.status_code == 400, response.text


def test_location_rejects_another_establishments_member(api):
    other = hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"], establishment="EST-DEMO-0002")
    assert api.post(URL, json=LOCATION, headers=other).status_code == 404
    listed = api.get("/api/v1/employers/me/members", headers=operator()).json()["data"]
    assert next(m for m in listed if m["account_link_id"] == "AL-0001")["location"] is None


def test_location_rejects_an_exited_member_id(api):
    from app.infra.db import sessions
    from app.infra.tables import employments

    async def mark_exited():
        async with sessions()() as session, session.begin():
            await session.execute(update(employments).where(employments.c.account_link_id == "AL-0001").values(
                date_of_exit=date(2026, 8, 31)))
    asyncio.run(mark_exited())
    assert api.post(URL, json=LOCATION, headers=operator()).status_code == 409


def test_staff_posting_event_updates_the_member_service_copy(api):
    from app.infra.db import sessions
    from app.infra.tables import office_staff

    async def posting():
        async with sessions()() as session:
            return dict((await session.execute(select(office_staff).where(office_staff.c.subject == S["ro-oic"]))).mappings().one())
    assert asyncio.run(posting())["office_id"] == "RO-DEMO-01"
    assert deliver("StaffPostingChanged.v1", {"subject": S["ro-oic"], "username": "ro-oic", "stakeholder": "fo.apfc",
                                            "office_id": "RO-DEMO-02", "previous_stakeholder": "fo.oic",
                                            "previous_office_id": "RO-DEMO-01"}) is True
    assert asyncio.run(posting()) == {"subject": S["ro-oic"], "stakeholder": "fo.apfc", "office_id": "RO-DEMO-02"}
