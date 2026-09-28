"""Form 13 transfer posted once when the case is approved, shown in both passbooks and as Annexure K; exits
recorded from MemberExitMarked.v1. Member D (synthetic) has two member IDs: AL-0008 (previous) and AL-0009."""
from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401  (ctx is a fixture)

MEMBER_D = SEED["keycloak_subjects"]["member-d"]


def approved(case="CASE-T1", to_state="APPROVED"):
    return {"process": "transfer_form13", "instance_id": case, "subject_ref": "100000000007", "from_state": "VERIFIED",
            "to_state": to_state, "operation": "decide", "actor_subject": "ao-1", "actor_role": "fo.ao", "terminal": True,
            "data": {"from_account_link_id": "AL-0008", "to_account_link_id": "AL-0009", "attesting_employer": "PRESENT"}}


def test_approved_transfer_moves_the_whole_balance_once_and_gives_annexure_k(ctx):
    client, q = ctx
    from app.infra.transfers import on_member_exit, on_process_transitioned
    _deliver(on_member_exit, {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                              "reason": "CESSATION", "marked_by": "MEMBER"}, "MemberExitMarked.v1")
    assert q("SELECT status, date_of_exit FROM establishment_members WHERE account_link_id='AL-0008'")[0][0] == "EXITED"
    _deliver(on_process_transitioned, approved(to_state="VERIFIED"), "ProcessTransitioned.v1")      # not yet approved
    assert q("SELECT COUNT(*) FROM transfer_postings")[0][0] == 0
    _deliver(on_process_transitioned, approved(), "ProcessTransitioned.v1")
    _deliver(on_process_transitioned, approved(), "ProcessTransitioned.v1")                           # a re-sent copy
    assert q("SELECT COUNT(*) FROM journals WHERE kind='TRANSFER'")[0][0] == 1
    book = client.get("/api/v1/members/me/passbook", headers=hdr(MEMBER_D, "member", [], establishment=None)).json()["data"]
    balances = {a["account_link_id"]: a["entries"][-1]["running_balance_paise"] for a in book["accounts"]}
    assert balances == {"AL-0008": 0, "AL-0009": 20000000}
    kinds = {a["account_link_id"]: [e["kind"] for e in a["entries"]] for a in book["accounts"]}
    assert kinds["AL-0008"] == ["OPENING_BALANCE", "TRANSFER_OUT"] and kinds["AL-0009"] == ["TRANSFER_IN"]
    k = client.get("/api/v1/members/me/transfers/CASE-T1/annexure-k", headers=hdr(MEMBER_D, "member", [], establishment=None)).json()["data"]
    assert k["transferred_from"]["establishment"] == "Demo Engineering Works" and k["transferred_from"]["date_of_exit"] == "2025-12-31"
    assert (k["employee_share_paise"], k["employer_share_paise"], k["total_paise"]) == (12000000, 8000000, 20000000)
    other = SEED["keycloak_subjects"]["member-a"]
    assert client.get("/api/v1/members/me/transfers/CASE-T1/annexure-k", headers=hdr(other, "member", [], establishment=None)).status_code == 404
    events = [r[0] for r in q("SELECT event_type FROM outbox")]
    assert events.count("TransferPosted.v1") == 1
