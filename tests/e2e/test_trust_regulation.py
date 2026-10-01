"""Phase 2, slice 9d on the running stack: Demo Steel Works' trust files its monthly online return; the exemption cell
sees the scores of the online performance evaluator, the ranking and the priority-matrix flags, and records a
show-cause notice on a category A flag; HO's Exemption Division sees the ranking. Repeatable: a month already filed is
filed again as a revision; an actioned flag stays actioned."""
from datetime import date

from tests.e2e.test_journey_a_ecr import SEED, call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EX = "EST-DEMO-0004"


def september():
    july = SEED["trust_returns"]["returns"][1]
    return {**july, "wage_month": "2026-09", "transfers": [{"date": date.today().isoformat(), "amount_paise": july["due_paise"]}],
            "claims_within_days": 30, "claims_beyond_days": 0, "claims_opening": 4, "claims_received": 26, "pending_reasons": None,
            "invested_paise": 650000000000, "interest_paid_paise": 0}


def test_trust_files_and_the_cell_supervises(persona):
    trust = persona("exempted-trust", "/exempted")
    status, r = call(trust, "POST", "/api/v1/exempted/me/returns", september())
    if status == 409:                                                           # filed by an earlier run
        status, r = call(trust, "POST", "/api/v1/exempted/me/returns", {**september(), "revised": True})
    assert status in (200, 201), r
    sept = r["data"]
    assert sept["score"] == 600 and sept["late_transfer_days"] == 0 and sept["balance_due_paise"] == 0, sept      # on time, all parts full
    assert call(trust, "POST", "/api/v1/exempted/me/returns", {**september(), "excluded": 99})[0] == 422          # Part C does not balance

    cell = persona("ro-exemption", "/office/exempted")
    ranking = call(cell, "GET", "/api/v1/office/exempted/rankings?month=2026-07")[1]["data"]["rankings"]
    july = next(x for x in ranking if x["establishment_id"] == EX)
    assert july["score"] < 600 and "CLAIMS_LATE" in july["flags"], july
    returns = call(cell, "GET", f"/api/v1/office/exempted/{EX}/returns")[1]["data"]["returns"]
    flag = next(f for x in returns if x["wage_month"] == "2026-07" for f in x["flags"] if f["code"] == "CLAIMS_LATE")
    assert flag["category"] == "A"
    if not flag.get("action"):
        url = f"/api/v1/office/exempted/{EX}/flags/{flag['flag_id']}/actions"
        assert call(cell, "POST", url, {"action": "ADVICE", "note": "Settle claims faster"},
                    {"X-Step-Up-Token": step_up(cell, "action-trust-flag", flag["flag_id"])})[0] == 422   # category A: not mere advice
        status, r = call(cell, "POST", url, {"action": "SHOW_CAUSE_NOTICE", "note": "Claims settled beyond the time in July 2026"},
                         {"X-Step-Up-Token": step_up(cell, "action-trust-flag", flag["flag_id"])})
        assert status == 200, r

    ho = persona("ho-exemption", "/ho/exempted-rankings")
    assert any(x["establishment_id"] == EX for x in call(ho, "GET", "/api/v1/office/exempted/rankings?month=2026-09")[1]["data"]["rankings"])
    assert call(persona("member-a", "/member"), "GET", "/api/v1/office/exempted/rankings")[0] == 403
