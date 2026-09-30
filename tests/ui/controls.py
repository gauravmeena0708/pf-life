"""Reusable visible controls; no direct fetch, API commands, or mocked business responses."""
import os
import re
from urllib.parse import urlsplit

from playwright.sync_api import expect

BASE_URL = os.getenv("UI_BASE_URL", "http://localhost:5173").rstrip("/")
PASSWORD = os.getenv("UI_DEMO_PASSWORD", "Demo@2026!")


def switch_persona(page, persona: str, landing: str, heading: str, record=None, role=None):
    if page.url == "about:blank":
        page.goto(BASE_URL)
    expect(page.locator(".demo-banner")).to_contain_text("NOT AN OFFICIAL EPFO SYSTEM")
    page.locator(".account-menu > summary").click()
    search = page.get_by_label("Search demo personas", exact=True)
    expect(search).to_be_visible()
    search.fill(persona)
    option = page.locator(f'.persona-option[data-persona="{persona}"]')
    if record:
        record.step(page, role, "Choose your demo persona",
                    f"Open the account menu in the header, search for {persona} and select that demo persona.",
                    "The account menu lists the matching synthetic roles with what each demonstrates.",
                    lambda: expect(option).to_be_visible())
    option.click()
    # A real top-level logout/login must reach Keycloak; selecting a role alone is insufficient.
    page.wait_for_url(re.compile(r".*/realms/epfo-demo/.*"))
    expect(page.locator("#password")).to_be_visible()
    if record:
        record.step(page, role, "Authenticate through Keycloak",
                    f"Check that the username is {persona}, enter the demo password, and select Sign In.",
                    "Keycloak requests the credentials for the selected persona.",
                    lambda: expect(page.locator("#password")).to_be_visible())
    if page.locator("#username").count() == 0 and page.locator("#reset-login").count():
        page.locator("#reset-login").click()
    page.locator("#username").fill(persona)
    page.locator("#password").fill(PASSWORD)
    page.locator("#kc-login").click()
    expect(page).to_have_url(BASE_URL + landing)
    expect(page.get_by_role("heading", name=heading, level=1, exact=True)).to_be_visible()
    expect(page.locator(".account-menu > summary")).not_to_contain_text("Sign in (demo)")


def navigate_claims(page, track=False):
    nav = page.get_by_role("navigation", name="Primary navigation", exact=True)
    nav.get_by_role("button", name="Online Services", exact=False).click()
    nav.get_by_role("link", name="Track Claim Status" if track else "Claim (Form-31, 19, 10C & 10D)",
                    exact=True).click()
    expect(page.get_by_role("heading", name="My claims", level=1, exact=True)).to_be_visible()


def confirm_dialog(page, record=None, role=None):
    dialog = page.get_by_role("dialog", name="Confirm this action", exact=True)
    expect(dialog).to_be_visible()
    code = dialog.locator(".demo-otp code")
    expect(code).to_have_text(re.compile(r"^\d{6}$"))
    if record:
        record.step(page, role, "Confirm the transaction intent",
                    "Review the action and reference. Enter the displayed synthetic one-time code and select Confirm.",
                    "The dialog describes the exact action being authorised; the one-time code is a demo simulation.",
                    lambda: expect(dialog.get_by_label("One-time code", exact=True)).to_be_visible())
    dialog.get_by_label("One-time code", exact=True).fill(code.inner_text())
    dialog.get_by_role("button", name="Confirm", exact=True).click()
    expect(dialog).not_to_be_visible()


def open_queue_claim(page, claim_id):
    row = page.get_by_role("row").filter(has=page.get_by_text(claim_id, exact=True))
    expect(row).to_have_count(1, timeout=60_000)
    row.get_by_role("link").click()
    expect(page.get_by_role("heading", name="Case details", level=1, exact=True)).to_be_visible()
    expect(page.locator("#case-summary-heading").locator("..")).to_contain_text(claim_id)


def generate_docket(page, record, role):
    submit = page.get_by_role("button", name="Submit action", exact=True)
    expect(submit).to_be_disabled()
    page.get_by_role("button", name="Generate docket", exact=True).click()
    expect(page.get_by_text("Your docket for this step is generated. You can act on the claim.", exact=True)).to_be_visible()
    expect(submit).to_be_enabled()
    record.step(page, role, "Generate and inspect the Claim Approval Docket",
                "Select Generate docket. Review gross amount, interest, tax, net payable and the illustrative rule version.",
                "The docket is present and Submit action becomes available for this officer's step.",
                lambda: expect(submit).to_be_enabled(), focus=page.locator("#docket-heading"))


def path(page):
    return urlsplit(page.url).path
