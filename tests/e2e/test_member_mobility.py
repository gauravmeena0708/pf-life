"""Phase 2, slice 8b on the running stack: e-Nomination and Know your UAN; a claim from a member without a verified
Aadhaar waits for the employer's attestation; a claim switched to another verified bank account before payment;
auto-transfer on a change of job; the employer corrects a date of exit, uploads exits in bulk and files a Joint
Declaration itself. Each run registers a fresh joinee for the employer steps, so it can be repeated."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from tests.e2e.test_journey_a_ecr import SEED, call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def member_seed(uan):
    return next(m for m in SEED["members"] if m["uan"] == uan)


def test_e_nomination_and_know_your_uan(persona):
    a = persona("member-a", "/member/nomination")
    me = call(a, "GET", "/api/v1/members/me/nominations")[1]["data"]
    assert me["aadhaar_verified"] is True
    body = {"has_family": True, "nominees": [
        {"name": "Meena Demo", "relation": "SPOUSE", "date_of_birth": "1986-01-01", "share_bp": 6000},
        {"name": "Ravi Demo", "relation": "SON", "date_of_birth": "2015-05-05", "share_bp": 4000, "guardian_name": "Meena Demo"}]}
    bad = call(a, "POST", "/api/v1/members/me/nominations", {**body, "nominees": [{**body["nominees"][0], "relation": "OTHER"},
                                                                                  body["nominees"][1]]},
               {"X-Step-Up-Token": step_up(a, "e-nominate", me["uan"])})
    assert bad[0] == 422 and "family members" in bad[1]["detail"], bad
    status, r = call(a, "POST", "/api/v1/members/me/nominations", body,
                     {"X-Step-Up-Token": step_up(a, "e-nominate", me["uan"])})
    assert status == 201 and r["data"]["state"] == "CURRENT", r
    assert [n["minor"] for n in r["data"]["nominees"]] == [False, True]
    f = persona("member-f", "/member/nomination")
    refused = call(f, "POST", "/api/v1/members/me/nominations", body, {"X-Step-Up-Token": step_up(f, "e-nominate", "100000000904")})
    assert refused[0] == 422 and "verified Aadhaar" in refused[1]["detail"], refused

    seed = member_seed("100000000001")
    status, found = call(a, "POST", "/api/v1/members/uan-lookups", {"name": seed["name"].lower(), "date_of_birth": seed["date_of_birth"],
                                                                     "mobile_last4": seed["mobile_masked"][-4:], "otp": "123456"})
    assert status == 200 and [x["uan"] for x in found["data"]["found"]] == ["100000000001"], found
    assert call(a, "POST", "/api/v1/members/uan-lookups", {"name": seed["name"], "date_of_birth": seed["date_of_birth"],
                                                          "mobile_last4": "0001", "otp": "000000"})[0] == 422


def _claims(page):
    return call(page, "GET", "/api/v1/members/me/claims")[1]["data"]


def test_a_claim_without_verified_aadhaar_waits_for_the_employer(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    f = persona("member-f", "/member/claims")
    cashier = None
    for old in [c for c in _claims(f) if c["claim_type"] == "ADVANCE_ILLNESS" and c["state"] == "AUTO_APPROVED"]:
        cashier = cashier or persona("ro-cashier", "/office/work-queue")      # an earlier run's claim: pay it, so a new one can be filed
        call(cashier, "POST", f"/api/v1/office/claims/{old['claim_id']}/payment-instructions", {"demo_scenario": "SUCCESS"},
             {"X-Step-Up-Token": step_up(cashier, "instruct-payment", old["claim_id"], None, old["amount_paise"]),
              "Idempotency-Key": str(uuid.uuid4())})
        wait_for(lambda: next(c for c in _claims(f) if c["claim_id"] == old["claim_id"])["state"] == "SETTLED", timeout=30)
    sig = persona("emp-signatory", "/employer/members")

    def file_and_confirm():
        status, created = call(f, "POST", "/api/v1/members/me/claims",
                               {"account_link_id": "AL-0904", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 500000})
        assert status == 201, created
        c = created["data"]["confirmation"]
        status, r = call(f, "POST", f"/api/v1/members/me/claims/{c['resource_id']}/confirmations", None,
                         {"X-Step-Up-Token": step_up(f, c["action"], c["resource_id"], c["resource_version"], c["amount_paise"])})
        assert status == 200 and r["data"]["state"] == "PENDING_EMPLOYER_ATTESTATION", r
        return r["data"]

    def decide(claim, decision, note):
        item = next(i for i in call(sig, "GET", "/api/v1/employers/me/claim-attestations")[1]["data"] if i["claim_id"] == claim["claim_id"])
        return call(sig, "POST", f"/api/v1/employers/me/claim-attestations/{claim['claim_id']}/decisions", {"decision": decision, "note": note},
                    {"X-Step-Up-Token": step_up(sig, "attest-claim", claim["claim_id"], item["version"])})

    status, r = decide(file_and_confirm(), "REJECT", "Dates of service do not match our records")
    assert status == 200 and r["data"]["state"] == "REJECTED_BY_EMPLOYER", r
    status, r = decide(file_and_confirm(), "ATTEST", "Service and wages checked")
    assert status == 200 and r["data"]["state"] == "AUTO_APPROVED", r            # within the automatic limit once attested


def test_a_claim_is_switched_to_another_verified_account_before_payment(persona):
    a = persona("member-a", "/member/claims")
    status, created = call(a, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0001", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 20000000})
    if status == 409:                                        # an earlier journey's claim of this type is still open: use it
        claim_id, ours = created["claim_id"], False
    else:
        assert status == 201, created
        c = created["data"]["confirmation"]
        claim_id, ours = c["resource_id"], True
        status, r = call(a, "POST", f"/api/v1/members/me/claims/{claim_id}/confirmations", None,
                         {"X-Step-Up-Token": step_up(a, c["action"], claim_id, c["resource_version"], c["amount_paise"])})
        assert status == 200 and r["data"]["state"] == "UNDER_REVIEW", r
    options = call(a, "GET", f"/api/v1/members/me/claims/{claim_id}/bank-details")[1]["data"]
    if options["switchable"]:
        target = next(b for b in options["verified_accounts"] if b["bank_account_last4"] == "4321")
        claim = call(a, "GET", f"/api/v1/members/me/claims/{claim_id}")[1]["data"]
        status, r = call(a, "PUT", f"/api/v1/members/me/claims/{claim_id}/bank-details", target,
                         {"X-Step-Up-Token": step_up(a, "switch-claim-bank", claim_id, claim["version"])})
        assert status == 200 and r["data"]["payee_account_last4"] == "4321", r
    if ours:                                                  # withdraw it, so the run leaves nothing open
        status, r = call(a, "POST", f"/api/v1/members/me/claims/{claim_id}/cancellations", None,
                         {"X-Step-Up-Token": step_up(a, "cancel-claim", claim_id)})
        assert status == 200 and r["data"]["state"] == "CANCELLED", r


def test_auto_transfer_on_a_change_of_job(persona):
    g = persona("member-g", "/member/service")
    status = call(g, "GET", "/api/v1/members/me/transfers/auto")[1]["data"]
    assert status["primary_account_link_id"] == "AL-0906", status
    if status["eligible"]:                                    # the first run: AL-0905 still holds its balance
        item = status["eligible"][0]
        r = call(g, "POST", f"/api/v1/members/me/transfers/auto/{item['transfer_id']}/confirmations", None,
                 {"X-Step-Up-Token": step_up(g, "confirm-auto-transfer", item["transfer_id"], None, item["amount_paise"])})
        assert r[0] == 201, r
    posted = wait_for(lambda: next((h for h in call(g, "GET", "/api/v1/members/me/transfers/auto")[1]["data"]["history"]
                                    if h["state"] == "POSTED"), None), timeout=30)
    assert posted["from_account_link_id"] == "AL-0905" and posted["to_account_link_id"] == "AL-0906"
    history = call(g, "GET", "/api/v1/members/me/service-history")[1]["data"]
    assert "AL-0905" in str(history)


def test_employer_exit_correction_bulk_exits_and_employer_joint_declaration(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    operator = persona("emp-preparer", "/employer/members")
    sig = persona("emp-signatory", "/employer/members")
    today = datetime.now(UTC).date()

    def register():
        tag = secrets.token_hex(3).upper()
        status, r = call(operator, "POST", "/api/v1/employers/me/members", {
            "name": f"Leaver {tag} Demo", "date_of_birth": "1996-02-02", "gender": "MALE",
            "aadhaar": f"{secrets.choice('23456789')}{secrets.randbelow(10**10):010d}3", "mobile": "9876500000",
            "date_of_joining": (today - timedelta(days=20)).isoformat()})
        assert status == 201, r
        uan, link = r["data"]["uan"], r["data"]["account_link_id"]
        wait_for(lambda: call(sig, "GET", "/api/v1/employers/me/approvals")[0] == 200 and
                 call(operator, "GET", f"/api/v1/employers/me/members/{uan}/contribution-ledger")[0] == 200, timeout=30)
        return uan, link

    def approve(case_id):
        case = next(c for c in call(sig, "GET", "/api/v1/employers/me/approvals")[1]["data"] if c["case_id"] == case_id)
        return call(sig, "POST", f"/api/v1/employers/me/approvals/{case_id}/decisions", {"decision": "APPROVE", "note": "Checked"},
                    {"X-Step-Up-Token": step_up(sig, "approve-exit", case_id, case["version"])})

    uan1, link1 = register()
    uan2, link2 = register()
    content = (f"uan,account_link_id,date_of_exit,reason\n{uan1},{link1},{(today - timedelta(days=10)).isoformat()},CESSATION\n"
               f"{uan2},{link1},{today.isoformat()},CESSATION\n")          # the second line names the wrong member ID
    status, up = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(call(
        operator, "POST", "/api/v1/employers/me/members/exit-bulk-uploads", {"content": content},
        {"X-Step-Up-Token": step_up(operator, "mark-exit-bulk", EST)})), timeout=30, every=2)
    assert up["data"]["accepted"] == 1 and up["data"]["results"][1]["status"] == "ERROR", up
    status, r = approve(up["data"]["results"][0]["case_id"])
    assert status == 200 and r["data"]["state"] == "APPROVED", r

    corrected = (today - timedelta(days=5)).isoformat()
    body = {"account_link_id": link1, "date_of_exit": corrected, "reason": "CESSATION",
            "correction_note": "The last working day was later than first marked"}
    status, case = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(call(
        operator, "POST", f"/api/v1/employers/me/members/{uan1}/exit-corrections", body,
        {"X-Step-Up-Token": step_up(operator, "correct-exit-employer", uan1)})), timeout=30, every=2)
    assert case["data"]["state"] == "CORRECTION_MARKED", case
    status, r = approve(case["data"]["case_id"])
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    wait_for(lambda: any(m["uan"] == uan1 and m.get("date_of_exit") == corrected
                         for m in call(operator, "GET", "/api/v1/employers/me/members")[1]["data"]), timeout=30)

    status, jd = call(sig, "POST", "/api/v1/employers/me/joint-declarations", {
        "uan": uan2, "parameter": "FATHER_NAME", "current_value": "NOT RECORDED", "corrected_value": "SURESH DEMO",
        "reason": "Father's name missing at registration", "member_consent": "MOCK_AADHAAR_OTP"},
        {"X-Step-Up-Token": step_up(sig, "submit-joint-declaration-employer", uan2)})
    assert status == 200 and jd["data"]["state"] == "EMPLOYER_ATTESTED", jd
    da = persona("do-caseworker", "/office/work-queue")
    assert any(c["case_id"] == jd["data"]["case_id"] for c in call(da, "GET", "/api/v1/office/member-change-requests")[1]["data"])
