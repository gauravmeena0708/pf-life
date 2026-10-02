"""Phase 2, slice 11c on the running stack: a 26B membership dispute heard by the RPFC-II; an appeal against a 7A order
with the 7-O pre-deposit, remanded by the Tribunal to an officer one level higher; a prosecution for returns not filed —
show-cause, the employer's reply, the RPFC's sanction, the Enforcement Officer's complaint, the conviction on the legal
register. Repeatable: each run makes its own cases."""
from datetime import date

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)
from tests.e2e.test_proceedings_b import DUES, heard, ok

EST, BASE, LEGAL = "EST-DEMO-0001", "/api/v1/office/compliance", "/api/v1/office/legal"


def test_membership_dispute_heard_by_the_rpfc2(persona):
    ss, rpfc2 = persona("ro-ss", "/office/inquiries"), persona("ro-rpfc2", "/office/inquiries")
    case = ok(call(ss, "POST", f"{BASE}/membership-disputes", {"establishment_id": EST, "trigger": "EMPLOYEE_COMPLAINT", "contributory_uans": 40,
              "note": "Two 'apprentices' say they are regular workers", "employees": [{"name": "SYNTH WORKER A", "claimed_from": "2025-01-01"},
              {"name": "SYNTH WORKER B", "claimed_from": "2025-03-01"}]}, {"X-Step-Up-Token": step_up(ss, "register-26b", EST)}))
    assert case["section"] == "26B" and case["officer_rank"] == "RPFC-II"
    heard(rpfc2, case["case_id"])
    order = ok(call(rpfc2, "POST", f"{BASE}/cases/{case['case_id']}/orders", {"kind": "26B", "reasoning": "A works on the shop floor; B is a genuine apprentice",
               "ex_parte": False, "decisions": [{"name": "SYNTH WORKER A", "eligible": True, "from_date": "2025-01-01"},
                                                {"name": "SYNTH WORKER B", "eligible": False}]},
               {"X-Step-Up-Token": step_up(rpfc2, "pass-order", case["case_id"], None, 0)}))
    assert "PARA 26B" in order["text"] and order["total_paise"] == 0


def test_appeal_with_pre_deposit_remanded_one_level_higher(persona):
    ss, apfc, legal = persona("ro-ss", "/office/inquiries"), persona("ro-apfc", "/office/inquiries"), persona("ro-legal", "/office/legal")
    case = ok(call(ss, "POST", f"{BASE}/cases", {"establishment_id": EST, "kind": "INQUIRY_7A", "dispute": "DUES", "period_from": "2025-04",
                                                 "period_to": "2025-09", "contributory_uans": 40, "note": "Workers' complaint with payslips",
                                                 "oic_approval": "OIC approved on e-office file (synthetic)"}))["case_id"]
    heard(apfc, case)
    ok(call(apfc, "POST", f"{BASE}/cases/{case}/orders", {"kind": "7A", "dues": DUES, "reasoning": "Muster roll", "ex_parte": False},
            {"X-Step-Up-Token": step_up(apfc, "pass-order", case, None, 4500000)}))
    appeal = ok(call(legal, "POST", f"{BASE}/cases/{case}/appeals", {"case_no": f"ATA-{case[-4:]}/2026", "filed_on": date.today().isoformat()}))
    assert appeal["pre_deposit_required_paise"] == 3375000 and appeal["heard"] is False
    remand = {"order_date": date.today().isoformat(), "outcome": "REMANDED", "note": "Decide afresh whether they were the contractor's"}
    assert call(legal, "POST", f"{LEGAL}/cases/{appeal['legal_case_id']}/orders", remand)[0] == 422             # not heard before the deposit
    deposited = ok(call(legal, "POST", f"{BASE}/cases/{case}/appeals/{appeal['legal_case_id']}/pre-deposits",
                        {"amount_paise": 3375000, "reference": f"TRRN-PD-{case[-6:]}", "deposited_on": date.today().isoformat()}))
    assert deposited["heard"] is True
    done = ok(call(legal, "POST", f"{LEGAL}/cases/{appeal['legal_case_id']}/orders", remand))
    assert done["effect"] == "remanded to the RPFC-II"
    reopened = ok(call(persona("ro-rpfc2", "/office/inquiries"), "GET", f"{BASE}/cases/{case}"))["inquiry"]
    assert reopened["state"] == "REGISTERED" and reopened["officer_rank"] == "RPFC-II"


def test_prosecution_for_returns_not_filed(persona):
    da, apfc = persona("ro-da-compliance", "/office/inquiries"), persona("ro-apfc", "/office/inquiries")
    status, r = call(da, "POST", f"{BASE}/cases", {"establishment_id": EST, "kind": "NON_FILING", "wage_months": ["2026-07"], "amount_paise": 0,
                                                   "note": "No return for July 2026"})
    case = r["data"]["case_id"] if status == 201 else r["case_id"]                                    # or the case already open
    scn = ok(call(apfc, "POST", f"{BASE}/cases/{case}/prosecutions", {"offence": "NON_FILING_RETURNS", "particulars": "July 2026 return not filed despite notices"},
                  {"X-Step-Up-Token": step_up(apfc, "issue-prosecution-scn", case)}))
    pid = scn["prosecution_id"]
    owner = persona("emp-owner", "/employer/proceedings")
    ok(call(owner, "POST", f"/api/v1/employers/me/prosecutions/{pid}/replies", {"text": "The return was delayed by a software failure"}))
    steps = f"{BASE}/prosecutions/{pid}/steps"
    assert ok(call(persona("ro-oic", "/office/inquiries"), "POST", steps, {"step": "SANCTION", "note": "Reply not satisfactory"}))["state"] == "SANCTIONED"
    filed = ok(call(persona("ro-eo", "/office/inquiries"), "POST", steps, {"step": "COMPLAINT", "note": "Filed", "court": "Court of the CJM (synthetic)",
                                                                         "complaint_no": f"CC {pid[-4:]}/2026"}))
    legal = persona("ro-legal", "/office/legal")
    listed = {c["legal_case_id"]: c for c in ok(call(legal, "GET", f"{LEGAL}/cases?kind=PROSECUTION"))}
    assert filed["legal_case_id"] in listed
    ok(call(legal, "POST", f"{LEGAL}/cases/{filed['legal_case_id']}/orders", {"order_date": date.today().isoformat(), "outcome": "CONVICTED", "note": "Fine imposed"}))
    mine = {p["prosecution_id"]: p for p in ok(call(owner, "GET", "/api/v1/employers/me/prosecutions"))}
    assert mine[pid]["state"] == "CONVICTED"
