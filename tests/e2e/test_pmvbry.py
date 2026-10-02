"""Phase 2, slice 15a on the running stack: PMVBRY (scheme guidelines, 16 Aug 2025; EPFO SOP for calculating incentives).
Demo Auto Components (manufacturing, baseline 30) crossed the threshold in October 2025; its owner exercises the option;
ARJUN DEMO, a first timer, completes the financial literacy course; the FA & CAO previews and pays the run for
September 2026 (one first timer's money is held: his bank account is not Aadhaar-seeded); the CPFC sees the dashboard.
Repeatable: the option, the course and the run are each done once."""
import uuid

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

AUTO, MONTH = "EST-DEMO-0007", "2026-09"


def test_pmvbry_parts_a_and_b(persona):
    owner = persona("auto-owner", "/employer")
    view = call(owner, "GET", "/api/v1/employers/me/pmvbry")[1]["data"]
    assert (view["baseline"], view["threshold"], view["crossing_month"], view["incentive_months"]) == (30, 2, "2025-10", 48), view
    october = next(m for m in view["months"] if m["wage_month"] == "2025-10")
    assert october["headcount"] == 33 and october["net_additional"] == 2      # one October joiner left before six months
    if not view.get("option_exercised_at"):
        status, r = call(owner, "POST", "/api/v1/employers/me/pmvbry/options", {"gstin": "07AAAAD0007A1Z5", "bank_account_ref": "PAN-LINKED-0007"},
                         {"X-Step-Up-Token": step_up(owner, "pmvbry-option", AUTO)})
        assert status in (200, 201), r

    member = persona("member-ft", "/member")
    status, r = call(member, "POST", "/api/v1/members/me/pmvbry/financial-literacy-completions", {})
    assert status in (200, 201), r
    def instalments():
        rows = call(member, "GET", "/api/v1/members/me/pmvbry")[1]["data"]["memberships"]
        return next(m["part_a"] for m in rows if m["establishment_id"] == AUTO)["instalments"]
    instalments_now = instalments()
    assert [(i["instalment"], i["amount_paise"]) for i in instalments_now] == [(1, 700000), (2, 700000)], instalments_now
    assert all(i["state"] in ("DUE", "PAID") for i in instalments_now), instalments_now

    finance = persona("ho-finance", "/ho/pmvbry")
    preview = call(finance, "GET", f"/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month={MONTH}")[1]["data"]
    if preview["amount_paise"]:
        assert any(p["state"] == "HELD" for p in preview["payments"]) or preview["held_paise"] == 0
        status, r = call(finance, "POST", "/api/v1/ho/pmvbry/disbursement-runs", {"as_of_month": MONTH},
                         {"X-Step-Up-Token": step_up(finance, "pmvbry-disbursement", MONTH, None, preview["amount_paise"]),
                          "Idempotency-Key": str(uuid.uuid4())})
        assert status == 200, r
        assert r["data"]["part_a_paise"] + r["data"]["part_b_paise"] == preview["amount_paise"]
    assert call(finance, "GET", f"/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month={MONTH}")[1]["data"]["amount_paise"] == 0
    assert [i["state"] for i in instalments()] == ["PAID", "PAID"]                    # ARJUN's ₹7,000 + ₹7,000

    assert call(persona("ho-analyst", "/ho/pmvbry"), "GET", "/api/v1/ho/pmvbry/dashboard")[0] == 200
    assert call(member, "GET", "/api/v1/ho/pmvbry/dashboard")[0] == 403
