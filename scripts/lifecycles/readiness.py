"""Verify synthetic sign-in readiness before submitting any lifecycle business command."""
import os
import time


def wait_for_sign_in(base_url, attempts=12):
    from playwright.sync_api import Error, TimeoutError, expect, sync_playwright

    base_url = base_url.rstrip("/")
    transient = ("net::ERR_CONNECTION_RESET", "net::ERR_SOCKET_NOT_CONNECTED",
                 "net::ERR_CONNECTION_REFUSED", "net::ERR_EMPTY_RESPONSE")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for attempt in range(attempts):
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(15_000)
                try:
                    print(f"Checking isolated sign-in readiness ({attempt + 1}/{attempts})", flush=True)
                    page.goto(base_url + "/auth/login?persona=member-a&return_to=/member/passbook")
                    page.locator("#username").fill("member-a")
                    page.locator("#password").fill(os.getenv("UI_DEMO_PASSWORD", "Demo@2026!"))
                    page.locator("#kc-login").click()
                    expect(page).to_have_url(base_url + "/member/passbook", timeout=15_000)
                    expect(page.get_by_role("heading", name="My passbook", exact=True, level=1)).to_be_visible(timeout=15_000)
                    print("Isolated sign-in and member landing page are ready; no business commands submitted.", flush=True)
                    return
                except Error as error:
                    # Only startup transport/navigation failures are retried. Credential/UI assertion
                    # failures propagate, and lifecycle tests themselves never receive retries.
                    if attempt + 1 == attempts or not (isinstance(error, TimeoutError) or any(code in str(error) for code in transient)):
                        raise
                    print(f"Sign-in transport not ready: {type(error).__name__}; retrying readiness only.", flush=True)
                    time.sleep(5)
                finally:
                    context.close()
        finally:
            browser.close()
