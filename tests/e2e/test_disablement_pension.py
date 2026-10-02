"""P2.13: a disablement pension (EPS para 15). SURESH DEMO left Demo Engineering Works on permanent and total disablement after
7 years — too little service for a monthly pension, but a disablement pension needs none; from the day after the exit,
without a reduction for age. Repeatable: a second run finds the application on file."""
from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

URL = "/api/v1/members/me/pension-applications"
CERT = {"date_of_disablement": "2026-08-12", "certificate_kind": "RPWD_CERTIFICATE", "certificate_ref": "UDID/DL/2026/0915",
        "issued_by": "District Medical Authority (synthetic)", "permanent_and_total": True}


def test_disablement_pension_filed_and_queued_at_the_office(persona):
    suresh = persona("member-disabled", "/member/pension")
    mine = call(suresh, "GET", URL)[1]["data"]
    if not mine:
        status, r = call(suresh, "POST", URL, {})
        assert status == 422 and "10 years" in r["detail"], r                      # an ordinary pension: too little service
        status, r = call(suresh, "POST", URL, {"disablement": CERT})
        assert status == 201, r
        assert (r["data"]["kind"], r["data"]["pension_from"], r["data"]["estimate"]["monthly_paise"]) == ("DISABLED", "2026-08-21", 150000)
        mine = call(suresh, "GET", URL)[1]["data"]
    claim = mine[0]
    assert claim["kind"] == "DISABLED" and claim["disablement"]["certificate_kind"] == "RPWD_CERTIFICATE"
    office = persona("do-caseworker", "/office/pension-claims")
    queue = call(office, "GET", "/api/v1/office/pension-claims")[1]["data"]
    items = queue["items"] if isinstance(queue, dict) else queue
    assert any(c["claim_id"] == claim["claim_id"] for c in items), "the claim waits at the pension desks"
