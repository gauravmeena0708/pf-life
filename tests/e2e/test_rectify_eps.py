"""P2.19c on the running stack — HO circular WSU/2025/E-961539 (19 Dec 2025), scenario I: a joinee of 2016 on ₹40,000 (not
eligible for EPS since 1 Sep 2014, G.S.R. 609(E)) is wrongly given EPS on a return; the DA (Accounts) works out the
rectification from the posted return, the APFC approves it, the EPS with interest goes back to the member's PF, the
pension service is deleted, and the next return refuses pension wages for the member ID. Repeatable: a new joinee and a
random month of 2020-2023 each run."""
import random
import secrets
import uuid

from tests.e2e.officers import call, step_up, wait_for
from tests.e2e.test_journey_a_ecr import SEED, ecr_line, ensure_verified_and_granted
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

URL = "/api/v1/office/eps-rectifications"


def file_and_pay(preparer, signatory, month, content):
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings", {"wage_month": month, "format": "ECR_TXT", "content": content})
    assert status == 201 and created["data"]["filing"]["state"] == "VALIDATED", created
    f, total = created["data"]["filing"], created["data"]["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    assert call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", {"decision": "APPROVE"},
                {"X-Step-Up-Token": step_up(signatory, "approve-ecr", f["filing_id"], f["version"], total)})[0] == 200
    status, sub = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions", None,
                       {"X-Step-Up-Token": step_up(signatory, "submit-ecr", f["filing_id"], f["version"], total),
                        "Idempotency-Key": str(uuid.uuid4()), "If-Match": str(f["version"])})
    assert status == 201, sub
    trrn = sub["data"]["trrn"]
    wait_for(lambda: call(signatory, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(signatory, "pay-challan", trrn, None, total), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
             timeout=20, every=1)
    wait_for(lambda: call(signatory, "GET", f"/api/v1/employers/me/challans/{trrn}")[1]["data"]["status"] == "PAID", timeout=30)


def test_eps_wrongly_allowed_is_rectified(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    preparer = persona("emp-preparer", "/employer/members")
    signatory = persona("emp-signatory", "/employer/ecr")
    tag = secrets.token_hex(3).upper()
    name = f"Rectify {tag} Demo"
    status, r = call(preparer, "POST", "/api/v1/employers/me/members", {
        "name": name, "date_of_birth": "1990-03-03", "gender": "MALE", "date_of_joining": "2016-01-04",
        "aadhaar": f"{secrets.choice('23456789')}{secrets.randbelow(10**10):010d}3", "mobile": "9876500002"})
    assert status == 201, r
    uan, link = r["data"]["uan"], r["data"]["account_link_id"]
    # 2020-2023: months no other test files (Journey A takes 2001-2019); member A is on the return too, as on any regular return
    month = f"{random.randint(2020, 2023)}-{random.randint(1, 12):02d}"
    a = SEED["members"][0]
    wait_for(lambda: call(preparer, "GET", f"/api/v1/employers/me/members/{uan}/contribution-ledger")[0] == 200, timeout=30)
    file_and_pay(preparer, signatory, month, "\n".join([ecr_line(a["uan"], a["name"], 15000),
                                                       ecr_line(uan, name.upper(), 40000)]))     # the joinee: EPS on ₹15,000 — wrongly

    da = persona("do-caseworker", "/office/ledger")
    body = {"account_link_id": link, "scenario": "WRONGLY_ALLOWED", "from_month": month, "to_month": month, "notesheet_no": f"NS/EPS/{tag}",
            "remarks": "Joined on 4 Jan 2016 on ₹40,000: not eligible for EPS (G.S.R. 609(E))."}

    def proposed():
        status, r = call(da, "POST", URL, body, {"X-Step-Up-Token": step_up(da, "propose-eps-rectification", link, None, None)})
        return r if status == 201 else None
    case = wait_for(proposed, timeout=30, every=2)["data"]                   # once the return is posted
    assert case["worksheet"]["amount_paise"] == 125000 and case["total_paise"] > 125000, case

    apfc = persona("ro-apfc", "/office/ledger")
    rid = case["rectification_id"]
    status, r = call(apfc, "POST", f"{URL}/{rid}/approvals", {"decision": "APPROVE", "note": "Form 11 shows ₹40,000 on joining"},
                     {"X-Step-Up-Token": step_up(apfc, "approve-eps-rectification", rid, None, case["total_paise"])})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    ledger = call(preparer, "GET", f"/api/v1/employers/me/members/{uan}/contribution-ledger")[1]["data"]
    assert ledger, ledger

    nxt = f"{int(month[:4]) + (month[5:] == '12')}-{int(month[5:]) % 12 + 1:02d}"
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings", {"wage_month": nxt, "format": "ECR_TXT",
                                                                                  "content": "\n".join([ecr_line(a["uan"], a["name"], 15000), ecr_line(uan, name.upper(), 40000)])})
    assert status == 201 and any(i["code"] == "E-EPS-NOT-ELIGIBLE" for i in created["data"]["validation_report"]["issues"]), created
