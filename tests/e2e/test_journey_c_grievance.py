"""Journey C (init.md §9, slice 4) on the running stack: a member files a grievance about a claim, the
regional office replies with evidence, the member escalates to the zone, the zone resolves it, and the
grievance metrics and the append-only audit trail show it all.

Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_journey_c_grievance.py
"""
import base64

import pytest

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, login, step_up, wait_for

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def as_persona(browser):
    contexts = []

    def make(persona, return_to="/"):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contexts.append(ctx)
        page = ctx.new_page()
        login(page, persona, return_to)
        return page
    yield make
    for c in contexts:
        c.close()


def shot(page, name, path):
    SHOTS.mkdir(exist_ok=True)
    page.goto(f"{WEB}{path}")
    page.get_by_role("heading", level=1).wait_for()
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def grievance_case(page, grievance_id):
    items = call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
    return next((c for c in items if c.get("grievance_id") == grievance_id), None)


def test_journey_c_grievance_reply_escalation_resolution_metrics_and_audit(as_persona):
    # C1: the member files a grievance linked to a claim, with a synthetic document.
    member = as_persona("member-a", "/member/claims")
    claims = call(member, "GET", "/api/v1/members/me/claims")[1]["data"]
    linked = claims[0]["claim_id"] if claims else None
    status, g = call(member, "POST", "/api/v1/members/me/grievances", {
        "category": "CLAIM_DELAY", "subject": "Advance paid late",
        "description": "My advance was returned by the bank once and paid only on the second attempt.",
        "linked_claim_id": linked})
    assert status == 201, g
    gid = g["data"]["grievance_id"]
    assert g["data"]["state"] == "ROUTED" and g["data"]["office_id"] == "RO-DEMO-01"
    doc = base64.b64encode(b"SYNTHETIC bank statement for the demo - no real data").decode()
    status, d = call(member, "POST", f"/api/v1/grievances/{gid}/documents",
                     {"filename": "statement.txt", "content_type": "text/plain", "content_base64": doc})
    assert status == 201, d

    # C2: another member and an officer without grievance duties cannot read it.
    other = as_persona("member-b", "/member/passbook")
    status, body = call(other, "GET", f"/api/v1/grievances/{gid}")
    assert status == 404 and "advance" not in str(body).lower()
    apfc = as_persona("ro-apfc", "/office/work-queue")
    assert call(apfc, "GET", f"/api/v1/grievances/{gid}")[0] == 403

    # C3: the regional office's PRO finds it in the work queue, replies and links case evidence.
    pro = as_persona("ro-pro", "/office/work-queue")
    case = wait_for(lambda: grievance_case(pro, gid))
    assert case["kind"] == "GRIEVANCE"
    status, r = call(pro, "POST", f"/api/v1/grievances/{gid}/messages",
                     {"body": "We are checking the payment with the cash section."})
    assert status == 201 and r["data"]["state"] == "IN_PROGRESS", r
    if linked:
        status, r = call(pro, "POST", f"/api/v1/grievances/{gid}/evidence-links",
                         {"evidence_refs": [linked], "note": "Claim timeline shows one bank return and a re-issue"})
        assert status == 201, r

    # C4: the member escalates; the zone takes it up and resolves it (step-up bound to the grievance version).
    status, r = call(member, "POST", f"/api/v1/grievances/{gid}/escalations", {"reason": "I want the delay explained"})
    assert status == 200 and r["data"]["tier"] == "ZO", r
    zone = as_persona("zo-acc", "/office/work-queue")
    wait_for(lambda: grievance_case(zone, gid))
    wait_for(lambda: grievance_case(pro, gid) is None)
    shot(zone, "c4-zone-grievance", f"/office/grievances/{gid}")
    status, r = call(zone, "POST", f"/api/v1/grievances/{gid}/messages", {"body": "The zone has reviewed the payment record."})
    assert r["data"]["state"] == "IN_PROGRESS"
    token = step_up(zone, "resolve-grievance", gid, r["data"]["version"])
    status, r = call(zone, "POST", f"/api/v1/grievances/{gid}/resolution",
                     {"resolution": "The first payment was returned by the bank; it was re-issued and credited."},
                     {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "RESOLVED", r
    wait_for(lambda: grievance_case(zone, gid) is None)
    final = call(member, "GET", f"/api/v1/grievances/{gid}")[1]["data"]
    assert [e["state"] for e in final["entries"] if e["kind"] == "STATUS"] == [
        "REGISTERED", "ROUTED", "IN_PROGRESS", "ESCALATED", "IN_PROGRESS", "RESOLVED"]

    # C5: metrics and the append-only audit trail.
    metrics = wait_for(lambda: (lambda m: m if m["offices"] and m["offices"][0]["resolved"] >= 1 else None)(
        call(zone, "GET", "/api/v1/monitoring/grievances")[1]["data"]))
    assert metrics["offices"][0]["office_id"] == "RO-DEMO-01"
    auditor = as_persona("auditor", "/")
    trail = wait_for(lambda: (lambda d: d if {"GrievanceRegistered.v1", "GrievanceEscalated.v1", "GrievanceResolved.v1"}
                              <= {i["event_type"] for i in d["items"]} else None)(
        call(auditor, "GET", f"/api/v1/audit/events?aggregate_id={gid}")[1]["data"]))
    assert trail["chain"]["valid"] is True
    registered = next(i for i in trail["items"] if i["event_type"] == "GrievanceRegistered.v1")
    correlated = call(auditor, "GET", f"/api/v1/audit/correlations/{registered['correlation_id']}")[1]["data"]
    assert {i["event_type"] for i in correlated["items"]} >= {"GrievanceRegistered.v1", "NotificationRequested.v1"}
    assert call(member, "GET", "/api/v1/audit/events")[0] == 403
    shot(member, "c1-member-grievance", f"/member/grievances/{gid}")
    shot(zone, "c5-grievance-metrics", "/monitoring/grievances")
    shot(auditor, "c5-audit-log", "/audit/log")
