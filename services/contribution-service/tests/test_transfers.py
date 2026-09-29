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


def test_registered_joinee_joins_the_establishment_and_the_employer_sees_the_ledger(ctx):
    client, q = ctx
    from app.infra.transfers import on_member_registered
    _deliver(on_member_registered, {"uan": "100000000008", "account_link_id": "AL-0010", "member_subject": None, "name": "KIRAN DEMO",
                                    "date_of_birth": "1998-03-04", "gender": "FEMALE", "establishment_id": "EST-DEMO-0001",
                                    "date_of_joining": "2026-09-01", "new_uan": True, "pan_verified": False}, "MemberRegistered.v1")
    assert q("SELECT status FROM establishment_members WHERE account_link_id='AL-0010'") == [("ACTIVE",)]
    signatory = SEED["keycloak_subjects"]["emp-signatory"]
    ledger = client.get("/api/v1/employers/me/members/100000000001/contribution-ledger", headers=hdr(signatory, "employer.signatory", [])).json()["data"]
    assert ledger["member_id"] == "AL-0001" and isinstance(ledger["months"], list)
    other = client.get("/api/v1/employers/me/members/100000000001/contribution-ledger",
                       headers=hdr(signatory, "employer.signatory", [], establishment="EST-DEMO-0002"))
    assert other.status_code == 404


def test_interest_on_a_transferred_member_id_is_credited_where_the_money_went(ctx):
    client, q = ctx
    from app.infra.transfers import on_member_exit, on_process_transitioned
    _deliver(on_member_exit, {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                              "reason": "CESSATION", "marked_by": "MEMBER"}, "MemberExitMarked.v1")
    _deliver(on_process_transitioned, approved(), "ProcessTransitioned.v1")
    finance = SEED["keycloak_subjects"]["ho-finance"]
    plan = client.get("/api/v1/office/accounts/interest-postings?financialYear=2025-26", headers=hdr(finance, "ho.fa_cao", [], establishment=None)).json()["data"]
    old = next(a for a in plan["accounts"] if a["account_link_id"] == "AL-0008")
    assert old["to_credit_paise"] == 20000000 * 825 // 10000                  # earned on AL-0008 during 2025-26
    step = {"action": "post-interest", "resource_id": "2025-26", "amount_paise": plan["total_to_credit_paise"]}
    assert client.post("/api/v1/office/accounts/interest-postings", json={"financial_year": "2025-26"},
                       headers=hdr(finance, "ho.fa_cao", [], step, establishment=None)).status_code == 200
    book = {a["account_link_id"]: a["entries"] for a in client.get("/api/v1/members/me/passbook", headers=hdr(MEMBER_D, "member", [], establishment=None)).json()["data"]["accounts"]}
    assert book["AL-0008"][-1]["running_balance_paise"] == 0                 # nothing lands on the transferred member ID
    interest = [e for e in book["AL-0009"] if e["kind"] == "INTEREST"]
    assert interest and "earned on AL-0008, transferred" in interest[0]["description"]
    again = client.get("/api/v1/office/accounts/interest-postings?financialYear=2025-26", headers=hdr(finance, "ho.fa_cao", [], establishment=None)).json()["data"]
    assert next(a for a in again["accounts"] if a["account_link_id"] == "AL-0008")["to_credit_paise"] == 0   # not credited twice


def test_an_account_without_credit_for_three_years_is_inoperative(ctx):
    client, q = ctx
    da = hdr(SEED["keycloak_subjects"]["do-caseworker"], "fo.da_accounts", [], establishment=None)
    assert client.get("/api/v1/office/accounts/inoperative", headers=da).json()["data"]["accounts"] == []   # the demo balances are recent
    import asyncio
    import app.infra.db as db
    from sqlalchemy import text as t

    async def backdate():
        async with db.engine().begin() as c:
            await c.execute(t("UPDATE journals SET occurred_at='2020-03-31 23:59:59' WHERE business_key='OPENING-AL-0002'"))
    asyncio.run(backdate())
    found = client.get("/api/v1/office/accounts/inoperative", headers=da).json()["data"]["accounts"]
    assert [a["account_link_id"] for a in found] == ["AL-0002"] and found[0]["last_credit"] == "2020-03-31"
    assert client.get("/api/v1/office/accounts/inoperative", headers=hdr(MEMBER_D, "member", [], establishment=None)).status_code == 403


def test_annexure_k_is_reconciled_with_the_vdr_receipt(ctx):
    client, q = ctx
    from app.infra.transfers import on_member_exit, on_process_transitioned
    _deliver(on_member_exit, {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31",
                              "reason": "CESSATION", "marked_by": "MEMBER"}, "MemberExitMarked.v1")
    _deliver(on_process_transitioned, approved(), "ProcessTransitioned.v1")
    da = SEED["keycloak_subjects"]["do-caseworker"]
    url = "/api/v1/office/annexure-k-files/CASE-T1/vdr-reconciliations"
    body = {"receipt_ref": "VDR/2026/0042", "vdr_receipt_paise": 19000000}
    assert client.post(url, json=body, headers=hdr(da, "fo.da_accounts", [], establishment=None)).status_code == 428
    step = lambda amount: {"action": "reconcile-annexure-k-vdr", "resource_id": "CASE-T1", "amount_paise": amount}  # noqa: E731
    short = client.post(url, json=body, headers=hdr(da, "fo.da_accounts", [], step(19000000), establishment=None)).json()["data"]
    assert (short["result"], short["difference_paise"]) == ("MISMATCH", -1000000)
    ok = client.post(url, json={**body, "vdr_receipt_paise": 20000000}, headers=hdr(da, "fo.da_accounts", [], step(20000000), establishment=None))
    assert ok.json()["data"]["result"] == "MATCHED"
    again = client.post(url, json={**body, "vdr_receipt_paise": 20000000}, headers=hdr(da, "fo.da_accounts", [], step(20000000), establishment=None))
    assert again.status_code == 409


def test_a_frozen_establishment_files_no_ecr_until_defrozen(ctx):
    client, q = ctx
    from app.infra.transfers import on_process_transitioned
    from tests.test_ecr_api import EST, signatory, upload
    freeze = {"process": "establishment_freeze", "instance_id": "CASE-F1", "subject_ref": EST, "from_state": None, "to_state": "FROZEN",
              "operation": "freeze", "actor_subject": "rpfc", "actor_role": "zo.rpfc1", "terminal": False, "data": {"order_ref": "ZO/FIA/7"}}
    _deliver(on_process_transitioned, freeze, "ProcessTransitioned.v1")
    r = upload(client).json()["data"]
    f, total = r["filing"], r["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    step = {"action": "approve-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    url = f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals"
    blocked = client.post(url, json={"decision": "APPROVE"}, headers=signatory(step))
    assert blocked.status_code == 403 and blocked.json()["type"] == "/problems/establishment-frozen" and "ZO/FIA/7" in blocked.json()["detail"]
    _deliver(on_process_transitioned, {**freeze, "from_state": "FROZEN", "to_state": "ACTIVE", "operation": "defreeze", "terminal": True},
             "ProcessTransitioned.v1")
    assert client.post(url, json={"decision": "APPROVE"}, headers=signatory(step)).status_code == 200
