"""PAST ACCUM VDR RECO (SOP on surrender of exemption, Dec 2023): the receipts of a trust's past accumulations — a demand
draft (a VDR entry), the SDS balance and the securities (HO's reference) — reconciled with the members credited and the
Form SE-6 statement; DA (Accounts) proposes, the APFC approves; each receipt clears the trust transfer receivable."""
from tests.test_ecr_api import SEED, ctx  # noqa: F401
from tests.test_returns import office
from tests.test_trust_and_interest import EST, TOTAL, ingest

S = SEED["keycloak_subjects"]
DA, APFC, CASH = S["do-caseworker"], S["ro-apfc"], S["ro-cashier"]
URL = "/api/v1/office/exempted"


def vdr(client, amount, ref):
    r = client.post("/api/v1/office/vdr-entries", json={"establishment_id": EST, "instrument": "DD", "instrument_ref": ref,
                                                        "amount_paise": amount, "received_on": "2026-09-20"},
                    headers=office(CASH, "fo.cash", {"action": "record-vdr", "resource_id": ref, "amount_paise": amount}))
    assert r.status_code == 201, r.json()
    return r.json()["data"]["vdr_id"]


def propose(client, receipts, statement=TOTAL):
    return client.post(f"{URL}/{EST}/past-accumulation-vdr-reconciliations", json={"statement_total_paise": statement, "receipts": receipts},
                       headers=office(DA, "fo.da_accounts"))


def approve(client, reco, amount, who=APFC):
    return client.post(f"{URL}/past-accumulation-vdr-reconciliations/{reco}/approvals", json={"decision": "APPROVE", "note": "Receipts verified"},
                       headers=office(who, "fo.apfc", {"action": "approve-pa-reco", "resource_id": reco, "amount_paise": amount}))


def receivable(q):
    return dict(q("SELECT side, SUM(amount_paise) FROM journal_lines WHERE account_code='TRUST_TRANSFER_RECEIVABLE' GROUP BY side"))


def test_receipts_in_parts_clear_the_receivable_until_reconciled(ctx):
    client, q = ctx
    dd = vdr(client, 300000, "DD-778899")
    assert propose(client, [{"component": "CASH", "vdr_id": dd}]).json()["type"] == "/problems/nothing-credited"
    assert ingest(client).status_code == 201                                             # ₹4,700 credited to two members
    first = propose(client, [{"component": "CASH", "vdr_id": dd}, {"component": "SDS", "ho_reference": "INV/SDS/2026/41", "amount_paise": 100000}])
    assert first.status_code == 201, first.json()
    reco = first.json()["data"]
    assert reco["summary"]["outstanding_after_paise"] == 70000 and reco["state"] == "PROPOSED"
    assert propose(client, [{"component": "SDS", "ho_reference": "X-1", "amount_paise": 1}]).json()["type"] == "/problems/pending"
    assert approve(client, reco["reco_id"], 400000, who=DA).status_code == 403             # the APFC decides
    done = approve(client, reco["reco_id"], 400000).json()["data"]
    assert done["state"] == "SHORT" and done["summary"]["outstanding_after_paise"] == 70000   # ₹700 still to come
    assert q(f"SELECT state FROM vdr_entries WHERE vdr_id='{dd}'") == [("RECONCILED",)]
    assert receivable(q) == {"debit": TOTAL, "credit": 400000}
    assert propose(client, [{"component": "CASH", "vdr_id": dd}]).status_code == 422       # a receipt is used once
    assert propose(client, [{"component": "SDS", "ho_reference": "INV/SDS/2026/41", "amount_paise": 70000}]).json()["type"] == "/problems/already-received"
    assert propose(client, [{"component": "SECURITIES", "ho_reference": "INV/SEC/2026/9", "amount_paise": 80000}]).json()["type"] == "/problems/more-than-credited"
    last = propose(client, [{"component": "SECURITIES", "ho_reference": "INV/SEC/2026/9", "amount_paise": 70000}]).json()["data"]
    assert approve(client, last["reco_id"], 70000).json()["data"]["state"] == "RECONCILED"
    assert receivable(q) == {"debit": TOTAL, "credit": TOTAL}
    [position] = client.get(f"{URL}/past-accumulation-vdr-reconciliations", headers=office(APFC, "fo.apfc")).json()["data"]
    assert (position["credited_paise"], position["received_paise"], position["outstanding_paise"]) == (TOTAL, TOTAL, 0)
    assert [r["state"] for r in position["reconciliations"]] == ["RECONCILED", "SHORT"]


def test_a_statement_that_differs_from_the_credits_is_not_reconciled(ctx):
    client, _ = ctx
    ingest(client)
    reco = propose(client, [{"component": "SDS", "ho_reference": "INV/SDS/2026/77", "amount_paise": TOTAL}], statement=TOTAL + 50000).json()["data"]
    assert reco["summary"]["statement_difference_paise"] == 50000                          # SE-6 says ₹500 more than credited
    assert approve(client, reco["reco_id"], TOTAL).json()["data"]["state"] == "SHORT"
