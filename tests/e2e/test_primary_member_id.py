"""Phase 2, slice 7d on the running stack: the primary member ID (P) — the latest member ID that has received
contributions, over the member's Aadhaar-verified set — in the service history, the claim screen and the member
360 view; a secondary member ID cannot claim, and a whole-balance claim needs the rest of the set transferred."""
from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_primary_member_id_everywhere(persona):
    member_d = persona("member-d", "/member/service")
    h = call(member_d, "GET", "/api/v1/members/me/service-history")[1]["data"]
    assert h["primary_member_id"] == "AL-0009" and {m["account_link_id"]: m["primary"] for m in h["member_ids"]}["AL-0008"] is False
    accounts = {a["account_link_id"]: a for a in call(member_d, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]}
    assert accounts["AL-0009"]["primary"] is True
    secondary = {t["claim_type"]: t for t in accounts["AL-0008"]["types"]}
    assert not secondary["ADVANCE_ILLNESS"]["eligible"] and any("primary member ID" in r for r in secondary["ADVANCE_ILLNESS"]["reasons"])

    member_b = persona("member-b", "/member/claims")
    [b] = call(member_b, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]
    final = next(t for t in b["types"] if t["claim_type"] == "FINAL_SETTLEMENT")
    assert b["primary"] is True and any("All services are not transferred" in r and "AL-0903" in r for r in final["reasons"]), final
    history = call(member_b, "GET", "/api/v1/members/me/service-history")[1]["data"]
    assert history["aadhaar_set_uans"] == ["100000000903"]

    da = persona("do-caseworker", "/office/claim-tools")
    status, m = call(da, "GET", "/api/v1/office/members/100000000903?purpose=Checking%20the%20Aadhaar-verified%20set")
    assert status == 200 and m["data"]["aadhaar_set_uans"] == ["100000000002", "100000000903"] and m["data"]["primary_member_id"] == "AL-0002", m
