"""Phase 2, slice 11a on the running stack (Compliance Manual, ch. 2): the circle officer schedules an inspection; the
Enforcement Officer reports 12 workers not enrolled; DA, SS and the circle officer put it through the file; the SS
registers the inquiry (diary number; by size it goes to an APFC); the officer issues summons, holds hearings with daily
orders while the employer replies, and passes the 7A order; the dues reach the employer as a demand. Repeatable: each
run is a new inspection and inquiry."""
import time
from datetime import UTC, datetime, timedelta

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona, wait_for  # noqa: F401  (fixtures)

EST, BASE = "EST-DEMO-0001", "/api/v1/office/compliance"


def ok(result, status=(200, 201)):
    assert result[0] in status, result
    return result[1]["data"]


def test_inspection_to_7a_order_and_the_demand(persona):
    apfc, eo, da, ss = (persona(p, "/office/inquiries") for p in ("ro-apfc", "ro-eo", "ro-da-compliance", "ro-ss"))
    iid = ok(call(apfc, "POST", f"{BASE}/inspections", {"establishment_id": EST, "purpose": "COMPLAINT", "period_from": "2025-04",
                                                         "period_to": "2025-09", "note": "Workers' complaint (synthetic)"}))["inspection_id"]
    ok(call(eo, "POST", f"{BASE}/inspections/{iid}/reports", {
        "visited_on": datetime.now(UTC).date().isoformat(), "employees_found": 40, "employees_not_enrolled": 12, "wages_paise_monthly": 1500000,
        "findings": "12 workers on the muster roll are not enrolled", "dues_estimate_paise": 5000000, "recommendation": "INITIATE_7A_DUES"}))
    ok(call(da, "POST", f"{BASE}/inspections/{iid}/processing-notes", {"note": "Report examined; facts verified"}))
    ok(call(ss, "POST", f"{BASE}/inspections/{iid}/processing-notes", {"note": "Put up for orders"}))
    decided = ok(call(apfc, "POST", f"{BASE}/inspections/{iid}/processing-notes", {"note": "Fit case", "decision": "INITIATE_7A"}))
    assert decided["state"] == "DECIDED_INITIATE" and [s["stage"] for s in decided["steps"]] == ["REPORT", "DA_NOTE", "SS_NOTE", "DECISION"]

    inquiry = ok(call(ss, "POST", f"{BASE}/cases", {"establishment_id": EST, "kind": "INQUIRY_7A", "dispute": "DUES", "period_from": "2025-04",
                                                    "period_to": "2025-09", "inspection_id": iid, "contributory_uans": 40, "note": "From the report"}))
    case, diary = inquiry["case_id"], inquiry["diary_no"]
    assert diary.startswith("EPR/RO-DEMO-01/") and inquiry["officer_rank"] == "APFC"           # 40 contributory UANs: an APFC

    hearing_at = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/notices", {"hearing_at": hearing_at, "scope": "Dues of 12 workers", "period": "Apr-Sep 2025"},
            {"X-Step-Up-Token": step_up(apfc, "issue-summons", case)}))
    time.sleep(3)
    held = datetime.now(UTC)
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/hearings", {"held_at": held.isoformat(), "employer_present": True, "eo_present": True,
                                                            "proceedings": "Employer asks for time to file wage records",
                                                            "next_hearing_at": (held + timedelta(days=7)).isoformat()}))
    owner = persona("emp-owner", "/employer/proceedings")
    mine = next(p for p in ok(call(owner, "GET", "/api/v1/employers/me/proceedings")) if p["case_id"] == case)
    assert mine["diary_no"] == diary and mine["summons"][0]["detail"]["meeting_link"]
    ok(call(owner, "POST", f"/api/v1/employers/me/proceedings/{case}/submissions",
            {"kind": "REPLY", "text": "The 12 are contract workers of a contractor", "documents": ["contract.pdf"]}))
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/hearings", {"held_at": datetime.now(UTC).isoformat(), "employer_present": True, "eo_present": True,
                                                            "proceedings": "Arguments heard; reserved for orders", "concluded": True}))

    dues = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
             "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]
    order = ok(call(apfc, "POST", f"{BASE}/cases/{case}/orders", {"kind": "7A", "dues": dues, "ex_parte": False,
                                                                  "reasoning": "The contractor is not registered; the principal employer is liable"},
                    {"X-Step-Up-Token": step_up(apfc, "pass-order", case, None, 4500000)}))
    assert order["total_paise"] == 4500000 and "₹45,000" in order["text"] and diary in order["text"]

    def demand():
        rows = ok(call(owner, "GET", "/api/v1/employers/me/demands"))["items"]
        return next((d for d in rows if d["demand_id"] == order["demand_id"]), None)
    raised = wait_for(demand, timeout=30, every=1)
    assert raised["amount_paise"] == 4500000 and raised["kind"] == "DUES_7A", raised
    assert call(persona("member-a", "/member"), "GET", f"{BASE}/inspections")[0] == 403
