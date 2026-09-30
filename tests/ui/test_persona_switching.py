import json
from pathlib import Path

from playwright.sync_api import expect

from tests.ui.controls import BASE_URL, switch_persona


def test_persona_switching_uses_real_login_and_role_landing(ui_pages, recording):
    record = recording(
        "persona-switching", "Sign-in and persona switching", "Switch safely between synthetic portal roles.",
        "Member, security analyst and employer account-menu navigation.",
        ["The seeded synthetic stack and Keycloak realm are running.", "Use the demo personas supplied with the POC."],
        ["This is a demo persona selector, not a production impersonation facility.",
         "The security-role gate is checked through its rendered screen; backend permission coverage is in the security suite."],
    )
    page = ui_pages()
    switch_persona(page, "member-a", "/member", "Your PF at a glance", record, "Portal user")
    expect(page.locator(".account-menu > summary")).to_contain_text("member")
    record.step(page, "Portal user", "Check the member workspace", "Confirm that the member passbook is displayed.",
                "The landing page is My passbook and the active account identifies the member role.",
                lambda: expect(page.locator(".account-menu > summary")).to_contain_text("member"))
    page.goto(BASE_URL + "/security/activity")
    expect(page.get_by_role("heading", name="Security role required", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Recent requests", exact=True)).not_to_be_visible()
    record.step(page, "Portal user", "Check the role boundary",
                "While signed in as a member, open /security/activity in the address bar.",
                "Security role required is displayed and request activity is not exposed to the member persona.",
                lambda: expect(page.get_by_role("heading", name="Security role required", exact=True)).to_be_visible())
    switch_persona(page, "security-analyst", "/security/activity", "Request activity", record, "Portal user")
    expect(page.get_by_role("heading", name="Security role required", exact=True)).not_to_be_visible()
    expect(page.get_by_role("heading", name="Recent requests", exact=True)).to_be_visible()
    expect(page.locator(".account-menu > summary")).to_contain_text("ho.security")
    record.step(page, "Portal user", "Check the security workspace",
                "Confirm the security analyst landing page and the recent request activity.",
                "Request activity is displayed with the ho.security account; the role-required message is absent.",
                lambda: expect(page.get_by_role("heading", name="Recent requests", exact=True)).to_be_visible())
    seed = json.loads((Path(__file__).resolve().parents[2] / "scripts/seed/synthetic.json").read_text())
    switch_persona(page, "emp-owner", "/employer", seed["establishment"]["legal_name"], record, "Portal user")
    expect(page.locator(".account-menu > summary")).to_contain_text("employer.owner")
    record.step(page, "Portal user", "Check the employer workspace",
                "Select the establishment owner and sign in again. Confirm the employer workspace is displayed.",
                "The previous security persona has been replaced by employer.owner at /employer.",
                lambda: expect(page).to_have_url(BASE_URL + "/employer"))
