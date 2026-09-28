"""Phase 2, slice 2 on the running stack: an employer registers a joinee (mock Aadhaar) and files Form 11; the
joinee reaches the ECR member list and the ledger; a member's KYC is verified by a mock verifier and approved by
the employer's authorised signatory (one-time code for DSC / e-sign); a bulk KYC upload reports its errors.
Each run registers a fresh synthetic joinee, so it can be repeated."""
import secrets
from datetime import UTC, datetime

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_employer_registers_a_joinee_and_approves_member_kyc(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))     # a fresh stack: operator and signatory grants first
    operator = persona("emp-preparer", "/employer/registration")
    tag = secrets.token_hex(3).upper()
    aadhaar = f"{secrets.choice('23456789')}{secrets.randbelow(10**10):010d}9"
    today = datetime.now(UTC).date().isoformat()
    status, r = call(operator, "POST", "/api/v1/employers/me/members", {
        "name": f"Joinee {tag} Demo", "date_of_birth": "1997-06-15", "gender": "FEMALE", "aadhaar": aadhaar,
        "mobile": "9876543210", "date_of_joining": today})
    assert status == 201 and r["data"]["new_uan"] is True, r
    uan = r["data"]["uan"]
    status, r = call(operator, "POST", f"/api/v1/employers/me/members/{uan}/declarations", {
        "previous_pf_member": False, "previous_eps_member": False, "international_worker": False, "declared_on": today})
    assert status == 200, r
    wait_for(lambda: any(m["uan"] == uan for m in call(operator, "GET", "/api/v1/employers/me/members")[1]["data"]), timeout=20)
    wait_for(lambda: call(operator, "GET", f"/api/v1/employers/me/members/{uan}/contribution-ledger")[0] == 200, timeout=30)
    export = call(operator, "GET", "/api/v1/employers/me/members/active-export")[1]["data"]["members"]
    assert next(m for m in export if m["uan"] == uan)["form11"] == "FILED"
    status, up = call(operator, "POST", "/api/v1/employers/me/kyc-bulk-uploads", {"content": f"{uan},PAN,ABCDE1234F\n999999999999,PAN,ABCPE1234F\n"})
    assert status == 201 and up["data"]["errors"] == 2, up                 # a company PAN (4th letter not P); not an employee
    SHOTS.mkdir(exist_ok=True)
    operator.goto(f"{WEB}/employer/registration")
    operator.get_by_role("heading", name="Active members").wait_for()
    operator.screenshot(path=str(SHOTS / "p2-registration.png"), full_page=True)

    member = persona("member-d", "/member/kyc")
    me = call(member, "GET", "/api/v1/members/me")[1]["data"]
    account = f"{secrets.randbelow(10**11):011d}7"
    status, r = call(member, "POST", "/api/v1/members/me/kyc/bank-accounts", {"ifsc": "DEMO0000007", "account_number": account},
                     {"X-Step-Up-Token": step_up(member, "seed-kyc", me["member_id"])})
    assert status == 201 and r["data"]["state"] == "PENDING_EMPLOYER", r
    request_id = r["data"]["request_id"]
    signatory = persona("emp-signatory", "/employer/registration")
    wait_for(lambda: request_id in [k["request_id"] for k in call(signatory, "GET", "/api/v1/employers/me/kyc-approvals")[1]["data"]])
    signatory.goto(f"{WEB}/employer/registration")
    signatory.get_by_role("heading", name="KYC awaiting your approval").wait_for()
    signatory.screenshot(path=str(SHOTS / "p2-kyc-approvals.png"), full_page=True)
    status, r = call(signatory, "POST", f"/api/v1/employers/me/kyc-approvals/{request_id}/decisions",
                     {"decision": "APPROVE", "note": "Cancelled cheque checked"},
                     {"X-Step-Up-Token": step_up(signatory, "approve-kyc", request_id)})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    assert call(member, "GET", "/api/v1/members/me")[1]["data"]["bank"]["account_last4"] == account[-4:]
    readiness = call(member, "GET", "/api/v1/members/me/account-status")[1]["data"]
    assert {a["account_link_id"] for a in readiness["accounts"]} >= {"AL-0008", "AL-0009"}
    card = call(member, "GET", "/api/v1/members/me/uan-card")[1]["data"]
    assert card["uan"] == "100000000007"
    notices = wait_for(lambda: [n for n in call(member, "GET", "/api/v1/members/me/notifications")[1]["data"] if n["reference_id"] == request_id])
    assert notices[0]["template"] == "KYC_APPROVED"
    member.goto(f"{WEB}/member/kyc")
    member.get_by_role("heading", name="Ready to claim?").wait_for()
    member.screenshot(path=str(SHOTS / "p2-member-kyc.png"), full_page=True)
