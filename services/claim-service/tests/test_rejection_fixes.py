"""P2.23b: every refusal and rejection says what fixes it."""
from datetime import date

from app.domain.claims import eligibility
from epfo_persistence.policy import baseline
from tests.test_claims_api import confirm, create, ctx, events, member  # noqa: F401  (ctx is a fixture)

RULES = baseline()


def account(**kw):
    return {"employee_paise": 100000, "employer_paise": 100000, "date_of_joining": date(2025, 1, 1), "date_of_exit": None, **kw}


def test_each_refusal_says_what_fixes_it_or_when_it_lapses():
    today = date(2026, 10, 4)
    e = eligibility(account(), "FINAL_SETTLEMENT", RULES, today)
    [fix] = [f for f in e["fixes"] if "after you leave" in f["reason"]]
    assert fix["link"] == "/member/service#exit-heading" and "mark" in fix["fix"]
    left = eligibility(account(date_of_exit=date(2026, 9, 10)), "FINAL_SETTLEMENT", RULES, today)
    wait = [f for f in left["fixes"] if "months after leaving" in f["reason"]]
    assert wait and wait[0]["fix"].endswith(".") and "2026-11-10" in wait[0]["fix"]                  # two months after the exit
    assert len(e["fixes"]) == len(e["reasons"]) and [f["reason"] for f in e["fixes"]] == e["reasons"]


def test_a_rejected_claim_shows_the_reason_and_its_fix(ctx):
    client, q, deliver = ctx
    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]
    base = {"case_id": "CASE-R", "claim_id": claim_id, "officer_subject": "x", "next_role": None}
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts", "approval_level": 0,
                                         "final": False, "reason": "Cheque shows another name", "recommendation": "REJECT"}, "workflow-service")
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "REJECT", "officer_role": "fo.ss", "approval_level": 1, "final": True,
                                         "reason": "The account is not the member's", "recommendation": "REJECT",
                                         "reason_code": "BANK_DETAILS"}, "workflow-service")
    c = client.get(f"/api/v1/members/me/claims/{claim_id}", headers=member()).json()["data"]
    assert c["state"] == "REJECTED_WITH_REASON"
    assert c["decision_reason"] == "The bank account does not match the records. The account is not the member's"
    assert c["decision_fix"]["code"] == "BANK_DETAILS" and c["decision_fix"]["link"] == "/member/kyc" and "KYC" in c["decision_fix"]["fix"]
    [notice] = [n for n in events(q, "NotificationRequested.v1") if n["template"] == "CLAIM_REJECTED"]
    assert "What to do: Seed your correct bank account" in notice["params"]["reason"]
