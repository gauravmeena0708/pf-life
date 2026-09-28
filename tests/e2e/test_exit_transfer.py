"""Phase 2, slice 1 on the running stack: dates of exit and Form 13 transfer.

Member D (synthetic) has two member IDs: AL-0008 at Demo Engineering Works (left, exit never marked) and AL-0009
at the demo establishment. The member marks the exit (step-up), asks to transfer AL-0008 into AL-0009, the present
employer's signatory attests, the DA verifies, the AO approves; the ledger moves the balance and the member gets
Annexure K. An employer-marked exit waits for the signatory (here rejected, so the demo data stays usable).
On a rerun the steps already done are checked instead (`make reset` restores the start).
"""
from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

UAN_D = "100000000007"


def service(page):
    return {m["account_link_id"]: m for m in call(page, "GET", "/api/v1/members/me/service-history")[1]["data"]["member_ids"]}


def test_member_marks_exit_and_transfers_the_previous_member_id(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))     # a fresh stack: the signatory's grants first
    member = persona("member-d", "/member/service")
    ids = service(member)
    assert set(ids) >= {"AL-0008", "AL-0009"}
    if not ids["AL-0008"]["date_of_exit"]:
        status, r = call(member, "POST", "/api/v1/members/me/exits", {"account_link_id": "AL-0008", "date_of_exit": "2025-12-31"},
                         {"X-Step-Up-Token": step_up(member, "mark-exit", "AL-0008")})
        assert status == 200 and r["data"]["date_of_exit"] == "2025-12-31", r
    status, again = call(member, "POST", "/api/v1/members/me/exits", {"account_link_id": "AL-0008", "date_of_exit": "2025-12-31"},
                         {"X-Step-Up-Token": step_up(member, "mark-exit", "AL-0008")})
    assert (status, again["type"]) in ((422, "/problems/exit-not-allowed"), (409, "/problems/process-ongoing")), again   # never twice

    if not service(member)["AL-0008"]["transferred_to"]:
        body = {"from_account_link_id": "AL-0008", "to_account_link_id": "AL-0009", "attesting_employer": "PRESENT"}
        open_case = next((a for a in call(member, "GET", "/api/v1/members/me/applications?status=pending")[1]["data"]
                          if a["process"] == "transfer_form13"), None)       # left open by an interrupted run: carry on
        if open_case:
            case = call(member, "GET", f"/api/v1/members/me/transfers/{open_case['application_id']}")[1]["data"]
        else:
            status, r = wait_for(lambda: (lambda x: x if x[0] == 200 else None)(call(
                member, "POST", "/api/v1/members/me/transfers", body, {"X-Step-Up-Token": step_up(member, "submit-transfer", UAN_D)})),
                timeout=20, every=2)                                     # the exit reaches the engine asynchronously
            case = r["data"]
        if case["state"] == "SUBMITTED":
            signatory = persona("emp-signatory", "/employer/members")
            queued = wait_for(lambda: next((c for c in call(signatory, "GET", "/api/v1/employers/me/transfer-requests")[1]["data"]
                                            if c["case_id"] == case["case_id"]), None))
            status, r = call(signatory, "POST", f"/api/v1/employers/me/transfer-requests/{case['case_id']}/decisions",
                             {"decision": "ATTEST", "note": "Present employee"},
                             {"X-Step-Up-Token": step_up(signatory, "attest-transfer", case["case_id"], queued["version"])})
            assert status == 200 and r["data"]["state"] == "EMPLOYER_ATTESTED", r
            case = r["data"]
        if case["state"] == "EMPLOYER_ATTESTED":
            da = persona("do-caseworker", "/office/work-queue")
            status, r = call(da, "POST", f"/api/v1/office/transfers/{case['case_id']}/verifications",
                             {"service_checked": "YES", "note": "Service at both establishments checked"})
            assert status == 200 and r["data"]["state"] == "VERIFIED", r
            case = r["data"]
        ao = persona("ro-ao", "/office/work-queue")
        status, r = call(ao, "POST", f"/api/v1/office/transfers/{case['case_id']}/decisions",
                         {"decision": "APPROVE", "reason": "Service and balance verified"},
                         {"X-Step-Up-Token": step_up(ao, "decide-transfer", case["case_id"], case["version"])})
        assert status == 200 and r["data"]["state"] == "APPROVED", r
        mine = call(member, "GET", f"/api/v1/members/me/transfers/{case['case_id']}")[1]["data"]
        assert mine["state"] == "APPROVED" and [h["action"] for h in mine["history"]] == ["SUBMIT", "ATTEST", "VERIFY", "DECIDE"]

    wait_for(lambda: service(member)["AL-0008"]["transferred_to"] == "AL-0009", timeout=30)
    apps = call(member, "GET", "/api/v1/members/me/applications?status=processed")[1]["data"]
    transfer = next(a for a in apps if a["process"] == "transfer_form13" and a["state"] == "APPROVED")
    k = call(member, "GET", f"/api/v1/members/me/transfers/{transfer['application_id']}/annexure-k")[1]["data"]
    assert k["transferred_from"]["member_id"] == "AL-0008" and k["total_paise"] > 0
    book = {a["account_link_id"]: a for a in call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]["accounts"]}
    assert book["AL-0008"]["entries"][-1]["running_balance_paise"] == 0
    assert any(e["kind"] == "TRANSFER_IN" for e in book["AL-0009"]["entries"])
    member.goto(f"{WEB}/member/service")
    member.get_by_role("heading", name="Recent applications").wait_for()
    member.get_by_role("button", name="Annexure K").first.click()
    member.get_by_role("heading", name=f"Annexure K — transfer {transfer['application_id']}").wait_for()
    SHOTS.mkdir(exist_ok=True)
    member.screenshot(path=str(SHOTS / "p2-service-transfer.png"), full_page=True)


def test_employer_marked_exit_waits_for_the_signatory(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    operator = persona("emp-preparer", "/employer/members")
    exit_body = {"account_link_id": "AL-0002", "date_of_exit": "2026-08-31", "reason": "CESSATION"}
    status, r = call(operator, "POST", "/api/v1/employers/me/members/100000000002/exits", exit_body,
                     {"X-Step-Up-Token": step_up(operator, "mark-exit-employer", "100000000002")})
    assert status == 200 and r["data"]["state"] == "EXIT_MARKED", r
    case = r["data"]
    status, r = call(operator, "POST", "/api/v1/employers/me/members/100000000002/exits", exit_body,
                     {"X-Step-Up-Token": step_up(operator, "mark-exit-employer", "100000000002")})
    assert status == 409                                                   # one open exit per member at a time
    signatory = persona("emp-signatory", "/employer/members")
    listed = call(signatory, "GET", "/api/v1/employers/me/approvals")[1]["data"]
    assert case["case_id"] in [c["case_id"] for c in listed]
    signatory.goto(f"{WEB}/employer/members")
    signatory.get_by_role("heading", name="Approvals — dates of exit").wait_for()
    signatory.screenshot(path=str(SHOTS / "p2-employer-approvals.png"), full_page=True)
    status, r = call(signatory, "POST", f"/api/v1/employers/me/approvals/{case['case_id']}/decisions",
                     {"decision": "REJECT", "note": "Test run: member B is still employed"},
                     {"X-Step-Up-Token": step_up(signatory, "approve-exit", case["case_id"], case["version"])})
    assert status == 200 and r["data"]["state"] == "REJECTED", r
    member = persona("member-b", "/member/service")
    assert service(member)["AL-0002"]["date_of_exit"] is None
