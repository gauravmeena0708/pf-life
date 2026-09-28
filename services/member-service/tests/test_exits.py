"""Mark Exit by the member, exits approved through the employer process, the member's applications, service
history, and the last contribution month and transfers kept from contribution-service events."""
import asyncio
import time
import uuid

import jwt

from tests.conftest import KEY, KID
from tests.test_member_api import SEED, api  # noqa: F401  (api is a fixture)
from tests.test_member_processes import outbox

MEMBER_D = SEED["keycloak_subjects"]["member-d"]
MEMBER_A = SEED["keycloak_subjects"]["member-a"]


def hdr(subject, step_up=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "member-service", "sub": subject, "stakeholder": "member",
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def deliver(event_type, payload):
    import app.infra.db as db
    from app.main import _route
    from epfo_persistence.consumer import apply_once
    event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "correlation_id": "c", "payload": payload}
    return asyncio.run(apply_once(db.sessions(), event, _route))


def mark(api, account="AL-0008", day="2025-12-31", subject=MEMBER_D):
    return api.post("/api/v1/members/me/exits", json={"account_link_id": account, "date_of_exit": day},
                    headers=hdr(subject, {"action": "mark-exit", "resource_id": account}))


def test_member_marks_the_exit_of_a_previous_member_id(api):
    history = api.get("/api/v1/members/me/service-history", headers=hdr(MEMBER_D)).json()["data"]
    old = next(m for m in history["member_ids"] if m["account_link_id"] == "AL-0008")
    assert old["establishment_name"] == "Demo Engineering Works" and old["mark_exit_allowed"] is True
    current = next(m for m in history["member_ids"] if m["account_link_id"] == "AL-0009")
    assert current["mark_exit_allowed"] is False                                   # still contributing
    assert "month of the last contribution" in mark(api, day="2025-11-30").json()["detail"]
    assert "two months after the last contribution" in mark(api, account="AL-0009", day="2026-08-31").json()["detail"]
    assert mark(api, subject=MEMBER_A).status_code == 404                        # not member A's member ID
    assert api.post("/api/v1/members/me/exits", json={"account_link_id": "AL-0008", "date_of_exit": "2025-12-31"},
                    headers=hdr(MEMBER_D)).status_code == 428                     # Aadhaar OTP (step-up) first
    r = mark(api)
    assert r.status_code == 200 and r.json()["data"]["date_of_exit"] == "2025-12-31", r.json()
    [event] = outbox("MemberExitMarked.v1")
    assert event == {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                     "reason": "CESSATION", "marked_by": "MEMBER"}
    assert "already marked" in mark(api).json()["detail"]
    apps = api.get("/api/v1/members/me/applications?status=processed", headers=hdr(MEMBER_D)).json()["data"]
    assert [(a["title"], a["state"]) for a in apps] == [("Mark Exit", "RECORDED")]


def test_ongoing_process_blocks_a_new_mark_exit(api):
    deliver("ProcessTransitioned.v1", {"process": "transfer_form13", "instance_id": "CASE-T1", "subject_ref": "100000000007",
                                       "from_state": None, "to_state": "SUBMITTED", "operation": "submit", "title": "Transfer of PF (Form 13)",
                                       "terminal": False, "visible_to_member": True, "actor_subject": MEMBER_D, "actor_role": "member",
                                       "data": {"from_account_link_id": "AL-0008", "to_account_link_id": "AL-0009"}})
    r = mark(api).json()
    assert r["type"] == "/problems/process-ongoing" and r["processes"][0]["process"] == "Transfer of PF (Form 13)"
    pending = api.get("/api/v1/members/me/applications?status=pending", headers=hdr(MEMBER_D)).json()["data"]
    assert [a["application_id"] for a in pending] == ["CASE-T1"]


def test_employer_exit_is_recorded_when_the_signatory_approves(api):
    base = {"process": "employer_exit", "instance_id": "CASE-E1", "subject_ref": "100000000001", "title": "Date of exit (employer)",
            "visible_to_member": True, "actor_subject": "sig", "actor_role": "employer.signatory",
            "data": {"account_link_id": "AL-0001", "date_of_exit": "2026-08-31", "reason": "CESSATION"}}
    deliver("ProcessTransitioned.v1", {**base, "from_state": None, "to_state": "EXIT_MARKED", "operation": "mark", "terminal": False})
    assert outbox("MemberExitMarked.v1") == []                                    # not until the signatory approves
    deliver("ProcessTransitioned.v1", {**base, "from_state": "EXIT_MARKED", "to_state": "APPROVED", "operation": "approve", "terminal": True})
    [event] = outbox("MemberExitMarked.v1")
    assert event["marked_by"] == "EMPLOYER" and event["account_link_id"] == "AL-0001"
    history = api.get("/api/v1/members/me/employment-history", headers=hdr(MEMBER_A)).json()["data"]
    assert history[0]["date_of_exit"] == "2026-08-31" and history[0]["exit_marked_by"] == "EMPLOYER"
    assert "EXIT_RECORDED" in [n["template"] for n in outbox("NotificationRequested.v1")]


def test_contributions_and_transfers_update_the_service_history(api):
    deliver("ContributionPosted.v1", {"journal_id": "J", "payment_id": "P", "filing_id": "F", "establishment_id": "EST-DEMO-0001",
                                      "wage_month": "2026-09", "postings": [{"account_code": "AC01_EPF", "side": "credit",
                                                                              "amount_paise": 1, "account_link_id": "AL-0009", "share": "employee"}]})
    deliver("TransferPosted.v1", {"transfer_id": "CASE-T1", "uan": "100000000007", "from_account_link_id": "AL-0008",
                                  "to_account_link_id": "AL-0009", "employee_paise": 12000000, "employer_paise": 8000000, "journal_id": "J2"})
    ids = {m["account_link_id"]: m for m in api.get("/api/v1/members/me/service-history", headers=hdr(MEMBER_D)).json()["data"]["member_ids"]}
    assert ids["AL-0009"]["last_contribution_month"] == "2026-09"
    assert ids["AL-0008"]["transfer_status"] == "Transferred to AL-0009" and ids["AL-0008"]["status"] == "TRANSFERRED"
    notice = [n for n in outbox("NotificationRequested.v1") if n["template"] == "TRANSFER_POSTED"][0]
    assert notice["params"]["amount_paise"] == 20000000
