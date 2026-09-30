"""Registering new joinees (new UAN or a new member ID under an existing UAN), Form 11, member KYC through the
mock verifiers and the employer's approval, bulk uploads, missing details, export, UAN card and readiness."""
import time
import uuid

import jwt

from tests.conftest import KEY, KID
from tests.test_member_api import SEED, api  # noqa: F401  (api is a fixture)
from tests.test_member_processes import outbox

EST = SEED["establishment"]["establishment_id"]
S = SEED["keycloak_subjects"]
MEMBER_B = S["member-b"]


def hdr(subject, stakeholder, grants=(), step_up=None, establishment=EST):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "member-service", "sub": subject, "stakeholder": stakeholder, "iat": now, "exp": now + 60,
              "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()), "grants": list(grants)}
    if establishment:
        claims["establishment_id"] = establishment
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def operator():
    return hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"])


def signatory(step=None):
    return hdr(S["emp-signatory"], "employer.signatory", ["ecr.approve"], step)


JOINEE = {"name": "Kiran Demo", "date_of_birth": "1998-03-04", "gender": "FEMALE", "aadhaar": "234512349876",
          "mobile": "9876500001", "date_of_joining": "2026-09-01"}


def test_new_joinee_gets_a_uan_and_form11_and_appears_in_the_export(api):
    r = api.post("/api/v1/employers/me/members", json=JOINEE, headers=operator())
    assert r.status_code == 201, r.json()
    new = r.json()["data"]
    assert new["new_uan"] is True and new["uan"] == "100000000008" and new["account_link_id"] == "AL-0010"
    [event] = outbox("MemberRegistered.v1")
    assert event["establishment_id"] == EST and event["member_subject"] is None
    assert api.post("/api/v1/employers/me/members", json=JOINEE, headers=operator()).json()["type"] == "/problems/possible-duplicate"
    assert "not verified" in api.post("/api/v1/employers/me/members", json={**JOINEE, "name": "X Demo", "aadhaar": "234512340000"},
                                      headers=operator()).json()["detail"]
    assert api.post("/api/v1/employers/me/members", json=JOINEE, headers=hdr(S["member-a"], "member", establishment=None)).status_code == 403
    f11 = {"previous_pf_member": False, "previous_eps_member": False, "international_worker": False, "declared_on": "2026-09-01"}
    assert api.post(f"/api/v1/employers/me/members/{new['uan']}/declarations", json=f11, headers=operator()).status_code == 200
    export = api.get("/api/v1/employers/me/members/active-export", headers=operator()).json()["data"]["members"]
    row = next(m for m in export if m["uan"] == new["uan"])
    assert row["form11"] == "FILED" and row["pan"] == "NOT_SEEDED" and "father_name" in row["missing_details"]
    step = {"action": "update-member-profile", "resource_id": new["uan"]}
    filled = api.patch(f"/api/v1/employers/me/members/{new['uan']}/profile", json={"father_name": "Suresh Demo"},
                       headers=hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"], step))
    assert filled.status_code == 200 and filled.json()["data"]["profile_extra"]["father_name"] == "SURESH DEMO"
    again = api.patch(f"/api/v1/employers/me/members/{new['uan']}/profile", json={"father_name": "Other"},
                      headers=hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"], step))
    assert again.status_code == 409 and "Joint Declaration" in again.json()["detail"]


def test_existing_uan_gets_a_new_member_id_only_when_the_person_matches(api):
    b = SEED["members"][1]
    body = {**JOINEE, "name": b["name"], "date_of_birth": b["date_of_birth"], "existing_uan": b["uan"]}
    assert api.post("/api/v1/employers/me/members", json=body, headers=operator()).json()["type"] == "/problems/already-employed"
    other = hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"], establishment="EST-DEMO-0002")
    r = api.post("/api/v1/employers/me/members", json=body, headers=other)
    assert r.status_code == 201 and r.json()["data"]["uan"] == b["uan"] and r.json()["data"]["new_uan"] is False
    wrong = api.post("/api/v1/employers/me/members", json={**body, "date_of_birth": "1990-01-01"}, headers=other)
    assert wrong.json()["type"] == "/problems/uan-mismatch"


def test_member_pan_is_verified_then_approved_by_the_employer(api):
    step = {"action": "seed-kyc", "resource_id": SEED["members"][1]["member_id"]}
    member = hdr(MEMBER_B, "member", step_up=step, establishment=None)
    bad = api.post("/api/v1/members/me/kyc/PAN", json={"number": "ABCPD1234Z"}, headers=member).json()["data"]
    assert bad["state"] == "FAILED_VERIFICATION" and "does not match" in bad["verification"]["reason"]
    assert api.post("/api/v1/members/me/kyc/PAN", json={"number": "ABCPD1234E"}, headers=hdr(MEMBER_B, "member", establishment=None)).status_code == 428
    r = api.post("/api/v1/members/me/kyc/PAN", json={"number": "ABCPD1234E"}, headers=member)
    assert r.status_code == 201 and r.json()["data"]["state"] == "PENDING_EMPLOYER" and r.json()["data"]["masked_value"] == "******234E"
    assert api.post("/api/v1/members/me/kyc/PAN", json={"number": "ABCPD1234E"}, headers=member).json()["type"] == "/problems/kyc-pending"
    queue = api.get("/api/v1/employers/me/kyc-approvals", headers=signatory()).json()["data"]
    [req] = [q for q in queue if q["uan"] == SEED["members"][1]["uan"]]
    url = f"/api/v1/employers/me/kyc-approvals/{req['request_id']}/decisions"
    assert api.post(url, json={"decision": "APPROVE", "note": "PAN copy on file"}, headers=signatory()).status_code == 428
    done = api.post(url, json={"decision": "APPROVE", "note": "PAN copy on file"}, headers=signatory({"action": "approve-kyc", "resource_id": req["request_id"]}))
    assert done.status_code == 200 and done.json()["data"]["state"] == "APPROVED"
    kyc = api.get("/api/v1/members/me/kyc", headers=hdr(MEMBER_B, "member", establishment=None)).json()["data"]
    assert kyc["pan"] == "VERIFIED" and kyc["pan_masked"] == "******234E"
    [event] = outbox("MemberKycUpdated.v1")
    assert event["pan_verified"] is True and event["uan"] == SEED["members"][1]["uan"]
    status = api.get("/api/v1/members/me/account-status", headers=hdr(MEMBER_B, "member", establishment=None)).json()["data"]
    codes = {b["code"] for b in status["accounts"][0]["blockers"]}
    assert "KYC_PAN_MISSING" not in codes and "EXIT_NOT_MARKED" in codes and status["accounts"][0]["ready_for"] == ["ADVANCE"]
    card = api.get("/api/v1/members/me/uan-card", headers=hdr(MEMBER_B, "member", establishment=None)).json()["data"]
    assert card["uan"] == SEED["members"][1]["uan"] and card["kyc"]["pan"] == "VERIFIED"


def test_bank_change_and_bulk_kyc_with_errors(api):
    step = {"action": "seed-kyc", "resource_id": SEED["members"][0]["member_id"]}
    r = api.post("/api/v1/members/me/kyc/bank-accounts", json={"ifsc": "DEMO0000011", "account_number": "11112222333"},
                 headers=hdr(S["member-a"], "member", step_up=step, establishment=None)).json()["data"]
    done = api.post(f"/api/v1/employers/me/kyc-approvals/{r['request_id']}/decisions", json={"decision": "APPROVE", "note": "Cancelled cheque seen"},
                    headers=signatory({"action": "approve-kyc", "resource_id": r["request_id"]}))
    assert done.status_code == 200
    me = api.get("/api/v1/members/me", headers=hdr(S["member-a"], "member", establishment=None)).json()["data"]
    assert me["bank"] == {"ifsc": "DEMO0000011", "account_last4": "2333"}
    content = "uan,type,number,ifsc\n100000000003,PAN,ABCPC1234D\n100000000004,BANK,5555666677770000,DEMO0000004\n999999999999,PAN,ABCPE1234F\n"
    up = api.post("/api/v1/employers/me/kyc-bulk-uploads", json={"content": content}, headers=operator()).json()["data"]
    assert (up["lines"], up["accepted"], up["errors"]) == (3, 1, 2)
    errs = api.get(f"/api/v1/employers/me/kyc-bulk-uploads/{up['upload_id']}/errors", headers=operator()).json()["data"]["errors"]
    assert {e["line"] for e in errs} == {3, 4}
    pending = api.get("/api/v1/employers/me/kyc-approvals?source=EMPLOYER_BULK", headers=signatory()).json()["data"]
    assert [p["uan"] for p in pending] == ["100000000003"]


def test_bulk_registration_reports_each_line(api):
    content = ("name,dob,gender,aadhaar,mobile,doj\nRavi Demo,1995-05-05,MALE,345612349876,9876500002,2026-09-02\n"
               "Bad Line,1995-05-05,MALE,12,9876500003,2026-09-02\nSita Demo,2020-01-01,FEMALE,456712349876,9876500004,2026-09-02\n")
    r = api.post("/api/v1/employers/me/members/bulk-registrations", json={"content": content}, headers=operator()).json()["data"]
    assert r["lines"] == 3 and r["registered"] == 1
    assert [x["status"] for x in r["results"]] == ["REGISTERED", "ERROR", "ERROR"]
    assert "14 years" in r["results"][2]["error"]


def test_member_360_needs_a_purpose_and_the_officers_office(api):
    da = hdr(S["do-caseworker"], "fo.da_accounts", establishment=None)
    assert api.get("/api/v1/office/members/100000000002", headers=da).status_code == 400                 # purpose required
    r = api.get("/api/v1/office/members/100000000002?purpose=Freeze%20verification%20of%20the%20member", headers=da)
    assert r.status_code == 200 and r.json()["data"]["member_ids"][0]["office_id"] == "RO-DEMO-01"
    assert api.get("/api/v1/office/members/999999999999?purpose=Checking%20a%20complaint", headers=da).status_code == 404
    assert api.get("/api/v1/office/members/100000000002?purpose=Just%20looking%20around", headers=hdr(S["member-a"], "member", establishment=None)).status_code == 403


def test_pro_counter_matches_the_filer_with_the_member_record(api):
    pro = hdr(S["ro-pro-counter"], "fo.pro_intake", establishment=None)
    url = "/api/v1/office/physical-claims/INW-0001/identity-validations"
    body = {"uan": "100000000002", "name": "Bharat  demo", "date_of_birth": "1985-11-02", "evidence": "AADHAAR_OTP"}
    ok = api.post(url, json=body, headers=pro)
    assert ok.status_code == 201 and ok.json()["data"]["result"] == "MATCHED" and ok.json()["data"]["kyc_snapshot"]["aadhaar"] == "VERIFIED"
    assert api.post(url, json={**body, "date_of_birth": "1985-11-03"}, headers=pro).json()["data"]["result"] == "MISMATCH"
    assert api.post(url, json={**body, "uan": "999999999999"}, headers=pro).status_code == 404
    assert api.post(url, json=body, headers=hdr(S["member-a"], "member", establishment=None)).status_code == 403


def test_form11_international_worker_declaration_changes_the_member_status(api):
    """P2.9a: an international worker is a member; the employer's Form 11 declaration sets or clears the status."""
    uan, url = "100000000001", "/api/v1/employers/me/members/100000000001/declarations"
    f11 = {"previous_pf_member": True, "previous_eps_member": True, "international_worker": True, "declared_on": "2026-09-01"}
    assert api.post(url, json=f11, headers=operator()).status_code == 422             # country of origin is required
    assert api.post(url, json={**f11, "country_of_origin": "Germany"}, headers=operator()).status_code == 200
    changed = [e for e in outbox("MemberInternationalStatusChanged.v1") if e["uan"] == uan]
    assert changed[-1] == {"uan": uan, "international_worker": True, "nationality": "Germany"}
    me = api.get("/api/v1/members/me", headers=hdr(S["member-a"], "member", establishment=None)).json()["data"]
    assert me["international_worker"] is True and me["nationality"] == "Germany"
    assert api.post(url, json={**f11, "country_of_origin": "Germany"}, headers=operator()).status_code == 200
    assert len([e for e in outbox("MemberInternationalStatusChanged.v1") if e["uan"] == uan]) == len(changed)   # unchanged: no event
    assert api.post(url, json={**f11, "international_worker": False}, headers=operator()).status_code == 200
    assert [e for e in outbox("MemberInternationalStatusChanged.v1") if e["uan"] == uan][-1]["nationality"] is None
