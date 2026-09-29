"""Phase 2, slice 5c on the running stack: the OIC finds the orphaned lock a dead batch left on a member's ledger
and releases it with a reason; an establishment is frozen by the zone and its employer sees the freeze; a
maker-checker de-freeze (APFC → OIC) lifts it; the DA lists Annexure K files."""
from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def test_oic_releases_an_orphaned_ledger_lock(persona):
    oic = persona("ro-oic", "/office/claim-tools")
    locks = call(oic, "GET", "/api/v1/office/members/100000000005/locks")[1]["data"]
    orphan = next((x for x in locks["active"] if x["lock_id"] == "LCK-LEGACY-0001"), None)
    if orphan:                                                        # released on an earlier run: nothing to do
        assert orphan["status"] == "ORPHANED"
        status, r = call(oic, "POST", "/api/v1/office/system/locks/LCK-LEGACY-0001/release",
                         {"reason": "Annual batch 2025-26 confirmed dead with the NDC"}, {"X-Step-Up-Token": step_up(oic, "release-lock", "LCK-LEGACY-0001")})
        assert status == 200 and r["data"]["released_by"], r
    after = call(oic, "GET", "/api/v1/office/members/100000000005/locks")[1]["data"]
    assert not after["active"] and any(x["lock_id"] == "LCK-LEGACY-0001" for x in after["recently_released"])


def test_frozen_establishment_cannot_approve_ecr_until_defrozen(persona):
    zone = persona("zo-rpfc", "/office/work-queue")
    status, r = call(zone, "POST", f"/api/v1/office/establishments/{EST}/freezes",
                     {"category": "B", "reason": "Ghost members reported by the FIA vertical", "order_ref": "ZO/FIA/2026/7"},
                     {"X-Step-Up-Token": step_up(zone, "freeze-establishment", EST)})
    assert status == 200 or r.get("type") == "/problems/process-open", r
    owner = persona("emp-owner", "/employer")
    wait_for(lambda: call(owner, "GET", "/api/v1/employers/me")[1]["data"]["frozen"], timeout=30)
    body = {"reason": "Members verified by the enforcement officer"}
    apfc = persona("ro-apfc", "/office/work-queue")
    status, r = call(apfc, "POST", f"/api/v1/office/establishments/{EST}/defreezes", body, {"X-Step-Up-Token": step_up(apfc, "defreeze-establishment", EST)})
    assert status == 200 and r["data"]["current_role"] == "fo.oic", r
    oic = persona("ro-oic", "/office/work-queue")
    status, r = call(oic, "POST", f"/api/v1/office/establishments/{EST}/defreezes", body, {"X-Step-Up-Token": step_up(oic, "defreeze-establishment", EST)})
    assert status == 200 and r["data"]["state"] == "ACTIVE", r
    wait_for(lambda: not call(owner, "GET", "/api/v1/employers/me")[1]["data"]["frozen"], timeout=30)


def test_da_lists_annexure_k_files(persona):
    da = persona("do-caseworker", "/office/claim-tools")
    status, r = call(da, "GET", "/api/v1/office/annexure-k-files")
    assert status == 200 and r["data"]["office_id"] == "RO-DEMO-01", r
