"""Tier-3 read models on the running stack: head office, ministry and zone dashboards built from events."""
import json

import pytest

from tests.e2e.test_journey_a_ecr import WEB, call, login

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def as_persona(browser, name):
    page = browser.new_context().new_page()
    login(page, name, "/")
    return page


def test_dashboards_by_role(browser):
    ho = as_persona(browser, "ho-analyst")
    for path in ("/api/v1/monitoring/claims", "/api/v1/monitoring/contributions", "/api/v1/monitoring/data-freshness"):
        status, body = call(ho, "GET", path)
        assert status == 200 and body["data"]["source"], (path, body)
    freshness = call(ho, "GET", "/api/v1/monitoring/data-freshness")[1]["data"]["sources"]
    assert {s["source"] for s in freshness} >= {"claim-service", "grievance-service"}
    ministry = as_persona(browser, "ministry-viewer")
    stats = call(ministry, "GET", "/api/v1/public/statistics")[1]["data"]
    assert "RO-DEMO" not in json.dumps(stats) and "suppressed" in stats              # national totals only
    assert call(ministry, "GET", "/api/v1/monitoring/data-freshness")[0] == 403
    zone = call(as_persona(browser, "zo-acc"), "GET", "/api/v1/zo/dashboards")[1]["data"]
    assert zone["zone_id"] == "ZO-DEMO-01" and zone["claims"]["offices"][0]["office_id"] == "RO-DEMO-01"
    assert call(as_persona(browser, "member-a"), "GET", "/api/v1/monitoring/claims")[0] == 403
    ho.goto(f"{WEB}/dashboards")
    ho.get_by_role("heading", name="Claims by office").wait_for()
