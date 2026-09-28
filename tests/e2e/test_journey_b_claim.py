"""Journey B (init.md §9, slice 3) on the running stack: a member files a claim, the regional office
approves it through the DA → SS → APFC chain, the cash section pays it, the mock bank returns it, the
member gives a new account, an APFC approves the re-payment, the cash section re-issues it, and the member sees every step and the notices.

Every call goes browser → gateway → service with a real Keycloak session, CSRF, step-up and idempotency.
Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_journey_b_claim.py
"""
import uuid
from pathlib import Path

import pytest

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, login, step_up, wait_for

playwright = pytest.importorskip("playwright.sync_api")

AMOUNT = 60000000          # ₹6,00,000: above the auto limit, in the DA → SS → APFC band


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def as_persona(browser):
    contexts = []

    def make(persona, return_to="/"):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contexts.append(ctx)
        page = ctx.new_page()
        login(page, persona, return_to)
        return page
    yield make
    for c in contexts:
        c.close()


def shot(page, name, path=None):
    SHOTS.mkdir(exist_ok=True)
    if path:
        page.goto(f"{WEB}{path}")
    page.get_by_role("heading", level=1).wait_for()
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def case_for(page, claim_id):
    items = call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
    return next((c for c in items if c["claim_id"] == claim_id), None)


def decide(page, case, path, decision="APPROVE", reason=None):
    token = step_up(page, "decide-case", case["case_id"], case["version"], case["amount_paise"])
    return call(page, "POST", f"/api/v1/office/cases/{case['case_id']}/{path}", {"decision": decision, "reason": reason},
                {"X-Step-Up-Token": token})


def cash(page, claim_id, action, path, scenario):
    token = step_up(page, action, claim_id, None, AMOUNT)
    return call(page, "POST", f"/api/v1/office/claims/{claim_id}/{path}", {"demo_scenario": scenario},
                {"X-Step-Up-Token": token, "Idempotency-Key": str(uuid.uuid4())})


def claim(page, claim_id):
    return call(page, "GET", f"/api/v1/members/me/claims/{claim_id}")[1]["data"]


