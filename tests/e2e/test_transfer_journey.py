"""P2.28c on the running stack: the transfer (Form 13) journey opens from the service history, numbers its steps, and —
for member A, who has no old account to move — says why instead of offering an empty choice. The submission itself is
covered by the web tests: a real one here would take member B's old account that test_exit_transfer moves."""
from playwright.sync_api import expect

from tests.e2e.test_journey_a_ecr import WEB
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_transfer_journey_explains_when_there_is_nothing_to_move(persona):
    member = persona("member-a", "/member/service")
    member.get_by_role("link", name="Move an old account step by step").click()
    expect(member).to_have_url(f"{WEB}/member/service/transfer/new")
    expect(member.get_by_role("heading", level=1, name="Move an old PF account into your current one")).to_be_visible()
    expect(member.get_by_text("Step 1 of 3")).to_be_visible()
    expect(member.get_by_role("radio")).to_have_count(0)                      # nothing to choose — and it says why
    expect(member.get_by_text("No previous member IDs are available to transfer.")).to_be_visible()
    expect(member.locator("main")).not_to_contain_text("AL-0001 ·")
