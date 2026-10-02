"""Phase 2, slice 11d on the running stack (Recovery Manual): Demo Engineering Works' 7A order of June 2026 is unpaid. The
APFC certifies it for recovery (s.8B); the Recovery Officer serves the demand notice, attaches machinery (recording why it
cannot wait) and sells it above the reserve; an 8F notice makes the bank pay; the rest is paid — the certificate closes,
contribution-service books every rupee to the demand, and PMVBRY no longer withholds Part B. HO sees both reports.
Repeatable: the seeded order is recovered once; later runs check what it left."""
from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)
from tests.e2e.test_proceedings_b import ok

SEEDED, ENG, BASE, REC = "CMP-SEED-0002", "EST-DEMO-0002", "/api/v1/office/compliance", "/api/v1/office/recovery"


def excluded(cpfc):
    board = ok(call(cpfc, "GET", "/api/v1/ho/pmvbry/dashboard"))
    return next((e["reason"] for e in board["excluded_establishments"] if e["establishment_id"] == ENG), None)


def test_recovery_of_an_unpaid_7a_order(persona):
    apfc, officer, cpfc = persona("ro-apfc", "/office/inquiries"), persona("ro-recovery", "/office/recovery"), persona("ho-analyst", "/ho/pmvbry")
    status, r = call(apfc, "POST", f"{BASE}/cases/{SEEDED}/recovery-certificates", {"note": "Order of 10 June 2026 unpaid"},
                     {"X-Step-Up-Token": step_up(apfc, "issue-recovery-certificate", SEEDED)})
    if status == 409:                                                  # recovered by an earlier run
        closed = [c for c in ok(call(officer, "GET", f"{REC}/cases")) if c["inquiry_case_id"] == SEEDED]
        assert closed and closed[0]["state"] == "CLOSED" and excluded(cpfc) is None
        return
    assert status == 201, r
    assert excluded(cpfc) and "not complied with" in excluded(cpfc)    # Part B withheld while the order is unpaid
    rid = r["data"]["recovery_case_id"]
    ok(call(officer, "POST", f"{REC}/{rid}/demand-notices"))
    att = ok(call(officer, "POST", f"{REC}/{rid}/attachments", {"kind": "MOVABLE", "description": "Two lathes", "value_paise": 1500000,
                                                               "urgent_reason": "Machinery being moved out at night"},
                  {"X-Step-Up-Token": step_up(officer, "attach-property", rid)}))
    att_id = next(a for a in att["actions"] if a["kind"] == "ATTACHMENT")["detail"]["attachment_id"]
    sold = ok(call(officer, "POST", f"{REC}/{rid}/sales", {"attachment_id": att_id, "reserve_price_paise": 1200000, "sale_price_paise": 1300000,
                                                         "buyer": "Synthetic Traders"}, {"X-Step-Up-Token": step_up(officer, "sell-property", rid, None, 1300000)}))
    assert sold["realised_paise"] == 1300000
    ok(call(apfc, "POST", f"{BASE}/cases/{SEEDED}/recovery-8f", {"garnishee": "BANK", "name": "Demo Bank", "reference": "AC-0002-CURRENT",
                                                                "amount_paise": 500000}, {"X-Step-Up-Token": step_up(apfc, "garnishee-8f", SEEDED, None, 500000)}))
    done = ok(call(officer, "POST", f"{REC}/{rid}/payments", {"amount_paise": 1200000, "reference": f"TRRN-{rid}", "mode": "DIRECT"}))
    assert done["state"] == "CLOSED" and done["outstanding_paise"] == 0
    wait_for(lambda: excluded(cpfc) is None, timeout=30, every=1)      # the demand is paid in the ledger: the bar is lifted
    rec = ok(call(persona("ho-recovery", "/ho/compliance-reports"), "GET", "/api/v1/ho/reports/recovery"))
    assert rec["realised_by_mode_paise"].get("SALE", 0) >= 1300000 and rec["realised_by_mode_paise"].get("GARNISHEE_8F", 0) >= 500000


def test_ho_reports_and_who_may_see_them(persona):
    ho = persona("ho-compliance", "/ho/compliance-reports")
    proceedings = ok(call(ho, "GET", "/api/v1/ho/reports/proceedings"))
    assert proceedings["inquiries"] >= 1 and "7A" in proceedings["by_section"]
    assert call(ho, "GET", "/api/v1/ho/reports/recovery")[0] == 200
    assert call(persona("ho-recovery", "/ho/compliance-reports"), "GET", "/api/v1/ho/reports/proceedings")[0] == 403
    assert call(persona("emp-owner", "/employer"), "GET", "/api/v1/ho/reports/recovery")[0] == 403


def test_instalment_referrals_reach_the_zone_and_head_office(persona):
    """P2.13b through the gateway: the zone's ACC and the CPFC read their referrals; others may not; a referral on a closed
    certificate is refused by the service (not by the gateway)."""
    for who, role in (("zo-acc", "zo.acc"), ("ho-analyst", "ho.cpfc")):
        page = persona(who, "/zo/instalments")
        status, r = call(page, "GET", "/api/v1/zo/recovery/instalment-referrals")
        assert status == 200 and isinstance(r["data"], list), (role, r)
    member = persona("member-a", "/member")
    assert call(member, "GET", "/api/v1/zo/recovery/instalment-referrals")[0] == 403
    oic = persona("ro-oic", "/office/recovery")
    cases = call(oic, "GET", "/api/v1/office/recovery/cases")[1]["data"]
    closed = next((c for c in cases if c["state"] == "CLOSED"), None)
    if closed:
        status, r = call(oic, "POST", f"/api/v1/office/recovery/{closed['recovery_case_id']}/instalment-referrals", {"count": 48, "note": "More than 36 asked"})
        assert status == 409 and r["type"] == "/problems/invalid-state", r
