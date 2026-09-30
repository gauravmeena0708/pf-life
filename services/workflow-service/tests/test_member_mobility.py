"""Phase 2, slice 8b on the process engine: the employer corrects a date of exit (the signatory approves it as an
exit), uploads exits in bulk (one case per valid line), and files a Joint Declaration itself."""
from tests.test_cases_api import S, ctx  # noqa: F401  (ctx is a fixture)
from tests.test_exit_transfer import deliver, step
from tests.test_joint_declaration import EST, hdr

OPERATOR, SIGNATORY = S["emp-preparer"], S["emp-signatory"]
UAN_A, UAN_B = "100000000001", "100000000002"


def test_a_marked_exit_can_be_corrected_and_the_signatory_approves_it(ctx):
    client, q, _ = ctx
    url = f"/api/v1/employers/me/members/{UAN_B}/exit-corrections"
    body = {"account_link_id": "AL-0002", "date_of_exit": "2026-08-15", "reason": "CESSATION",
            "correction_note": "The last working day was the 15th, not the 31st"}
    op = hdr(OPERATOR, "employer.operator", {"action": "correct-exit-employer", "resource_id": UAN_B}, establishment=EST)
    assert "must be marked first" in client.post(url, json=body, headers=op).json()["detail"]
    deliver("MemberExitMarked.v1", {"uan": UAN_B, "account_link_id": "AL-0002", "date_of_exit": "2026-08-31",
                                    "reason": "CESSATION", "marked_by": "EMPLOYER"})
    assert client.post(url, json={**body, "correction_note": "short"}, headers=op).status_code == 422
    case = client.post(url, json=body, headers=op).json()["data"]
    assert case["state"] == "CORRECTION_MARKED"
    listed = client.get("/api/v1/employers/me/approvals", headers=hdr(SIGNATORY, "employer.signatory", establishment=EST)).json()["data"]
    assert case["case_id"] in [c["case_id"] for c in listed]
    done = step(client, f"/api/v1/employers/me/approvals/{case['case_id']}/decisions", case, SIGNATORY, "employer.signatory",
                {"decision": "APPROVE", "note": "Corrected date checked"}, "approve-exit", EST).json()["data"]
    assert done["state"] == "APPROVED" and done["data"]["correction_note"].startswith("The last working day")


def test_bulk_exits_start_one_case_per_valid_line(ctx):
    client, *_ = ctx
    url = "/api/v1/employers/me/members/exit-bulk-uploads"
    content = ("uan,account_link_id,date_of_exit,reason\n"
               f"{UAN_A},AL-0001,2026-08-31,CESSATION\n"
               f"{UAN_B},AL-0001,2026-08-31,CESSATION\n"          # not B's account
               f"{UAN_B},AL-0002,2099-01-01,CESSATION\n")         # in the future
    assert client.post(url, json={"content": content}, headers=hdr(OPERATOR, "employer.operator", establishment=EST)).status_code == 428
    r = client.post(url, json={"content": content},
                    headers=hdr(OPERATOR, "employer.operator", {"action": "mark-exit-bulk", "resource_id": EST}, establishment=EST))
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert out["lines"] == 3 and out["accepted"] == 1
    assert [x["status"] for x in out["results"]] == ["ACCEPTED", "ERROR", "ERROR"]
    assert "no such member account" in out["results"][1]["error"] and "future" in out["results"][2]["error"]
    again = client.post(url, json={"content": content.splitlines()[1]},
                        headers=hdr(OPERATOR, "employer.operator", {"action": "mark-exit-bulk", "resource_id": EST}, establishment=EST))
    assert "already in progress" in again.json()["data"]["results"][0]["error"]


def test_the_employer_can_file_a_joint_declaration_already_attested(ctx):
    client, *_ = ctx
    body = {"uan": UAN_A, "parameter": "FATHER_NAME", "current_value": "RAMESH", "corrected_value": "RAMESH KUMAR",
            "reason": "Spelling as in the Aadhaar record", "member_consent": "MOCK_AADHAAR_OTP"}
    url = "/api/v1/employers/me/joint-declarations"
    su = {"action": "submit-joint-declaration-employer", "resource_id": UAN_A}
    assert client.post(url, json=body, headers=hdr(SIGNATORY, "employer.signatory", su, establishment="EST-DEMO-0002")).status_code == 404
    assert client.post(url, json={**body, "member_consent": None}, headers=hdr(SIGNATORY, "employer.signatory", su, establishment=EST)).status_code == 422
    case = client.post(url, json=body, headers=hdr(SIGNATORY, "employer.signatory", su, establishment=EST)).json()["data"]
    assert case["state"] == "EMPLOYER_ATTESTED" and case["subject_ref"] == UAN_A and case["current_role"] == "fo.da_accounts"
