"""UI-only journeys. All business commands are submitted through visible application controls."""
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from scripts.manuals.recording import Recording


def pytest_collection_modifyitems(session, config, items):
    """Select named data cases without introducing skipped/empty parametrized tests."""
    requested = {name.strip() for name in os.getenv("UI_CASE_IDS", "").split(",") if name.strip()}
    if not requested:
        return
    from tests.ui.test_claim_lifecycle import CASE_LINKS
    selected, deselected, covered = [], [], set()
    for item in items:
        identifier = getattr(item, "callspec", None)
        identifier = identifier.params.get("case_id") if identifier else None
        ids = set(CASE_LINKS.get(identifier, [identifier]))
        if requested & ids:
            selected.append(item)
            covered.update(requested & ids)
        else:
            deselected.append(item)
    if covered != requested:
        raise pytest.UsageError("No executable UI case for: " + ", ".join(sorted(requested - covered)))
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    setattr(item, f"report_{report.when}", report)
    # The teardown report includes fixture cleanup. Publish only after that has passed too.
    if report.when == "teardown" and hasattr(item, "ui_recording"):
        reports = [getattr(item, f"report_{phase}", None) for phase in ("setup", "call", "teardown")]
        item.ui_recording.finish(all(report is not None and report.passed for report in reports))


@pytest.fixture(scope="session")
def ui_output():
    default = Path("artifacts/ui-manuals") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = Path(os.getenv("UI_MANUAL_OUTPUT", str(default))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def ui_browser():
    expect.set_options(timeout=30_000)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("UI_HEADED") != "1")
        yield browser
        browser.close()


@pytest.fixture
def ui_pages(ui_browser, request):
    contexts = []

    def new_page():
        context = ui_browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-GB")
        context.set_default_timeout(30_000)
        contexts.append(context)
        page = context.new_page()
        # Runtime errors are test failures even if the page happens to retain an old heading.
        page.on("pageerror", lambda error: errors.append(str(error)))
        return page

    errors = []
    yield new_page
    for context in contexts:
        context.close()
    assert not errors, f"Browser runtime errors: {errors}"


@pytest.fixture
def recording(ui_output, request):
    def make(scenario, title, purpose, scope, prerequisites, limitations, lifecycle=None):
        record = Recording(ui_output, scenario, title, purpose, scope, prerequisites, limitations, lifecycle)
        request.node.ui_recording = record
        if lifecycle:
            request.node.user_properties.append(("lifecycle_cases", ",".join(lifecycle["case_ids"])))
        return record
    return make
