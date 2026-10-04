"""P2.28b on the running stack: member A changes the bank account step by step — the IFSC checked as typed, the account
number twice, check your answers (only "ending …"), the one-time code — and the mock penny-drop refuses an account ending
0000, so the bank's reason is shown with the way back. Nothing is sent to the employer, so the test leaves no request
behind for others."""
import re

from playwright.sync_api import expect

from tests.e2e.test_journey_a_ecr import WEB
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_member_changes_bank_account_step_by_step(persona):
    member = persona("member-a", "/member/kyc")
    member.get_by_role("link", name="Change your bank account").click()
    expect(member).to_have_url(f"{WEB}/member/kyc/bank/new")

    ifsc = member.get_by_label("IFSC", exact=True)
    ifsc.fill("SBIN123")
    member.get_by_role("button", name="Continue").click()
    expect(member.get_by_role("alert").filter(has_text="There is a problem")).to_be_visible()
    ifsc.fill("sbin0001234")
    expect(ifsc).to_have_value("SBIN0001234")                          # uppercased as typed
    member.get_by_role("button", name="Continue").click()

    member.get_by_label("Account number", exact=True).fill("123456780000")
    member.get_by_label("Confirm account number", exact=True).fill("123456780001")
    member.get_by_role("button", name="Continue").click()
    expect(member.get_by_text("The account numbers do not match").first).to_be_visible()
    member.get_by_label("Confirm account number", exact=True).fill("123456780000")
    member.get_by_role("button", name="Continue").click()

    expect(member.get_by_role("heading", name="Check your answers")).to_be_visible()
    expect(member.get_by_text("ending 0000")).to_be_visible()
    expect(member.get_by_text("123456780000")).to_have_count(0)            # never the full number
    member.get_by_role("button", name="Submit").click()
    dialog = member.get_by_role("dialog")
    code = dialog.locator(".demo-otp code")
    expect(code).to_have_text(re.compile(r"^\d{6}$"))
    dialog.get_by_label("One-time code", exact=True).fill(code.inner_text())
    dialog.get_by_role("button", name="Confirm", exact=True).click()

    expect(member.get_by_role("alert").filter(has_text="could not confirm")).to_be_visible(timeout=20_000)
    member.get_by_role("button", name="Enter another account number").click()
    expect(member.get_by_role("heading", name="Account number")).to_be_visible()
