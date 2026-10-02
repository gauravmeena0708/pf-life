"""Gate 1 check (init.md §10): the running stack lets seeded personas log in through Keycloak and the
gateway, and every request path — web → gateway → service — enforces the security rules.

Needs the stack running (`make up`) and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_gate1_walking_skeleton.py
"""
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

WEB = "http://localhost:5173"
PASSWORD = "Demo@2026!"


def login(page, persona: str) -> None:
    page.goto(f"{WEB}/auth/login?persona={persona}&return_to=/")
    page.wait_for_url(re.compile(r"localhost:8080/realms/epfo-demo/"))
    if not page.locator("#username").input_value():
        page.fill("#username", persona)
    page.fill("#password", PASSWORD)
    page.click("#kc-login")
    page.wait_for_url(f"{WEB}/")


def api(page, method: str, path: str) -> tuple[int, dict]:
    result = page.evaluate(
        """async ([method, path]) => {
            const csrf = document.cookie.split('; ').find(c => c.startsWith('epfo-csrf='))?.split('=')[1];
            const headers = {Accept: 'application/json'};
            if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf;
            const r = await fetch(path, {method, headers, credentials: 'include'});
            const text = await r.text();
            return [r.status, text ? JSON.parse(text) : {}];
        }""",
        [method, path],
    )
    return result[0], result[1]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    yield context.new_page()
    context.close()


def test_member_logs_in_and_sees_own_permissions(page):
    login(page, "member-a")
    status, session = api(page, "GET", "/auth/session")
    assert status == 200 and session["authenticated"] and session["stakeholder"] == "member"
    status, body = api(page, "GET", "/api/v1/security/me/permissions")
    assert status == 200 and body["data"]["stakeholder"] == "member"
    endpoints = {g["endpoint"] for g in body["data"]["endpoints"]}
    assert "GET /members/me/passbook" in endpoints
    assert not any(e.split(" ", 1)[1].startswith("/office/") for e in endpoints)


def test_no_token_reaches_the_browser(page):
    login(page, "member-a")
    cookies = {c["name"]: c for c in page.context.cookies()}
    session = cookies["__Host-epfo-session"]
    assert session["httpOnly"] and session["secure"] and session["sameSite"] == "Strict"
    storage = page.evaluate("() => JSON.stringify({...localStorage, ...sessionStorage})")
    readable = page.evaluate("() => document.cookie")
    for blob in (storage, readable):
        assert "eyJ" not in blob  # no JWT anywhere JavaScript can read


def test_member_cannot_call_office_endpoint(page):
    login(page, "member-a")
    status, body = api(page, "GET", "/api/v1/office/work-queue")
    assert status == 403 and body["type"] == "/problems/forbidden"


def test_planned_endpoint_answers_501_planned(page):
    login(page, "ro-apfc")                             # prosecution: planned until P2.11c (the gateway
    status, body = api(page, "POST", "/api/v1/office/compliance/cases/CMP-1/prosecutions")   # says so before any code)
    assert status == 501 and body["type"] == "/problems/planned"


def test_working_endpoint_reaches_service_with_verified_internal_token(page):
    # The service answers only after verifying the gateway's internal JWT (a missing or invalid token gives 401),
    # and it resolves the member from that token's subject. So this proves browser -> gateway -> service auth works.
    login(page, "member-a")
    status, body = api(page, "GET", "/api/v1/members/me/passbook")
    assert status == 200 and [a["account_link_id"] for a in body["data"]["accounts"]] == ["AL-0001"], body


def test_office_persona_reaches_office_service(page):
    login(page, "ro-apfc")
    status, body = api(page, "GET", "/api/v1/office/work-queue")
    assert status == 200 and body["data"]["role"] == "fo.apfc" and body["data"]["office_id"] == "RO-DEMO-01", body


def test_mutation_without_csrf_is_rejected(page):
    login(page, "member-a")
    status = page.evaluate(
        "async () => (await fetch('/api/v1/members/me/security-reports', {method: 'POST', credentials: 'include'})).status")
    assert status == 403


def test_unauthenticated_api_call_is_401(page):
    page.goto(WEB)
    status, body = api(page, "GET", "/api/v1/members/me/passbook")
    assert status == 401


def test_web_shell_renders_demo_banner_and_interfaces(page):
    page.goto(WEB)
    assert "NOT AN OFFICIAL EPFO SYSTEM" in page.inner_text("body")
    page.goto(WEB + "/system-map")                       # the 21 interfaces, from the generated system map
    page.locator(".system-map-grid > article").first.wait_for()
    assert page.locator(".system-map-grid > article").count() == 21
