"""P2.28 on the running stack: member A makes a claim through the step-by-step journey — the job by its employer's name,
the claim, the amount (checked as typed, with an error summary), the bank account on record, check your answers, the
one-time code — and gets a confirmation with the reference and when to expect the money. ₹5,000 each run (approved
automatically), then paid by Cash so no claim is left open for the tests that follow."""
import re
import uuid

from playwright.sync_api import expect

from tests.e2e.test_journey_a_ecr import WEB, call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def settle(persona, member, claim_id):
    """Cash pays an automatically approved claim, as for any other, so it ends SETTLED."""
    cashier = persona("ro-cashier", "/office/work-queue")
    amount = call(member, "GET", f"/api/v1/members/me/claims/{claim_id}")[1]["data"]["amount_paise"]
    wait_for(lambda: call(cashier, "POST", f"/api/v1/office/claims/{claim_id}/payment-instructions", {"demo_scenario": "SUCCESS"},
                          {"X-Step-Up-Token": step_up(cashier, "instruct-payment", claim_id, None, amount),
                           "Idempotency-Key": str(uuid.uuid4())})[0] == 200, timeout=30, every=2)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{claim_id}")[1]["data"]["state"] == "SETTLED", timeout=30)


def test_member_claims_step_by_step(persona):
    member = persona("member-a", "/member/claims")
    for left in call(member, "GET", "/api/v1/members/me/claims")[1]["data"]:      # an interrupted earlier run's claim
        if left["claim_type"] == "ADVANCE_ILLNESS" and left["state"] == "AUTO_APPROVED" and left["amount_paise"] == 500000:
            settle(persona, member, left["claim_id"])
    types = call(member, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]
    [account] = [a for a in types if a["account_link_id"] == "AL-0001"]
    illness = next(t for t in account["types"] if t["claim_type"] == "ADVANCE_ILLNESS" and t["eligible"])
    jobs = {e["account_link_id"]: e for e in call(member, "GET", "/api/v1/members/me/employment-history")[1]["data"]}

    member.get_by_role("link", name="Start a claim").click()
    expect(member).to_have_url(f"{WEB}/member/claims/new")
    expect(member.get_by_text("Step 1 of 5")).to_be_visible()
    member.get_by_role("radio", name=re.compile(re.escape(jobs["AL-0001"]["establishment_name"]))).first.check()
    member.get_by_role("button", name="Continue").click()

    member.get_by_role("radio", name=re.compile(re.escape(illness["label"]))).check()
    member.get_by_role("button", name="Continue").click()

    expect(member.get_by_text("Step 3 of 5")).to_be_visible()
    amount = member.get_by_label("Amount in whole rupees")
    amount.fill(str(illness["max_amount_paise"] // 100 + 1))
    member.get_by_role("button", name="Continue").click()
    summary = member.get_by_role("alert").filter(has_text="There is a problem")
    expect(summary).to_be_visible()                                       # above the maximum: said at the top and on the field
    amount.fill("5,000")
    member.get_by_role("button", name="Continue").click()

    expect(member.get_by_role("heading", name="Where it is paid")).to_be_visible()
    member.get_by_role("button", name="Continue").click()
    expect(member.get_by_role("heading", name="Check your answers")).to_be_visible()
    expect(member.get_by_text("₹5,000")).to_be_visible()
    member.get_by_role("button", name="Submit claim").click()

    dialog = member.get_by_role("dialog")
    code = dialog.locator(".demo-otp code")
    expect(code).to_have_text(re.compile(r"^\d{6}$"))
    dialog.get_by_label("One-time code", exact=True).fill(code.inner_text())
    dialog.get_by_role("button", name="Confirm", exact=True).click()

    panel = member.locator(".ui-confirmation")
    expect(panel.get_by_role("heading", name="Claim submitted")).to_be_visible(timeout=20_000)
    reference = panel.locator(".ui-reference").inner_text()
    assert re.fullmatch(r"CLM-[0-9A-F]+", reference), reference
    expect(panel.get_by_text(re.compile(r"Expect it by \d\d/\d\d/\d{4}"))).to_be_visible()
    claim = call(member, "GET", f"/api/v1/members/me/claims/{reference}")[1]["data"]
    assert claim["amount_paise"] == 500000 and claim["state"] == "AUTO_APPROVED", claim
    settle(persona, member, reference)