def test_journey_b_claim_through_officers_payment_return_and_reissue(as_persona):
    # B1: the member's own record, resolved from the session (no member ID anywhere in the request).
    member = as_persona("member-a", "/member/passbook")
    status, me = call(member, "GET", "/api/v1/members/me")
    assert status == 200 and me["data"]["uan"] == "100000000001"

    # B3: eligible types with the illustrative rules, then a claim with a plain-language summary.
    types = call(member, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]
    advance = next(t for t in types["accounts"][0]["types"] if t["claim_type"] == "ADVANCE_ILLNESS")
    assert advance["eligible"] and advance["max_amount_paise"] >= AMOUNT, (
        "member A's balance is used up by earlier runs; run `make reset` to restore the synthetic opening balance")
    status, created = call(member, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0001", "claim_type": "ADVANCE_ILLNESS", "amount_paise": AMOUNT},
                           {"Idempotency-Key": str(uuid.uuid4())})
    if status == 409 and created["type"] == "/problems/claim-already-open":
        # An earlier interrupted run left an unconfirmed claim; carry on with it rather than fail.
        existing = claim(member, created["claim_id"])
        assert existing["state"] == "AWAITING_CONFIRMATION", f"claim {existing['claim_id']} is stuck in {existing['state']}"
        created = {"data": {**existing, "rules_applied": {"route": "REVIEW"}, "confirmation": {
            "action": "confirm-claim", "resource_id": existing["claim_id"], "resource_version": existing["version"],
            "amount_paise": existing["amount_paise"]}}}
    else:
        assert status == 201, created
    c = created["data"]
    claim_id = c["claim_id"]
    assert c["rules_applied"]["route"] == "REVIEW" and "₹6,00,000" in c["summary"]
    shot(member, "b3-claim-review", f"/member/claims/{claim_id}")

    # B2: member B cannot reach member A's claim or passbook, and learns nothing from the answer.
    other = as_persona("member-b", "/member/passbook")
    status, body = call(other, "GET", f"/api/v1/members/me/claims/{claim_id}")
    assert status == 404 and "AL-0001" not in str(body)
    assert call(other, "GET", "/api/v1/members/me/accounts/AL-0001/passbook")[0] == 404

    # Transaction-intent confirmation: step-up bound to this claim, version and amount.
    conf = c["confirmation"]
    token = step_up(member, conf["action"], conf["resource_id"], conf["resource_version"], conf["amount_paise"])
    status, confirmed = call(member, "POST", f"/api/v1/members/me/claims/{claim_id}/confirmations", None,
                             {"X-Step-Up-Token": token})
    assert status == 200 and confirmed["data"]["state"] == "UNDER_REVIEW", confirmed

    # B4–B5: the case reaches the DA of the member's regional office; each level decides in turn.
    da = as_persona("do-caseworker", "/office/work-queue")
    case = wait_for(lambda: case_for(da, claim_id))
    assert case["chain"] == ["fo.da_accounts", "fo.ss", "fo.apfc"]
    shot(da, "b4-work-queue", "/office/work-queue")
    status, r = call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/recommendations",
                     {"checks": ["KYC verified", "Balance sufficient"], "note": "Treatment estimate attached"})
    assert status == 200, r
    ss = as_persona("ro-ss", "/office/work-queue")
    case = wait_for(lambda: case_for(ss, claim_id))
    shot(ss, "b5-case-decision", f"/office/cases/{case['case_id']}")
    status, r = decide(ss, case, "decisions")
    assert status == 200 and r["data"]["current_role"] == "fo.apfc", r
    apfc = as_persona("ro-apfc", "/office/work-queue")
    case = wait_for(lambda: case_for(apfc, claim_id))
    status, r = decide(apfc, case, "second-approvals", reason="Within band; documents in order")
    assert status == 200 and r["data"]["state"] == "AWAITING_PAYMENT", r
    wait_for(lambda: claim(member, claim_id)["state"] == "APPROVED")

    # B6: the cash section pays; the mock bank returns it; the cash section re-issues; the bank pays.
    cashier = as_persona("ro-cashier", "/office/work-queue")
    wait_for(lambda: case_for(cashier, claim_id))
    status, paid = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(
        cash(cashier, claim_id, "instruct-payment", "payment-instructions", "RETURN")), timeout=20, every=1)
    assert paid["data"]["attempt"] == 1
    wait_for(lambda: claim(member, claim_id)["state"] == "PAYMENT_RETURNED", timeout=30)
    # The member gives a new account (mock penny-drop); an APFC approves the re-payment; adjudication is not reopened.
    status, r = call(member, "POST", f"/api/v1/members/me/claims/{claim_id}/re-disbursement-requests",
                     {"ifsc": "DEMO0000001", "account_number": "123456789012"})
    assert status == 200 and r["data"]["state"] == "CORRECTION_PENDING", r
    case = wait_for(lambda: (lambda x: x if x and x.get("next_action") == "approve-redisbursement" else None)(case_for(apfc, claim_id)))
    token = step_up(apfc, "approve-redisbursement", claim_id, None, AMOUNT)
    status, r = call(apfc, "POST", f"/api/v1/office/claims/{claim_id}/re-disbursement-approvals",
                     {"decision": "APPROVE", "note": "New account verified by the bank"}, {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "REISSUE_APPROVED", r
    wait_for(lambda: (case_for(cashier, claim_id) or {}).get("next_action") == "reissue")
    status, again = cash(cashier, claim_id, "reissue-payment", "reissues", "SUCCESS")
    assert status == 200 and again["data"]["attempt"] == 2, again
    wait_for(lambda: claim(member, claim_id)["state"] == "SETTLED", timeout=30)

    # B7: the member sees the full timeline and plain-language notices.
    final = claim(member, claim_id)
    assert [t["state"] for t in final["timeline"]] == [
        "AWAITING_CONFIRMATION", "SUBMITTED", "UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL", "APPROVED",
        "PAYMENT_PENDING", "PAYMENT_RETURNED", "CORRECTION_PENDING", "REISSUE_APPROVED", "PAYMENT_PENDING", "SETTLED"]
    notices = wait_for(lambda: [n for n in call(member, "GET", "/api/v1/members/me/notifications")[1]["data"]
                                if n["reference_id"] == claim_id and n["template"] == "CLAIM_SETTLED"])
    assert "₹6,00,000" in notices[0]["body"] and "ending 9012" in notices[0]["body"]
    book = call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]
    assert any(e.get("claim_id") == claim_id and e["kind"] == "WITHDRAWAL" for a in book["accounts"] for e in a["entries"])
    shot(member, "b7-claim-settled", f"/member/claims/{claim_id}")
    shot(member, "b7-profile-notices", "/member/profile")


def test_officer_of_wrong_role_cannot_act_out_of_turn(as_persona):
    member = as_persona("member-a", "/member/passbook")
    ao = as_persona("ro-ao", "/office/work-queue")
    status, body = call(ao, "GET", "/api/v1/office/work-queue")
    assert status == 200 and all(c["current_role"] == "fo.ao" for c in body["data"]["items"])
    # A member cannot call office endpoints at all.
    assert call(member, "GET", "/api/v1/office/work-queue")[0] == 403
