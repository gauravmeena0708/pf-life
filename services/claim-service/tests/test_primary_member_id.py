"""Phase 2, slice 7d: claims go against the primary member ID; a claim for the whole balance needs the other member
IDs of the member's Aadhaar-verified set transferred first; the projection follows PrimaryMemberIdChanged.v1."""
from tests.test_claims_api import SUBJECTS, create, ctx, member  # noqa: F401

MEMBER_B, MEMBER_D = SUBJECTS["member-b"], SUBJECTS["member-d"]


def types_of(client, subject):
    return {a["account_link_id"]: (a["primary"], {t["claim_type"]: t for t in a["types"]})
            for a in client.get("/api/v1/members/me/claims/eligible-types", headers=member(subject)).json()["data"]["accounts"]}


def test_a_secondary_member_id_cannot_claim(ctx):
    client, *_ = ctx
    accounts = types_of(client, MEMBER_D)
    assert accounts["AL-0009"][0] is True and accounts["AL-0008"][0] is False
    reasons = accounts["AL-0008"][1]["ADVANCE_ILLNESS"]["reasons"]
    assert any("does not match with the primary member ID (AL-0009)" in r for r in reasons)
    r = create(client, amount=100000, account="AL-0008", subject=MEMBER_D)
    assert r.status_code == 422 and any("primary member ID" in x for x in r.json()["reasons"])


def test_a_whole_balance_claim_needs_the_rest_of_the_aadhaar_set_transferred(ctx):
    client, *_ = ctx
    [(primary, t)] = types_of(client, MEMBER_B).values()                   # AL-0903 is on BHARAT's older UAN (no login)
    assert primary is True and t["ADVANCE_ILLNESS"]["eligible"]           # an advance is fine
    assert any("All services are not transferred to the primary member ID: AL-0903 holds ₹50,000" in r for r in t["FINAL_SETTLEMENT"]["reasons"])


def test_the_projection_follows_primary_member_id_changed(ctx):
    client, q, deliver = ctx
    deliver("PrimaryMemberIdChanged.v1", {"uan": "100000000007", "set_uans": ["100000000007"], "primary_account_link_id": "AL-0008",
                                          "previous_account_link_id": "AL-0009", "member_ids": ["AL-0008", "AL-0009"]}, "member-service")
    assert dict(q("SELECT account_link_id, is_primary FROM accounts WHERE uan='100000000007'")) in ({"AL-0008": True, "AL-0009": False},
                                                                                                     {"AL-0008": 1, "AL-0009": 0})
