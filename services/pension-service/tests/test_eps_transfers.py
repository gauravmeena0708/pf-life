"""The EPS service leg follows a posted Form 13 PF leg in either direction."""
import asyncio
import json
import uuid

from tests.test_pensions import SUBJECTS, ctx, hdr  # noqa: F401 (fixture)

PREVIEW = "/api/v1/members/me/pension-eligibility-preview"


def deliver(payload, event_id=None):
    from app.infra.db import sessions
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once

    event = {"event_id": event_id or str(uuid.uuid4()), "event_type": "TransferPosted.v1",
             "producer": "contribution-service", "correlation_id": str(uuid.uuid4()), "payload": payload}
    asyncio.run(apply_once(sessions(), event, dispatch))


def estimate(client, persona):
    response = client.get(PREVIEW, headers=hdr(SUBJECTS[persona], "member"))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_eps_transfer_in_both_directions_and_redelivery(ctx):
    client, q, _ = ctx
    from app.infra.messaging import BINDINGS

    assert "contribution-service.TransferPosted.v1" in BINDINGS
    priya_before = estimate(client, "member-p")
    assert [(s["account_link_id"], s["pf_with"]) for s in priya_before["service_by_member_id"]] == [
        ("AL-0914", "EPFO"), ("AL-0915", "TRUST Demo Steel Works Employees' Provident Fund Trust")]
    assert [s["eps_transferred_to"] for s in priya_before["service_by_member_id"]] == [None, None]

    epfo_to_trust = {"transfer_id": "TR-P-1", "uan": "100000000911", "from_account_link_id": "AL-0914",
                     "to_account_link_id": "AL-0915", "source": "EPFO", "destination": "TRUST"}
    deliver(epfo_to_trust)
    deliver(epfo_to_trust)  # a second event ID with the same transfer ID is also harmless
    priya_after = estimate(client, "member-p")
    assert priya_after["service_months_so_far"] == priya_before["service_months_so_far"]
    assert priya_after["scenarios"] == priya_before["scenarios"]
    assert priya_after["service_by_member_id"][0]["eps_transferred_to"] == "AL-0915"
    assert q("SELECT transfer_id, from_account_link_id, to_account_link_id, service_months, breaks_months "
             "FROM eps_transfers WHERE transfer_id='TR-P-1'")[0][1:3] == ("AL-0914", "AL-0915")
    assert q("SELECT COUNT(*) FROM eps_transfers WHERE transfer_id='TR-P-1'")[0][0] == 1
    out = q("SELECT payload FROM outbox WHERE event_type='EpsServiceTransferred.v1'")
    assert len(out) == 1
    posted = json.loads(out[0][0])["envelope"]["payload"]
    assert posted == {"transfer_id": "TR-P-1", "from_account_link_id": "AL-0914", "to_account_link_id": "AL-0915",
                      "service_months": priya_before["service_by_member_id"][0]["months"], "breaks_months": 0}

    ravi_before = estimate(client, "member-r")
    trust_to_epfo = {"transfer_id": "TR-R-1", "uan": "100000000912", "from_account_link_id": "AL-0918",
                     "to_account_link_id": "AL-0919", "source": "TRUST", "destination": "EPFO",
                     "service_from": "2015-01-01", "service_to": "2026-06-30", "breaks_months": 2}
    deliver(trust_to_epfo)
    deliver(trust_to_epfo)
    ravi_after = estimate(client, "member-r")
    assert ravi_after["service_months_so_far"] == ravi_before["service_months_so_far"] - 2
    assert ravi_after["service_by_member_id"][0]["pf_with"].startswith("TRUST ")
    assert ravi_after["service_by_member_id"][0]["breaks_months"] == 2
    assert ravi_after["service_by_member_id"][0]["eps_transferred_to"] == "AL-0919"
    assert q("SELECT breaks_months, transferred_to FROM eps_accounts WHERE account_link_id='AL-0918'") == [(2, "AL-0919")]
    rows = q("SELECT transfer_id, service_months, breaks_months FROM eps_transfers ORDER BY transfer_id")
    assert rows == [("TR-P-1", posted["service_months"], 0),
                    ("TR-R-1", ravi_before["service_by_member_id"][0]["months"], 2)]
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='EpsServiceTransferred.v1'")[0][0] == 2
