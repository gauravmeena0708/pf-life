"""Phase 2, slice 7b: a cheque recorded by Cash and allocated to a TRRN by the DA (the return posts as if paid
online); VDR rejection; reversing a posted contribution; recrediting a transfer; Appendix E proposed by the DA and
approved by the APFC for each of its types."""
import json

from tests.test_ecr_api import SEED, _deliver, approved, ctx  # noqa: F401
from tests.test_returns import office, regular_posted, submit
from tests.test_transfers import approved as transfer_approved

S = SEED["keycloak_subjects"]
DA, CASH, APFC = S["do-caseworker"], S["ro-cashier"], S["ro-apfc"]
EST = SEED["establishment"]["establishment_id"]


def events(q, kind):
    return [json.loads(p)["envelope"]["payload"] for (p,) in q(f"SELECT payload FROM outbox WHERE event_type='{kind}' ORDER BY id")]


def shares(q, account):
    return dict(q("SELECT share, SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) FROM journal_lines "
                  f"WHERE account_code='AC01_EPF' AND account_link_id='{account}' GROUP BY share"))


def vdr(client, amount, ref="CHQ-000123"):
    body = {"establishment_id": EST, "instrument": "CHEQUE", "instrument_ref": ref, "amount_paise": amount, "received_on": "2026-09-20"}
    r = client.post("/api/v1/office/vdr-entries", json=body, headers=office(CASH, "fo.cash", {"action": "record-vdr", "resource_id": ref, "amount_paise": amount}))
    assert r.status_code == 201, r.json()
    return r.json()["data"]


def test_a_cheque_allocated_to_a_trrn_posts_the_return(ctx):
    client, q = ctx
    f, total = approved(client)
    trrn = submit(client, f, total)
    receipt = vdr(client, total + 100000)                                   # ₹1,000 more than the challan
    listed = client.get("/api/v1/office/receipts/unreconciled", headers=office(DA, "fo.da_accounts")).json()["data"]
    assert [r["vdr_id"] for r in listed["receipts"]] == [receipt["vdr_id"]] and trrn in [c["trrn"] for c in listed["unpaid_challans"]]
    url = f"/api/v1/office/receipts/{receipt['vdr_id']}/trrn-adjustments"
    assert client.post(url, json={"trrn": trrn}, headers=office(DA, "fo.da_accounts")).status_code == 428
    r = client.post(url, json={"trrn": trrn}, headers=office(DA, "fo.da_accounts", {"action": "adjust-trrn", "resource_id": receipt["vdr_id"], "amount_paise": total}))
    assert r.status_code == 200, r.json()
    assert (r.json()["data"]["state"], r.json()["data"]["unallocated_paise"]) == ("PARTIAL", 100000)
    assert q(f"SELECT state FROM ecr_filings WHERE id='{f['filing_id']}'")[0][0] == "POSTED"
    assert events(q, "ChallanStatusChanged.v1")[-1]["status"] == "SETTLED_OFFLINE"
    other = vdr(client, 50000, "DD-000777")
    rej = client.post(f"/api/v1/office/vdr-entries/{other['vdr_id']}/rejections", json={"reason": "Demand draft reported lost"},
                      headers=office(DA, "fo.da_accounts", {"action": "reject-vdr", "resource_id": other["vdr_id"]}))
    assert rej.json()["data"]["state"] == "REJECTED"


def test_reversing_a_posted_contribution(ctx):
    client, q = ctx
    f, total, _ = regular_posted(client)
    account = SEED["members"][0]["account_link_id"]
    before = shares(q, account)
    [(jid,)] = q(f"SELECT id FROM journals WHERE filing_id='{f['filing_id']}' AND kind='CONTRIBUTION'")
    url = f"/api/v1/office/ledger-journals/{jid}/reversals"
    body = {"reason": "Return filed for the wrong establishment"}
    step = {"action": "reverse-journal", "resource_id": jid, "amount_paise": total}
    r = client.post(url, json=body, headers=office(DA, "fo.da_accounts", step))
    assert r.status_code == 200, r.json()
    after = shares(q, account)
    assert after["employee"] == before["employee"] - 180000 and q(f"SELECT state FROM ecr_filings WHERE id='{f['filing_id']}'")[0][0] == "REVERSED"
    assert events(q, "LedgerReversed.v1")[-1]["reversed_kind"] == "CONTRIBUTION"
    assert client.post(url, json=body, headers=office(DA, "fo.da_accounts", step)).status_code == 409
    [(opening,)] = q(f"SELECT id FROM journals WHERE business_key='OPENING-{account}'")
    assert client.post(f"/api/v1/office/ledger-journals/{opening}/reversals", json=body,
                       headers=office(DA, "fo.da_accounts", {"action": "reverse-journal", "resource_id": opening})).status_code == 422


def test_recrediting_a_transfer_puts_the_balance_back(ctx):
    client, q = ctx
    from app.infra.transfers import on_member_exit, on_process_transitioned
    _deliver(on_member_exit, {"uan": "100000000007", "account_link_id": "AL-0008", "date_of_exit": "2025-12-31", "reason": "CESSATION",
                              "marked_by": "MEMBER"}, "MemberExitMarked.v1")
    _deliver(on_process_transitioned, transfer_approved(), "ProcessTransitioned.v1")
    assert sum(shares(q, "AL-0008").values()) == 0
    url = "/api/v1/office/transfers/CASE-T1/recredits"
    body = {"reason": "Receiving office rejected the transfer-in"}
    r = client.post(url, json=body, headers=office(DA, "fo.da_accounts", {"action": "recredit-transfer", "resource_id": "CASE-T1", "amount_paise": 20000000}))
    assert r.status_code == 200 and r.json()["data"]["recredited_to"] == "AL-0008", r.json()
    assert sum(shares(q, "AL-0008").values()) == 20000000 and sum(shares(q, "AL-0009").values()) == 0
    assert events(q, "LedgerReversed.v1")[-1]["reversed_kind"] == "TRANSFER"
    assert client.post(url, json=body, headers=office(DA, "fo.da_accounts", {"action": "recredit-transfer", "resource_id": "CASE-T1",
                                                                              "amount_paise": 20000000})).status_code == 409


