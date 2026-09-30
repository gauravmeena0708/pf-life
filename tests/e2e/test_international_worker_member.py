"""Phase 2, slice 9a on the running stack: an international worker signs in as an ordinary member — passbook,
profile and the member menu, with the international-worker coverage page under View — and the claims they may not
make come back refused with the international-worker reason (illustrative rules). Read-only, so repeatable."""
import uuid

from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_an_international_worker_is_a_member_with_the_iw_rules(persona):
    expat = persona("worker-expat", "/member")
    me = call(expat, "GET", "/api/v1/members/me")[1]["data"]
    assert me["uan"] == "100000000907" and me["international_worker"] is True and me["nationality"] == "United States", me
    assert call(expat, "GET", "/api/v1/members/me/passbook")[0] == 200
    assert call(expat, "GET", "/api/v1/members/me/international")[1]["data"]["nationality"] == "United States"

    [account] = call(expat, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]
    types = {t["claim_type"]: t for t in account["types"]}
    advances = [t for name, t in types.items() if name != "FINAL_SETTLEMENT"]
    assert advances and all(not t["eligible"] and any("international workers" in r for r in t["reasons"]) for t in advances), advances
    assert not types["FINAL_SETTLEMENT"]["eligible"] and any("age of 58" in r for r in types["FINAL_SETTLEMENT"]["reasons"])
    status, r = call(expat, "POST", "/api/v1/members/me/claims", {"account_link_id": account["account_link_id"],     # must deny
                     "claim_type": "ADVANCE_ILLNESS", "amount_paise": 100_000}, {"Idempotency-Key": str(uuid.uuid4())})
    assert 400 <= status < 500 and "international workers" in str(r), (status, r)

    expat.get_by_role("button", name="View").click()
    expat.get_by_role("link", name="International worker coverage").click()
    expat.get_by_role("heading", name="International worker coverage").wait_for()
    expat.get_by_text("United States").first.wait_for()


def test_a_domestic_member_has_no_iw_page(persona):
    member = persona("member-a", "/member")
    assert call(member, "GET", "/api/v1/members/me")[1]["data"]["international_worker"] is False
    assert call(member, "GET", "/api/v1/members/me/international")[0] == 404
    member.get_by_role("button", name="View").click()
    assert member.get_by_role("link", name="International worker coverage").count() == 0
