"""member-service as owner of the freeze and Joint Declaration contracts (callbacks from the process engine)."""
import asyncio
import json
import uuid

from sqlalchemy import text

from tests.test_member_api import MEMBER_B, SEED, api, token  # noqa: F401  (api is a fixture)


def deliver(payload):
    import app.infra.db as db
    from app.domain.processes import on_process_transitioned
    from epfo_persistence.consumer import apply_once
    event = {"event_id": str(uuid.uuid4()), "event_type": "ProcessTransitioned.v1", "correlation_id": "c", "payload": payload}
    return asyncio.run(apply_once(db.sessions(), event, on_process_transitioned)), event


def outbox(event_type):
    import app.infra.db as db

    async def run():
        async with db.engine().connect() as c:
            return (await c.execute(text("SELECT payload FROM outbox WHERE event_type=:t ORDER BY id"), {"t": event_type})).all()
    return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for (p,) in asyncio.run(run())]


def jd(to_state, parameter="NAME", value="BHARAT KUMAR DEMO"):
    return {"process": "joint_declaration", "instance_id": "CASE-JD1", "subject_ref": "100000000002", "from_state": "VERIFIED",
            "to_state": to_state, "operation": "decide", "actor_subject": "apfc-1", "actor_role": "fo.apfc",
            "data": {"parameter": parameter, "current_value": "BHARAT DEMO", "corrected_value": value,
                     "reason": "Name incomplete in employer records", "change_class": "MAJOR"}}


def test_approved_name_correction_is_applied_once_and_published(api):
    applied, event = deliver(jd("APPROVED"))
    assert applied
    import app.infra.db as db
    from app.domain.processes import on_process_transitioned
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), {**event, "event_id": str(uuid.uuid4())}, on_process_transitioned))  # a re-sent copy
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["name"] == "BHARAT KUMAR DEMO"
    [change] = outbox("MemberChangeApproved.v1")                       # applied once even when sent twice
    assert change == {"request_id": "CASE-JD1", "uan": "100000000002", "approver_subject": "apfc-1",
                      "parameters": [{"parameter": "NAME", "value": "BHARAT KUMAR DEMO"}]}
    assert outbox("NotificationRequested.v1")[0]["template"] == "JD_APPROVED"


def test_minor_field_goes_to_the_extra_profile(api):
    deliver(jd("APPROVED", parameter="FATHER_NAME", value="RAMESH DEMO"))
    me = api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]
    assert me["profile_extra"] == {"father_name": "RAMESH DEMO"}


def test_rejection_notifies_without_changing_anything(api):
    deliver(jd("REJECTED"))
    assert api.get("/api/v1/members/me", headers=token(MEMBER_B)).json()["data"]["name"] == SEED["members"][1]["name"]
    assert outbox("MemberChangeApproved.v1") == [] and outbox("NotificationRequested.v1")[0]["template"] == "JD_REJECTED"
