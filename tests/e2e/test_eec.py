"""P2.26b: the Employees' Enrolment Campaign, 2026 (PIB 2300475) — an employee left out since 2023 is registered (face-
authenticated UAN, mocked), declared, the past dues paid on one challan, and the member's account credited. Repeatable: a new
employee each run. After 31 October 2026 the campaign is closed and the declaration is refused."""
import secrets
import uuid

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

URL = "/api/v1/employers/me/eec-declarations"


def test_a_left_out_employee_enrolled_and_the_past_dues_credited(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    operator = persona("emp-preparer", "/employer/members")
    sig = persona("emp-signatory", "/employer/returns")
    tag = secrets.token_hex(3).upper()
    status, r = call(operator, "POST", "/api/v1/employers/me/members", {
        "name": f"Left Out {tag} Demo", "date_of_birth": "1994-05-05", "gender": "FEMALE",
        "aadhaar": f"{secrets.choice('23456789')}{secrets.randbelow(10**10):010d}7", "mobile": "9876500001", "date_of_joining": "2024-01-08"})
    assert status == 201, r
    uan = r["data"]["uan"]
    data = wait_for(lambda: (lambda d: d if any(c["uan"] == uan for c in d["candidates"]) or not d["open"] else None)(
        call(sig, "GET", URL)[1]["data"]), timeout=30)
    body = {"uan": uan, "monthly_wages_paise": 1400000, "employee_share_deducted": False, "declaration": True}
    if not data["open"]:
        status, r = call(sig, "POST", URL, body)
        assert status == 422 and r["type"] == "/problems/campaign-closed", r
        return
    status, preview = call(sig, "GET", f"{URL}/dues?uan={uan}&monthly_wages_paise=1400000&employee_share_deducted=false")
    assert status == 200 and preview["data"]["from_month"] == "2024-01" and len(preview["data"]["months"]) == 27, preview
    t = preview["data"]["totals_paise"]
    assert t["AC01_EPF_EE"] == 0 and t["DAMAGES_14B"] == 10000                       # the employee's share waived; ₹100 damages
    status, r = call(sig, "POST", URL, body, {"X-Step-Up-Token": step_up(sig, "declare-eec", uan, None, t["TOTAL"])})
    assert status == 201, r
    trrn = r["data"]["trrn"]
    wait_for(lambda: call(sig, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(sig, "pay-challan", trrn, None, t["TOTAL"]), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
             timeout=20, every=1)
    wait_for(lambda: any(d["uan"] == uan and d["state"] == "PAID" for d in call(sig, "GET", URL)[1]["data"]["declarations"]), timeout=40)
    assert not any(c["uan"] == uan for c in call(sig, "GET", URL)[1]["data"]["candidates"])
    ledger = call(operator, "GET", f"/api/v1/employers/me/members/{uan}/contribution-ledger")[1]["data"]
    [past] = [m for m in ledger["months"] if "EEC, 2026" in m["wage_month"]]
    assert (past["employee_paise"], past["employer_paise"], past["trrn"]) == (0, t["AC01_EPF_ER"], trrn), ledger
