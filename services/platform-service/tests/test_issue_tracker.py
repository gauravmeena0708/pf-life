"""NDC requests are scoped to the raiser and require IS step-up for execution."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_interest_declaration import q
from tests.test_policy_admin import ctx, hdr  # noqa: F401 (fixture)

SEED = json.loads((Path(__file__).resolve().parents[3] / "scripts/seed/synthetic.json").read_text())
S = SEED["keycloak_subjects"]
URL = "/api/v1/ndc/issue-tracker/requests"
BODY = {"kind": "FREEZE_MEMBER", "target_uan": "100000000002", "order_ref": "RO/ORDER/01",
        "reason": "Freeze ordered pending office verification."}


def events():
    return [(json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"])["envelope"]["payload"]
            for row in q("SELECT payload FROM outbox WHERE event_type='IssueTrackerExecuted.v1' ORDER BY id")]


@pytest.mark.parametrize("attach_order", [False, True])
def test_raise_freeze_with_optional_pdf_and_prevent_duplicate_open_request(ctx, attach_order):
    client, _ = ctx
    content = b"%PDF-1.4 x"
    body = {**BODY, **({"order_filename": "order.pdf", "order_base64": base64.b64encode(content).decode()} if attach_order else {})}
    raiser = hdr(S["ro-oic"], "fo.oic")
    response = client.post(URL, json=body, headers=raiser)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["state"] == "RAISED" and data["kind"] == "FREEZE_MEMBER"
    assert data["order_document"] == ({"filename": "order.pdf", "size_bytes": len(content),
                                       "sha256": hashlib.sha256(content).hexdigest()} if attach_order else None)
    assert client.post(URL, json=body, headers=raiser).status_code == 409
    assert len(q("SELECT request_id FROM issue_tracker_requests")) == 1
    assert events() == []


@pytest.mark.parametrize("changes", [
    {"order_base64": base64.b64encode(b"not a PDF").decode()},
    {"order_base64": "invalid base64!"},
    {"kind": "LOGIN_NOTICE"},
    {"kind": "LOGIN_NOTICE", "notice": "   "},
])
def test_invalid_order_and_missing_notice_are_rejected(ctx, changes):
    client, _ = ctx
    assert client.post(URL, json={**BODY, **changes}, headers=hdr(S["ro-oic"], "fo.oic")).status_code == 422
    assert q("SELECT request_id FROM issue_tracker_requests") == []


def test_is_lists_all_requests_and_raisers_only_their_own(ctx):
    client, _ = ctx
    mine = client.post(URL, json=BODY, headers=hdr(S["ro-oic"], "fo.oic"))
    other = client.post(URL, json={**BODY, "target_uan": "100000000001"},
                        headers=hdr(S["security-analyst"], "ho.security"))
    assert mine.status_code == other.status_code == 201
    for name, role, expected in (
        ("ndc-is", "ho.is", {mine.json()["data"]["request_id"], other.json()["data"]["request_id"]}),
        ("ro-oic", "fo.oic", {mine.json()["data"]["request_id"]}),
        ("security-analyst", "ho.security", {other.json()["data"]["request_id"]}),
    ):
        response = client.get(URL, headers=hdr(S[name], role))
        assert response.status_code == 200
        assert {r["request_id"] for r in response.json()["data"]} == expected


@pytest.mark.parametrize("decision,state", [("EXECUTE", "EXECUTED"), ("REJECT", "REJECTED")])
def test_execution_requires_request_bound_step_up_and_only_execute_publishes(ctx, decision, state):
    client, _ = ctx
    raised = client.post(URL, json=BODY, headers=hdr(S["ro-oic"], "fo.oic"))
    assert raised.status_code == 201
    request_id = raised.json()["data"]["request_id"]
    url = f"{URL}/{request_id}/executions"
    body = {"decision": decision, "note": "Order checked by the IS Division"}
    assert client.post(url, json=body, headers=hdr(S["ndc-is"], "ho.is")).status_code == 428
    for action, resource in (("execute-issue-tracker", "ITR-OTHER"), ("other-action", request_id)):
        assert client.post(url, json=body, headers=hdr(S["ndc-is"], "ho.is",
                           {"action": action, "resource_id": resource})).status_code == 403
    assert events() == []
    headers = hdr(S["ndc-is"], "ho.is", {"action": "execute-issue-tracker", "resource_id": request_id})
    response = client.post(url, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == state
    assert response.json()["data"]["execution_note"] == body["note"]
    assert events() == ([{"request_id": request_id, "kind": "FREEZE_MEMBER", "target_uan": BODY["target_uan"],
                         "order_ref": BODY["order_ref"], "notice": ""}] if decision == "EXECUTE" else [])
    before = events()
    assert client.post(url, json=body, headers=headers).status_code == 409
    assert events() == before


def test_members_cannot_raise_list_or_execute_requests(ctx):
    client, _ = ctx
    member = hdr(S["member-a"], "member")
    assert client.post(URL, json=BODY, headers=member).status_code == 403
    assert client.get(URL, headers=member).status_code == 403
    raised = client.post(URL, json=BODY, headers=hdr(S["ro-oic"], "fo.oic")).json()["data"]
    assert client.post(f"{URL}/{raised['request_id']}/executions", json={"decision": "EXECUTE", "note": "Member tries execution"},
                       headers=member).status_code == 403
    assert events() == []