def test_appendix_e_types_proposed_and_approved(ctx):
    client, q = ctx
    account = SEED["members"][0]["account_link_id"]
    before = shares(q, account)
    base = {"type": "APPENDIX_E", "account_link_id": account, "notesheet_no": "NS/RO-DEMO-01/2026/41", "notesheet_date": "2026-09-25",
            "remarks": "EPS on higher wages from April 2025 (joint option)"}
    diversion = {**base, "appendix_type": "EPS_DIVERSION", "employer_paise": 116000}
    step = {"action": "propose-appendix-e", "resource_id": account, "amount_paise": 116000}
    assert client.post("/api/v1/office/ledger-adjustments", json={**diversion, "employer_paise": before["employer"] + 100},
                       headers=office(DA, "fo.da_accounts", {**step, "amount_paise": before["employer"] + 100})).status_code == 422
    assert client.post("/api/v1/office/ledger-adjustments", json={**diversion, "eps_paise": 5}, headers=office(DA, "fo.da_accounts", step)).status_code == 422
    p = client.post("/api/v1/office/ledger-adjustments", json=diversion, headers=office(DA, "fo.da_accounts", step))
    assert p.status_code == 201, p.json()
    adj = p.json()["data"]
    assert [(x["account_code"], x["side"]) for x in adj["lines"]] == [("AC01_EPF", "debit"), ("AC10_EPS", "credit")]
    url = f"/api/v1/office/ledger-adjustments/{adj['adjustment_id']}/approvals"
    ok = client.post(url, json={"decision": "APPROVE", "note": "Joint option verified"},
                     headers=office(APFC, "fo.apfc", {"action": "approve-appendix-e", "resource_id": adj["adjustment_id"], "amount_paise": 116000}))
    assert ok.json()["data"]["state"] == "APPROVED" and ok.json()["data"]["journal_id"]
    assert shares(q, account)["employer"] == before["employer"] - 116000
    assert events(q, "LedgerAdjusted.v1")[0]["appendix_type"] == "EPS_DIVERSION"
    excess = {**base, "appendix_type": "EXCESS_INTEREST_DEBIT", "employee_paise": 5000, "employer_paise": 3000, "remarks": "Interest credited twice for 2024-25"}
    e = client.post("/api/v1/office/ledger-adjustments", json=excess,
                    headers=office(DA, "fo.da_accounts", {"action": "propose-appendix-e", "resource_id": account, "amount_paise": 8000})).json()["data"]
    assert e["lines"][-1] == {"account_code": "INTEREST_SUSPENSE", "side": "credit", "amount_paise": 8000}
    rej = client.post(f"/api/v1/office/ledger-adjustments/{e['adjustment_id']}/approvals", json={"decision": "REJECT", "note": "Notesheet not signed"},
                      headers=office(APFC, "fo.apfc", {"action": "approve-appendix-e", "resource_id": e["adjustment_id"], "amount_paise": 8000}))
    assert rej.json()["data"]["state"] == "REJECTED" and shares(q, account)["employee"] == before["employee"]
    listed = client.get("/api/v1/office/ledger-adjustments", headers=office(DA, "fo.da_accounts")).json()["data"]
    assert {x["state"] for x in listed} == {"APPROVED", "REJECTED"}


def test_appendix_e_other_with_a_reduction_binds_the_code_to_the_amounts_entered(ctx):
    client, q = ctx
    account = SEED["members"][0]["account_link_id"]
    body = {"type": "APPENDIX_E", "appendix_type": "OTHER", "account_link_id": account, "employee_paise": -20000, "employer_paise": 5000,
            "eps_paise": 0, "notesheet_no": "NS/1", "notesheet_date": "2026-09-25", "remarks": "Wrong split corrected from the ledger card"}
    r = client.post("/api/v1/office/ledger-adjustments", json=body,
                    headers=office(DA, "fo.da_accounts", {"action": "propose-appendix-e", "resource_id": account, "amount_paise": 25000}))
    assert r.status_code == 201, r.json()
    assert r.json()["data"]["lines"][-1] == {"account_code": "ADJUSTMENT_SUSPENSE", "side": "credit", "amount_paise": 15000}


def test_a_short_cheque_cannot_pay_a_challan(ctx):
    """P2.19: a cheque for less than the TRRN is not split across it — the challan stays due, nothing is posted, and the
    receipt waits unallocated (to be used for another challan, or rejected and returned)."""
    client, q = ctx
    f, total = approved(client)
    trrn = submit(client, f, total)
    short = vdr(client, total - 100000, "CHQ-SHORT-1")                       # ₹1,000 short
    r = client.post(f"/api/v1/office/receipts/{short['vdr_id']}/trrn-adjustments", json={"trrn": trrn},
                    headers=office(DA, "fo.da_accounts", {"action": "adjust-trrn", "resource_id": short["vdr_id"], "amount_paise": total}))
    assert r.status_code == 422 and r.json()["type"] == "/problems/receipt-too-small"
    assert q(f"SELECT status FROM challans WHERE trrn='{trrn}'") == [("DUE",)]
    assert q(f"SELECT state, allocated_paise FROM vdr_entries WHERE vdr_id='{short['vdr_id']}'") == [("UNRECONCILED", 0)]
    assert not q(f"SELECT 1 FROM journals WHERE filing_id='{f['filing_id']}'")
