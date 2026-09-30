"""Phase 2, slice 9c on the running stack: the member's home page — savings across member IDs, what is pending, the
nudges that apply (member-b has no PAN seeded) and the life events — and every member page usable at phone width:
no horizontal scroll, the menu behind one button. Read-only, so repeatable."""
import pytest

from tests.e2e.test_journey_a_ecr import call, login
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

WEB = "http://localhost:5173"
MEMBER_PAGES = ["/member", "/member/passbook", "/member/claims", "/member/profile", "/member/service", "/member/nomination",
                "/member/kyc", "/member/pension", "/member/grievances", "/member/security", "/member/uan-card"]


def test_member_home_shows_savings_pending_nudges_and_life_events(persona):
    member = persona("member-b", "/member")
    member.get_by_role("heading", name="Your PF at a glance").wait_for()
    for heading in ("Your savings", "What is pending", "To do", "What do you want to do?"):
        member.get_by_role("heading", name=heading, exact=True).wait_for()
    assert call(member, "GET", "/api/v1/members/me")[1]["data"]["kyc"]["pan"] != "VERIFIED"
    member.get_by_role("link", name="Complete your KYC", exact=False).first.wait_for()
    member.get_by_text("I changed jobs").wait_for()
    member.goto(f"{WEB}/member/passbook")
    member.get_by_role("navigation", name="Primary navigation").get_by_role("link", name="Home", exact=True).click()
    member.wait_for_url(f"{WEB}/member")                                           # the member's Home is this page


@pytest.fixture
def phone(browser):  # noqa: F811
    ctx = browser.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    login(page, "member-a", "/member")
    yield page
    ctx.close()


def test_member_pages_fit_a_phone(phone):
    for path in MEMBER_PAGES:
        phone.goto(f"{WEB}{path}")
        phone.wait_for_load_state("networkidle")
        width, client = phone.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert width <= client, f"{path} scrolls sideways: {width} > {client}"
    menu = phone.get_by_role("button", name="Menu")
    assert not phone.get_by_role("button", name="View").is_visible()
    menu.click()
    phone.get_by_role("button", name="View").click()
    phone.get_by_role("link", name="Passbook").click()
    phone.wait_for_url(f"{WEB}/member/passbook")
    assert phone.get_by_role("button", name="Menu").is_visible()                   # closed again after navigating
