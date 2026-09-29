"""Employer-marked exit (operator marks, signatory approves) and Form 13 transfer (member → present employer →
DA → AO) on the process engine, with account and date checks against the member-account projection."""
import asyncio
import json
import uuid

from tests.test_cases_api import S, ctx  # noqa: F401  (ctx is a fixture)
from tests.test_joint_declaration import EST, hdr, transitions

MEMBER_D, MEMBER_B = S["member-d"], S["member-b"]
OPERATOR, SIGNATORY, DA, AO = S["emp-preparer"], S["emp-signatory"], S["do-caseworker"], S["ro-ao"]
UAN_D, UAN_B = "100000000007", "100000000002"


def deliver(event_type, payload):
    import app.infra.db as db
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once
    event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "correlation_id": str(uuid.uuid4()), "payload": payload}
    asyncio.run(apply_once(db.sessions(), event, dispatch))


def transfer(client, frm="AL-0008", to="AL-0009", subject=MEMBER_D):
    return client.post("/api/v1/members/me/transfers", json={"from_account_link_id": frm, "to_account_link_id": to,
                                                              "attesting_employer": "PRESENT"},
                       headers=hdr(subject, "member", {"action": "submit-transfer", "resource_id": UAN_D}))


def step(client, path, case, subject, role, body, action=None, establishment=None):
    su = {"action": action, "resource_id": case["case_id"], "resource_version": case["version"]} if action else None
    return client.post(path, json=body, headers=hdr(subject, role, su, establishment))


def test_employer_exit_needs_the_signatory_and_valid_dates(ctx):
    client, q, _ = ctx
    url = f"/api/v1/employers/me/members/{UAN_B}/exits"
    body = {"account_link_id": "AL-0002", "date_of_exit": "2026-08-31", "reason": "CESSATION"}
    op = hdr(OPERATOR, "employer.operator", {"action": "mark-exit-employer", "resource_id": UAN_B}, establishment=EST)
    bad = client.post(url, json={**body, "date_of_exit": "2020-01-31"}, headers=op).json()
    assert "before the date of joining" in bad["detail"]
    assert "future" in client.post(url, json={**body, "date_of_exit": "2099-01-31"}, headers=op).json()["detail"]
    assert "no such member account" in client.post(url, json={**body, "account_link_id": "AL-0001"}, headers=op).json()["detail"]
    assert client.post(url, json=body, headers=hdr(OPERATOR, "employer.operator", {"action": "mark-exit-employer", "resource_id": UAN_B},
                                                   establishment="EST-DEMO-0002")).status_code == 404
    case = client.post(url, json=body, headers=op).json()["data"]
    assert case["state"] == "EXIT_MARKED"
    listed = client.get("/api/v1/employers/me/approvals", headers=hdr(SIGNATORY, "employer.signatory", establishment=EST)).json()["data"]
    assert [c["case_id"] for c in listed] == [case["case_id"]]
    path = f"/api/v1/employers/me/approvals/{case['case_id']}/decisions"
    assert step(client, path, case, SIGNATORY, "employer.signatory", {"decision": "APPROVE", "note": "Left on 31 August"},
                establishment=EST).status_code == 428
    done = step(client, path, case, SIGNATORY, "employer.signatory", {"decision": "APPROVE", "note": "Left on 31 August"},
                "approve-exit", EST).json()["data"]
    assert done["state"] == "APPROVED" and transitions(q) == ["EXIT_MARKED", "APPROVED"]
    payload = json.loads(q("SELECT payload FROM outbox WHERE event_type='ProcessTransitioned.v1' ORDER BY id DESC LIMIT 1")[0][0])
    assert payload["envelope"]["payload"]["terminal"] is True and payload["envelope"]["payload"]["visible_to_member"] is True


