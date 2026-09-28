"""The claims projection follows exits and Form 13 transfers (member D: AL-0008 → AL-0009)."""
from tests.test_claims_api import SUBJECTS, ctx, member  # noqa: F401  (ctx is a fixture)

MEMBER_D = SUBJECTS["member-d"]


def test_exit_and_transfer_move_eligibility_and_balances(ctx):
    client, q, deliver = ctx
    before = {a["account_link_id"]: a for a in client.get("/api/v1/members/me/claims/eligible-types", headers=member(MEMBER_D)).json()["data"]["accounts"]}
    assert set(before) == {"AL-0008", "AL-0009"}
    deliver("MemberExitMarked.v1", {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                                    "reason": "CESSATION", "marked_by": "MEMBER"}, "member-service")
    deliver("TransferPosted.v1", {"transfer_id": "CASE-T1", "uan": "100000000007", "from_account_link_id": "AL-0008",
                                  "to_account_link_id": "AL-0009", "employee_paise": 12000000, "employer_paise": 8000000,
                                  "journal_id": "J", "postings": []}, "contribution-service")
    rows = dict(q("SELECT account_link_id, employee_paise + employer_paise FROM accounts WHERE account_link_id IN ('AL-0008','AL-0009')"))
    assert rows == {"AL-0008": 0, "AL-0009": 20000000}
    assert q("SELECT date_of_exit FROM accounts WHERE account_link_id='AL-0008'")[0][0] is not None


def test_new_member_id_and_verified_pan_reach_the_projection(ctx):
    client, q, deliver = ctx
    deliver("MemberRegistered.v1", {"uan": "100000000008", "account_link_id": "AL-0010", "member_subject": None, "name": "KIRAN DEMO",
                                    "date_of_birth": "1998-03-04", "gender": "FEMALE", "establishment_id": "EST-DEMO-0001",
                                    "date_of_joining": "2026-09-01", "new_uan": True, "pan_verified": False}, "member-service")
    assert q("SELECT office_id, employee_paise FROM accounts WHERE account_link_id='AL-0010'") == [("RO-DEMO-01", 0)]
    deliver("MemberKycUpdated.v1", {"uan": "100000000002", "kyc_type": "PAN", "status": "VERIFIED", "pan_verified": True,
                                    "bank_ifsc": "DEMO0000002", "bank_account_last4": "0002"}, "member-service")
    assert q("SELECT pan_verified FROM accounts WHERE uan='100000000002'")[0][0] in (True, 1)
