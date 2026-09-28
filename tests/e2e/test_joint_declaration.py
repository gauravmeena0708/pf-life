"""Joint Declaration (tier-2 process) on the running stack: member → employer → DA → SS → AO (minor change),
and the correction appears on the member's profile with a notice at each step."""
import uuid

import pytest

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, login, step_up, wait_for

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def persona(browser):
    made = []

    def make(name, return_to="/"):
        ctx = browser.new_context()
        made.append(ctx)
        page = ctx.new_page()
        login(page, name, return_to)
        return page
    yield make
    for c in made:
        c.close()


def test_member_correction_through_employer_and_office(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    member = persona("member-b", "/member/profile")
    me = call(member, "GET", "/api/v1/members/me")[1]["data"]
    father = f"RAMESH {uuid.uuid4().hex[:4].upper()} DEMO"
    token = step_up(member, "submit-joint-declaration", me["uan"])
    status, jd = call(member, "POST", "/api/v1/members/me/joint-declarations", {
        "parameter": "FATHER_NAME", "current_value": "not recorded", "corrected_value": father,
        "reason": "Father's name missing from the employer's records"}, {"X-Step-Up-Token": token})
    assert status == 200, jd
    case = jd["data"]
    assert case["data"]["change_class"] == "MINOR"

    signatory = persona("emp-signatory", "/employer")
    listed = wait_for(lambda: [j for j in call(signatory, "GET", "/api/v1/employers/me/joint-declarations")[1]["data"] if j["case_id"] == case["case_id"]])
    token = step_up(signatory, "attest-joint-declaration", case["case_id"], listed[0]["version"])
    status, r = call(signatory, "POST", f"/api/v1/employers/me/joint-declarations/{case['case_id']}/decisions",
                     {"decision": "ATTEST", "note": "Our records agree"}, {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "EMPLOYER_ATTESTED", r

    url = f"/api/v1/office/member-change-requests/{case['case_id']}"
    da = persona("do-caseworker", "/office/work-queue")
    assert any(c["case_id"] == case["case_id"] for c in call(da, "GET", "/api/v1/office/member-change-requests")[1]["data"])
    status, r = call(da, "POST", f"{url}/recommendations", {"documents_checked": "YES", "note": "Birth certificate checked"})
    assert status == 200, r
    status, r = call(persona("ro-ss", "/office/work-queue"), "POST", f"{url}/verifications",
                     {"finding": "CONSISTENT", "note": "Consistent with the KYC documents"})
    assert status == 200, r
    ao = persona("ro-ao", "/office/work-queue")
    token = step_up(ao, "decide-joint-declaration", case["case_id"], r["data"]["version"])
    status, r = call(ao, "POST", f"{url}/decisions", {"decision": "APPROVE", "reason": "Minor correction supported by documents"},
                     {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "APPROVED", r

    wait_for(lambda: call(member, "GET", "/api/v1/members/me")[1]["data"]["profile_extra"].get("father_name") == father, timeout=30)
    notices = wait_for(lambda: (lambda t: t if "JD_APPROVED" in t else None)(
        [n["template"] for n in call(member, "GET", "/api/v1/members/me/notifications")[1]["data"] if n["reference_id"] == case["case_id"]]),
        timeout=30)
    assert notices[0] == "JD_APPROVED" and "JD_EMPLOYER_ATTESTED" in notices
