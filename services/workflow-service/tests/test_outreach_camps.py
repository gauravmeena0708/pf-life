"""NAN assistance: camp jurisdiction, request validation, references and outbox."""
import asyncio
from datetime import date

from sqlalchemy import insert

from tests.test_cases_api import S, ctx, hdr  # noqa: F401 (ctx is a fixture)
from tests.test_locks_and_freeze import events

from app.infra.tables import outreach_camps

CAMP = "NAN-RO1-2026-10"
URL = f"/api/v1/office/outreach-camps/{CAMP}/assisted-requests"
BODY = {"kind": "GRIEVANCE", "name": "Synthetic Visitor", "mobile": "9876543210",
        "uan": "100000000001", "details": "Needs help with a contribution grievance."}


def officer():
    return hdr(S["ro-nan"], "fo.nan")


def test_camp_seed_is_idempotent_and_scope_is_enforced(ctx):
    client, q, _ = ctx
    assert q(f"SELECT office_id, held_on FROM outreach_camps WHERE camp_id='{CAMP}'") == [
        ("RO-DEMO-01", "2026-10-27")]
    from app import seed
    asyncio.run(seed.main())
    assert q(f"SELECT count(*) FROM outreach_camps WHERE camp_id='{CAMP}'") == [(1,)]

    from app.infra.db import sessions

    async def other_camp():
        async with sessions()() as session, session.begin():
            await session.execute(insert(outreach_camps).values(
                camp_id="NAN-OTHER", office_id="RO-DEMO-02", held_on=date(2026, 10, 28), venue="Other office hall"))
    asyncio.run(other_camp())
    other = "/api/v1/office/outreach-camps/NAN-OTHER/assisted-requests"
    assert client.post(other, json=BODY, headers=officer()).status_code == 404
    assert client.post("/api/v1/office/outreach-camps/UNKNOWN/assisted-requests",
                       json=BODY, headers=officer()).status_code == 404
    assert client.post(URL, json=BODY, headers=hdr(S["ro-pro"], "fo.pro")).status_code == 403
    assert q("SELECT count(*) FROM camp_requests") == [(0,)]
    assert events(q, "CampRequestTaken.v1") == []


def test_validation_rejects_bad_kind_contact_and_details(ctx):
    client, q, _ = ctx
    for change in ({"kind": "OTHER"}, {"mobile": "123"}, {"uan": "123456"}, {"details": "short"}):
        response = client.post(URL, json={**BODY, **change}, headers=officer())
        assert response.status_code == 400, response.text
    assert q("SELECT count(*) FROM camp_requests") == [(0,)]
    assert events(q, "CampRequestTaken.v1") == []


def test_requests_get_camp_sequence_counts_next_step_and_event(ctx):
    client, q, _ = ctx
    first = client.post(URL, json=BODY, headers=officer())
    assert first.status_code == 200, first.text
    one = first.json()["data"]
    assert one["reference"] == f"NAN/{CAMP}/1"
    assert one["next_step"] == "Registered for the PRO to enter in the grievance system."
    assert one["camp"]["request_counts"] == {"GRIEVANCE": 1, "CLAIM_HELP": 0, "KYC_UPDATE": 0,
                                               "INOPERATIVE_ACCOUNT": 0, "PENSION": 0, "UAN_HELP": 0}
    assert one["camp"]["held_on"] == "2026-10-27"

    second = client.post(URL, json={**BODY, "kind": "INOPERATIVE_ACCOUNT", "uan": None}, headers=officer())
    assert second.status_code == 200, second.text
    two = second.json()["data"]
    assert two["reference"] == f"NAN/{CAMP}/2"
    assert two["request_id"] != one["request_id"]
    assert two["next_step"] == "Verification through co-workers by the DA (Accounts); then reactivation by the AO."
    assert two["camp"]["request_counts"]["GRIEVANCE"] == 1
    assert two["camp"]["request_counts"]["INOPERATIVE_ACCOUNT"] == 1
    assert q("SELECT request_number, reference, kind, uan FROM camp_requests ORDER BY request_number") == [
        (1, f"NAN/{CAMP}/1", "GRIEVANCE", "100000000001"),
        (2, f"NAN/{CAMP}/2", "INOPERATIVE_ACCOUNT", None)]
    assert events(q, "CampRequestTaken.v1") == [
        {"request_id": one["request_id"], "camp_id": CAMP, "office_id": "RO-DEMO-01", "kind": "GRIEVANCE"},
        {"request_id": two["request_id"], "camp_id": CAMP, "office_id": "RO-DEMO-01", "kind": "INOPERATIVE_ACCOUNT"}]
    assert q("SELECT count(*) FROM audit_local WHERE action='outreach.assisted_request'") == [(2,)]
