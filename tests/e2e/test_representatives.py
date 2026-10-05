"""P2.24: a member authorises a representative for chosen scopes; the representative acts only within them, through
the gateway, and not after the member revokes."""
from datetime import date, timedelta

from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_representative_acts_only_within_the_scopes_the_member_granted(persona):
    member = persona("member-a", "/member")
    status, granted = call(member, "POST", "/api/v1/members/me/representatives", {
        "representative_username": "rep-demo", "relation": "AGENT", "scopes": ["VIEW_PASSBOOK"],
        "valid_until": (date.today() + timedelta(days=30)).isoformat()})
    assert status == 201, granted
    grant_id = granted["data"]["grant_id"]

    rep = persona("rep-demo", "/representative")
    status, mine = call(rep, "GET", "/api/v1/representatives/me/members")
    assert status == 200 and any(g["grant_id"] == grant_id for g in mine["data"]), mine
    acting = {"X-Acting-For": grant_id}
    status, own = call(member, "GET", "/api/v1/members/me/passbook")
    status_rep, seen = call(rep, "GET", "/api/v1/members/me/passbook", headers=acting)
    assert status == 200 and status_rep == 200, seen
    assert seen["data"] == own["data"]                                        # the member's own passbook, as the member
    assert call(rep, "GET", "/api/v1/members/me/nominations", headers=acting)[0] == 403        # not in the scope
    assert call(rep, "GET", "/api/v1/members/me/passbook")[0] == 403                           # no authorisation named
    assert call(rep, "POST", "/api/v1/members/me/claims", {"claim_type": "FORM_31"}, headers=acting)[0] == 403   # money

    status, _ = call(member, "POST", f"/api/v1/members/me/representatives/{grant_id}/revocations", {})
    assert status == 200
    assert call(rep, "GET", "/api/v1/members/me/passbook", headers=acting)[0] == 403           # revoked at once
