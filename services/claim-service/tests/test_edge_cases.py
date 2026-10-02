"""P2.19 edge cases, written as tests first: what happens to money when life does not follow the happy path."""
from tests.test_claims_api import _approved_claim, confirm, create, ctx, events, member  # noqa: F401  (ctx is a fixture)


DEATH = {"uan": "100000000001", "account_link_id": "AL-0001", "date_of_exit": "2026-09-20", "reason": "DEATH_IN_SERVICE", "marked_by": "EMPLOYER"}


def test_death_closes_an_approved_claim_and_credits_back_its_debit(ctx):
    """Member A dies in service with an approved advance not yet paid: it is closed with the reason, so the balance is paid
    once — to the nominees (Form 20) — and the debit comes back (ClaimDecided REJECTED). A second delivery changes nothing."""
    client, q, deliver = ctx
    approved = _approved_claim(client, deliver)
    deliver("MemberExitMarked.v1", DEATH, "member-service")
    c = client.get(f"/api/v1/members/me/claims/{approved}", headers=member()).json()["data"]
    assert c["state"] == "REJECTED_WITH_REASON" and "Form 20" in c["decision_reason"], c
    deliver("MemberExitMarked.v1", DEATH, "member-service")
    closed = [e for e in events(q, "ClaimDecisionRecorded.v1") if e["reason_code"] == "MEMBER_DECEASED"]
    assert [(e["claim_id"], e["decision"]) for e in closed] == [(approved, "REJECTED")]


def test_death_closes_a_claim_under_review(ctx):
    client, _, deliver = ctx
    review = confirm(client, create(client).json()["data"]).json()["data"]
    assert review["state"] == "UNDER_REVIEW"
    deliver("MemberExitMarked.v1", DEATH, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{review['claim_id']}", headers=member()).json()["data"]["state"] == "REJECTED_WITH_REASON"


def test_an_ordinary_exit_leaves_open_claims_alone(ctx):
    client, _, deliver = ctx
    review = confirm(client, create(client).json()["data"]).json()["data"]
    deliver("MemberExitMarked.v1", {"uan": "100000000001", "account_link_id": "AL-0001", "date_of_exit": "2026-09-20",
                                    "reason": "CESSATION", "marked_by": "EMPLOYER"}, "member-service")
    assert client.get(f"/api/v1/members/me/claims/{review['claim_id']}", headers=member()).json()["data"]["state"] == review["state"]
