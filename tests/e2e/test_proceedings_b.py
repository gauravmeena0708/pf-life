"""Phase 2, slice 11b on the running stack (Compliance Manual): a late payment's auto-calculated 14B / 7Q demands go to a
damages proceeding — the DA's notice, the SS, the circle officer, the hearing, the 14B order (reduced, with reasons) and
the 7Q order replacing them; a 7A order is reviewed on the employer's application after the RPFC-II's view, heard again
and replaced; the RPFC-II scrutinises it. Repeatable: each run makes its own late payment and its own inquiry."""
import time
from datetime import UTC, datetime, timedelta

from tests.e2e.test_compliance import pay_a_return_late
from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST, BASE = "EST-DEMO-0001", "/api/v1/office/compliance"
DUES = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
         "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]


def ok(result, status=(200, 201)):
    assert result[0] in status, result
    return result[1]["data"]


def heard(apfc, case):
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/notices", {"hearing_at": (datetime.now(UTC) + timedelta(seconds=2)).isoformat(),
                                                           "scope": "As in the notice", "period": "As in the notice"},
            {"X-Step-Up-Token": step_up(apfc, "issue-summons", case)}))
    time.sleep(3)
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/hearings", {"held_at": datetime.now(UTC).isoformat(), "employer_present": True, "eo_present": True,
                                                            "proceedings": "Heard the employer; reserved for orders", "concluded": True}))


def test_damages_and_interest_proceeding_replaces_the_auto_demands(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    sig = persona("emp-signatory", "/employer/returns")
    pay_a_return_late(persona, sig)
    da, ss, apfc = persona("ro-da-compliance", "/office/inquiries"), persona("ro-ss", "/office/inquiries"), persona("ro-apfc", "/office/inquiries")
    body = {"establishment_id": EST, "kind": "INQUIRY_14B", "contributory_uans": 40, "note": "Periodic desk review: delayed remittances"}
    draft = wait_for(lambda: (lambda r: r[1]["data"] if r[0] == 201 else None)(call(da, "POST", f"{BASE}/cases", body)), timeout=40, every=2)
    case = draft["case_id"]
    ok(call(ss, "POST", f"{BASE}/cases/{case}/approvals", {"note": "Endorsed"}))
    filed = ok(call(apfc, "POST", f"{BASE}/cases/{case}/approvals", {"note": "Approved"}))
    assert filed["state"] == "REGISTERED" and filed["diary_no"].startswith("EPR/") and filed["officer_rank"] == "APFC"
    heard(apfc, case)
    detail = ok(call(apfc, "GET", f"{BASE}/cases/{case}"))["inquiry"]
    noticed = next(a for a in detail["actions"] if a["kind"] == "NOTICE_DRAFT")["detail"]["demands"]
    for kind, code, factor in (("14B", "DAMAGES_14B", 0.5), ("7Q", "INTEREST_7Q", 1)):
        levies = [{"demand_id": d["demand_id"], "amount_paise": int(d["amount_paise"] * factor) // 100 * 100 if factor < 1 else d["amount_paise"]}
                  for d in noticed if d["kind"] == code]                     # a reduced levy in whole rupees
        if not levies:
            continue
        total = sum(x["amount_paise"] for x in levies)
        order = ok(call(apfc, "POST", f"{BASE}/cases/{case}/orders", {"kind": kind, "levies": levies, "ex_parte": False,
                                                                      "reasoning": "Delay owing to a bank strike, proved" if kind == "14B" else "Statutory interest"},
                        {"X-Step-Up-Token": step_up(apfc, "pass-order", case, None, total)}))
        assert order["demand_id"] == f"D{kind}-{case}" and order["total_paise"] == total

    def replaced():
        items = ok(call(sig, "GET", "/api/v1/employers/me/demands"))["items"]
        by = {d["demand_id"]: d for d in items}
        return by if f"D14B-{case}" in by and all(by[d["demand_id"]]["state"] != "OPEN" for d in noticed if d["demand_id"] in by) else None
    by = wait_for(replaced, timeout=30, every=1)
    assert by[f"D14B-{case}"]["state"] == "OPEN"


def test_review_after_the_next_higher_view_and_scrutiny(persona):
    ss, apfc, owner = persona("ro-ss", "/office/inquiries"), persona("ro-apfc", "/office/inquiries"), persona("emp-owner", "/employer/proceedings")
    case = ok(call(ss, "POST", f"{BASE}/cases", {"establishment_id": EST, "kind": "INQUIRY_7A", "dispute": "DUES", "period_from": "2025-04",
                                                 "period_to": "2025-09", "contributory_uans": 40, "note": "Workers' complaint with payslips",
                                                 "oic_approval": "OIC approved on e-office file (synthetic)"}))["case_id"]
    heard(apfc, case)
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/orders", {"kind": "7A", "dues": DUES, "reasoning": "Muster roll", "ex_parte": False},
            {"X-Step-Up-Token": step_up(apfc, "pass-order", case, None, 4500000)}))
    app = ok(call(owner, "POST", f"/api/v1/employers/me/proceedings/{case}/applications",
                  {"kind": "REVIEW_7B", "grounds": "NEW_EVIDENCE", "text": "The wage register was found after the order", "documents": ["register.pdf"]}))
    review = {"application_id": app["application_id"], "view_by_rank": "RPFC-I", "view_note": "x", "decision": "GRANTED", "note": "New evidence"}
    assert call(apfc, "POST", f"{BASE}/cases/{case}/reviews-7b", review, {"X-Step-Up-Token": step_up(apfc, "review-order", case)})[0] == 422
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/reviews-7b", {**review, "view_by_rank": "RPFC-II", "view_note": "Fit for review"},
            {"X-Step-Up-Token": step_up(apfc, "review-order", case)}))
    heard(apfc, case)
    revised = [{**DUES[0], "ac1_employee_paise": 1080000}]
    order = ok(call(apfc, "POST", f"{BASE}/cases/{case}/orders", {"kind": "7A", "dues": revised, "reasoning": "Half were contract workers", "ex_parte": False},
                    {"X-Step-Up-Token": step_up(apfc, "pass-order", case, None, 3420000)}))
    assert order["demand_id"] == f"D7A-{case}-R1" and "under review" in order["text"]
    mine = next(p for p in ok(call(owner, "GET", "/api/v1/employers/me/proceedings")) if p["case_id"] == case)
    assert mine["order"]["detail"]["total_paise"] == 3420000 and mine["applications"][0]["detail"]["status"] == "GRANTED"

    rpfc2 = persona("ro-rpfc2", "/office/inquiries")
    month = datetime.now(UTC).strftime("%Y-%m")
    due = {d["case_id"]: d for d in ok(call(rpfc2, "GET", f"{BASE}/scrutinies?month={month}"))}
    assert case in due and due[case]["scrutiny_due"].endswith("-15")
    assert call(apfc, "POST", f"{BASE}/cases/{case}/scrutinies", {"observations": "x"})[0] == 403
    ok(call(rpfc2, "POST", f"{BASE}/cases/{case}/scrutinies", {"observations": "Reasons recorded; review within its scope"}))
