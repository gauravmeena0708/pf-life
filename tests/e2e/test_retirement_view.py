"""P2.23 on the running stack: member A's retirement view — PF at 58 from the ledger, with and without VPF, beside the
pension estimate; the page shows both and what share of the wages they replace. Read-only, repeatable."""
from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_retirement_view_with_a_vpf_what_if(persona):
    member = persona("member-a", "/member/retirement")
    status, r = call(member, "GET", "/api/v1/members/me/retirement-forecast?vpf_pct=10")
    assert status == 200, r
    f = r["data"]
    assert f["in_service"] and f["wages_now_paise"] > 0 and f["balance_now_paise"] > 0, f
    without, with_vpf = f["scenarios"]
    assert with_vpf["corpus_paise"] > without["corpus_paise"] and with_vpf["employer_paise"] == without["employer_paise"]
    assert call(member, "GET", "/api/v1/members/me/retirement-forecast?vpf_pct=95")[0] == 422
    member.get_by_role("heading", name="At 58").wait_for(timeout=15000)
    assert member.get_by_text("12% (as now)").is_visible()
    member.get_by_role("button", name="Show with VPF").click()
    member.get_by_text("12% + 10% VPF").wait_for(timeout=15000)