def test_transfer_from_an_exited_member_id_through_employer_da_and_ao(ctx):
    client, q, _ = ctx
    assert "must be marked first" in transfer(client).json()["detail"]                 # AL-0008 has no exit yet
    assert "no such member account" in transfer(client, frm="AL-0002").json()["detail"]  # not member D's account
    deliver("MemberExitMarked.v1", {"uan": UAN_D, "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                                    "reason": "CESSATION", "marked_by": "MEMBER"})
    r = transfer(client)
    assert r.status_code == 200, r.json()
    case = r.json()["data"]
    assert case["state"] == "SUBMITTED"
    mine = client.get(f"/api/v1/members/me/transfers/{case['case_id']}", headers=hdr(MEMBER_D, "member")).json()["data"]
    assert mine["state"] == "SUBMITTED" and mine["history"][0]["action"] == "SUBMIT"
    assert client.get(f"/api/v1/members/me/transfers/{case['case_id']}", headers=hdr(MEMBER_B, "member")).status_code == 404
    queued = client.get("/api/v1/employers/me/transfer-requests", headers=hdr(SIGNATORY, "employer.signatory", establishment=EST)).json()["data"]
    assert [c["case_id"] for c in queued] == [case["case_id"]]
    pending = client.get("/api/v1/employers/me/pending-approvals", headers=hdr(SIGNATORY, "employer.signatory", establishment=EST)).json()["data"]
    assert [(i["case_id"], i["action"], i["title"]) for i in pending["items"]] == [(case["case_id"], "attest", "Transfer of PF (Form 13)")]
    assert pending["items"][0]["operation"]["step_up"]["action"] == "attest-transfer"
    case = step(client, f"/api/v1/employers/me/transfer-requests/{case['case_id']}/decisions", case, SIGNATORY, "employer.signatory",
                {"decision": "ATTEST", "note": "Present employee"}, "attest-transfer", EST).json()["data"]
    verify = {"service_checked": "YES", "note": "Service at both establishments checked"}
    unseen = step(client, f"/api/v1/office/transfers/{case['case_id']}/verifications", case, DA, "fo.da_accounts", verify)
    assert unseen.status_code == 409 and unseen.json()["type"] == "/problems/attestation-not-viewed"   # open the signed PDF first
    [doc] = client.get(f"/api/v1/office/cases/{case['case_id']}", headers=hdr(DA, "fo.da_accounts")).json()["data"]["documents"]
    assert doc["doc_type"] == "FORM13_EMPLOYER_SIGNED" and doc["viewed_by_you"] is False
    seen = client.post(f"/api/v1/office/cases/{case['case_id']}/documents/{doc['doc_id']}/attestation-views", headers=hdr(DA, "fo.da_accounts"))
    assert seen.status_code == 201 and seen.json()["data"]["content"]["signed_by_role"] == "employer.signatory"
    case = step(client, f"/api/v1/office/transfers/{case['case_id']}/verifications", case, DA, "fo.da_accounts", verify).json()["data"]
    assert case["state"] == "VERIFIED" and case["current_role"] == "fo.ao"
    done = step(client, f"/api/v1/office/transfers/{case['case_id']}/decisions", case, AO, "fo.ao",
                {"decision": "APPROVE", "reason": "Service and balance verified"}, "decide-transfer").json()["data"]
    assert done["state"] == "APPROVED"
    assert transitions(q) == ["SUBMITTED", "EMPLOYER_ATTESTED", "VERIFIED", "APPROVED"]
    deliver("TransferPosted.v1", {"transfer_id": case["case_id"], "uan": UAN_D, "from_account_link_id": "AL-0008",
                                  "to_account_link_id": "AL-0009", "employee_paise": 1, "employer_paise": 1, "journal_id": "J"})
    assert "already transferred to AL-0009" in transfer(client).json()["detail"]


def test_a_registered_joinee_can_be_exited_by_the_employer(ctx):
    client, _, _ = ctx
    deliver("MemberRegistered.v1", {"uan": "100000000008", "account_link_id": "AL-0010", "member_subject": None, "name": "KIRAN DEMO",
                                    "date_of_birth": "1998-03-04", "gender": "FEMALE", "establishment_id": EST,
                                    "date_of_joining": "2026-09-01", "new_uan": True, "pan_verified": False})
    r = client.post("/api/v1/employers/me/members/100000000008/exits",
                    json={"account_link_id": "AL-0010", "date_of_exit": "2026-09-15", "reason": "CESSATION"},
                    headers=hdr(OPERATOR, "employer.operator", {"action": "mark-exit-employer", "resource_id": "100000000008"}, establishment=EST))
    assert r.status_code == 200 and r.json()["data"]["state"] == "EXIT_MARKED", r.json()
