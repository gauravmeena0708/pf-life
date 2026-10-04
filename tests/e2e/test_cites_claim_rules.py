"""P2.5d on the running stack — claim scrutiny as the CITES manuals set it: the initiator stops and restarts a
claim; the final level cannot reject a claim recommended for approval (only send it back); the initiator
re-forwards it as "Recommend to Reject" and the final level rejects it. Each level generates its docket first. The member is
told the reason and what fixes it (P2.23b)."""
from tests.e2e.officers import decide, recommend
from tests.e2e.test_claim_lifecycle import file_claim
from tests.e2e.test_journey_a_ecr import call, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_stop_restart_and_rejection_only_at_the_final_level(persona):
    member = persona("member-a", "/member/claims")
    c = file_claim(member, "AL-0001", 15000000)                       # ₹1,50,000: DA → AO
    assert c["state"] == "UNDER_REVIEW", c

    def mine(page):
        return next((x for x in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"] if x["claim_id"] == c["claim_id"]), None)
    da = persona("do-caseworker", "/office/work-queue")
    case = wait_for(lambda: mine(da), timeout=30)
    assert case["chain"] == ["fo.da_accounts", "fo.ao"], case
    status, r = call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/stops", {"reason": "Court case on the member ID pending"})
    assert status == 200 and r["data"]["state"] == "STOPPED", r
    assert any(x["case_id"] == case["case_id"] for x in call(da, "GET", "/api/v1/office/stopped-cases")[1]["data"])
    assert call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/restarts")[1]["data"]["state"] == "IN_REVIEW"

    case = wait_for(lambda: mine(da))
    assert recommend(da, case, "Scrutiny done; recommending approval")[0] == 200
    ao = persona("ro-ao", "/office/work-queue")
    case = wait_for(lambda: mine(ao), timeout=30)
    status, r = decide(ao, case, "decisions", "REJECT", "Estimate not from a listed hospital")
    assert status == 409 and r["type"] == "/problems/decision-not-offered", r
    assert decide(ao, case, "decisions", "RETURN", "Recommend rejection: estimate not from a listed hospital")[0] == 200

    case = wait_for(lambda: mine(da), timeout=30)
    assert recommend(da, case, "Agree: not a listed hospital", recommendation="REJECT", reason_code="DOCUMENT_MISSING")[0] == 200
    case = wait_for(lambda: mine(ao), timeout=30)
    status, r = decide(ao, case, "decisions", "REJECT", "Estimate not from a listed hospital")
    assert status == 200 and r["data"]["state"] == "REJECTED", r
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]["state"] == "REJECTED_WITH_REASON", timeout=30)
    timeline = [t["note"] for t in call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]["timeline"]]
    assert "Reviewed; recommended for rejection." in timeline
    # P2.23b: the member is told the reason from the rule set and what fixes it
    claim = call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]
    assert claim["decision_fix"]["code"] == "DOCUMENT_MISSING" and claim["decision_fix"]["link"] == "/member/claims", claim
    assert claim["decision_reason"].startswith("A document the claim needs is missing.")
