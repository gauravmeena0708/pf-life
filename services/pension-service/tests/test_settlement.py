"""Pension settlement end to end (Form 10D → IDS → worksheet → PPO → initial arrear → e-sign → dispatch), scheme
certificates with surrender and aggregation, transfers-in, and the CPPS run with reconciliation and BRS.
Member E (synthetic) retired on 31 January 2026 after 15 years 5 months of service, aged 60."""
import hashlib
import hmac

from tests.test_pensioner_services import at
from tests.test_pensions import APFC_P, SUBJECTS, ctx, hdr  # noqa: F401  (ctx is a fixture)
from datetime import date

MEMBER_E, MEMBER_C = SUBJECTS["member-e"], SUBJECTS["member-c"]
DA_ACC, AO, DA_P, SS_P, CPPS = SUBJECTS["do-caseworker"], SUBJECTS["ro-ao"], SUBJECTS["ro-da-pension"], SUBJECTS["ro-ss-pension"], SUBJECTS["ndc-cpps"]


def step(client, method, path, subject, role, body=None, action=None, resource=None, amount=None):
    su = {"action": action, "resource_id": resource, **({"amount_paise": amount} if amount is not None else {})} if action else None
    return client.request(method, path, json=body, headers=hdr(subject, role, su))


def test_form_10d_goes_through_every_desk_and_the_pension_is_paid_with_its_arrear(ctx, monkeypatch):
    client, _, _ = ctx
    at(monkeypatch, date(2026, 9, 29))
    r = step(client, "POST", "/api/v1/members/me/pension-applications", MEMBER_E, "member", {})
    assert r.status_code == 201, r.json()
    c = r.json()["data"]
    assert c["pension_from"] == "2026-02-01" and c["estimate"]["monthly_paise"] == 321400      # ₹15,000 x 15 / 70
    assert step(client, "POST", "/api/v1/members/me/pension-applications", MEMBER_E, "member", {}).status_code == 409
    cid = c["claim_id"]
    c = step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets", DA_ACC, "fo.da_accounts",
             {"service_months": 185, "pensionable_salary_paise": 1500000, "note": "Service and wages checked with the ledger"}).json()["data"]
    ids = c["ids"]["ids_id"]
    assert step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets/{ids}/approvals", AO, "fo.ao",
                {"decision": "APPROVE", "note": "IDS in order"}).status_code == 428
    c = step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets/{ids}/approvals", AO, "fo.ao",
             {"decision": "APPROVE", "note": "IDS in order"}, "approve-ids", ids).json()["data"]
    assert c["state"] == "IDS_APPROVED"
    c = step(client, "POST", "/api/v1/office/pensions/worksheets", DA_P, "fo.da_pension", {"claim_id": cid}).json()["data"]
    ws = c["worksheet"]
    assert ws["monthly_paise"] == 321400 and ws["rule_version"] == "demo-rules-2026.1"
    c = step(client, "POST", f"/api/v1/office/pensions/worksheets/{ws['worksheet_id']}/approvals", APFC_P, "fo.apfc_pension",
             {"decision": "APPROVE", "note": "Worksheet checked"}, "approve-worksheet", ws["worksheet_id"]).json()["data"]
    c = step(client, "POST", "/api/v1/office/pensions/ppo-issuances", DA_P, "fo.da_pension", {"claim_id": cid}, "issue-ppo", cid).json()["data"]
    ppo = c["ppo_id"]
    assert ppo == "PPO-DEMO-0003"
    c = step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/initial-arrears", DA_P, "fo.da_pension", {"action": "PROPOSE", "note": "Arrear from February"}).json()["data"]
    assert c["arrears"]["months"] == ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    assert c["arrears"]["amount_paise"] == 7 * 321400
    assert step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/initial-arrears", DA_P, "fo.da_pension", {"action": "CHECK", "note": "x" * 5}).status_code == 403
    c = step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/initial-arrears", SS_P, "fo.ss_pension", {"action": "CHECK", "note": "Arrear checked"}).json()["data"]
    assert step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/e-signatures", APFC_P, "fo.apfc_pension", {"decision": "APPROVE", "note": "e-signed"},
                "esign-ppo", ppo, 1).status_code == 403                                   # bound to the arrear amount
    c = step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/e-signatures", APFC_P, "fo.apfc_pension", {"decision": "APPROVE", "note": "e-signed"},
             "esign-ppo", ppo, 7 * 321400).json()["data"]
    assert c["state"] == "PPO_SIGNED"
    c = step(client, "POST", f"/api/v1/office/pensions/ppos/{ppo}/dispatches", DA_P, "fo.da_pension").json()["data"]
    assert c["state"] == "DISPATCHED"
    enquiry = step(client, "GET", f"/api/v1/office/pensions/enquiries?ppo={ppo}", DA_P, "fo.da_pension").json()["data"]
    paid = [p for p in enquiry["pension_payment_details"] if p["kind"] == "MONTHLY"]
    assert len(paid) == 7 and {p["paid_on"] for p in paid} == {"2026-09-29"} and enquiry["ppo_details"]["status"] == "IN_PAYMENT"
    mine = step(client, "GET", "/api/v1/members/me/pension-applications", MEMBER_E, "member").json()["data"]
    assert mine[0]["ppo_id"] == ppo and [h["state"] for h in mine[0]["history"]][-1] == "DISPATCHED"
    roles = [h["role"] for h in mine[0]["history"]]
    assert roles == ["Member", "DA (Accounts)", "AO", "DA (Pension)", "APFC (Pension)", "DA (Pension)", "DA (Pension)", "SS (Pension)", "APFC (Pension)", "DA (Pension)"]


def test_scheme_certificate_surrender_and_aggregation(ctx):
    client, _, _ = ctx
    su = ("request-scheme-certificate", "100000000006")
    r = step(client, "POST", "/api/v1/members/me/pension-scheme-certificates", MEMBER_C, "member", {"confirm": True}, *su)
    assert r.status_code == 201, r.json()
    cert = r.json()["data"]
    assert cert["service_months"] == 41 and cert["state"] == "ISSUED"                      # 2023-01-02 to 2026-06-30
    assert step(client, "GET", "/api/v1/members/me/pension-scheme-certificate", MEMBER_C, "member").json()["data"]["cert_id"] == cert["cert_id"]
    assert step(client, "POST", "/api/v1/members/me/pension-scheme-certificates", MEMBER_E, "member", {"confirm": True},
                "request-scheme-certificate", "100000000004").json()["type"] == "/problems/not-eligible"     # 10 years or more: Form 10D
    r = step(client, "POST", f"/api/v1/members/me/pension-scheme-certificates/{cert['cert_id']}/surrenders", MEMBER_C, "member",
             {"purpose": "MONTHLY_PENSION"}, "surrender-scheme-certificate", cert["cert_id"])
    assert r.json()["data"]["state"] == "SURRENDERED"
    r = step(client, "POST", f"/api/v1/office/pensions/scheme-certificates/{cert['cert_id']}/surrender-adjudications", DA_P, "fo.da_pension",
             {"decision": "CANCEL", "note": "Original certificate received"}, "adjudicate-surrender", cert["cert_id"])
    assert r.json()["data"]["state"] == "CANCELLED"


def test_transfer_in_and_the_cpps_run_reconciled_with_brs(ctx):
    client, _, _ = ctx
    r = step(client, "POST", "/api/v1/office/pensions/transfers-in", DA_P, "fo.da_pension", {
        "ppo_id": "PPO-OTHER-0001", "name": "Moved Demo", "uan": "100000000999", "date_of_birth": "1960-01-01", "pension_start": "2020-01-01",
        "monthly_paise": 250000, "from_office": "RO-OTHER-01", "with_ppo": True})
    assert r.status_code == 201 and r.json()["data"]["status"] == "IN_PAYMENT"
    assert step(client, "POST", "/api/v1/cpps/disbursement-runs", CPPS, "tech.cpps", {"month": "2099-01"}, "run-disbursement", "2099-01").status_code == 422
    run = step(client, "POST", "/api/v1/cpps/disbursement-runs", CPPS, "tech.cpps", {"month": "2026-08"}, "run-disbursement", "2026-08").json()["data"]
    assert run["state"] == "SENT" and {x["ppo_id"] for x in run["lines"]} == {"PPO-DEMO-0001", "PPO-DEMO-0002", "PPO-OTHER-0001"}
    assert step(client, "POST", "/api/v1/cpps/disbursement-runs", CPPS, "tech.cpps", {"month": "2026-08"}, "run-disbursement", "2026-08").status_code == 409
    bad = {"run_id": run["run_id"], "returned_ppo_ids": ["PPO-DEMO-0002"], "paid_total_paise": 361400, "signature": "0" * 64}
    assert step(client, "POST", "/api/v1/integrations/mock-pension-bank/paid-statements", "bank", "public", bad).status_code == 401
    sig = hmac.new(b"dev-mock-pension-bank", f"{run['run_id']}|361400".encode(), hashlib.sha256).hexdigest()
    assert step(client, "POST", "/api/v1/integrations/mock-pension-bank/paid-statements", "bank", "public", {**bad, "signature": sig}).status_code == 200
    rec = step(client, "POST", "/api/v1/cpps/reconciliations", CPPS, "tech.cpps", {"run_id": run["run_id"]}, "reconcile-disbursement", run["run_id"]).json()["data"]
    assert rec["state"] == "RECONCILED" and [e["ppo_id"] for e in rec["exceptions"]] == ["PPO-DEMO-0002"]
    brs = step(client, "POST", "/api/v1/office/pensions/brs-reconciliations", APFC_P, "fo.apfc_pension", {"month": "2026-08"}, "prepare-brs", "2026-08").json()["data"]
    assert brs["scroll_total_paise"] == 111400 + 578600 + 250000 and brs["bank_debit_total_paise"] == 361400 and brs["difference_paise"] == 578600


def test_family_pension_from_the_widow_through_the_same_desks(ctx, monkeypatch):
    client, q, _ = ctx
    at(monkeypatch, date(2026, 9, 29))
    widow = SUBJECTS["claimant-a"]
    url = "/api/v1/claimants/family-pension-applications"
    body = {"form_type": "FORM_10D", "deceased_uan": "100000000901"}
    assert step(client, "POST", url, widow, "claimant", body).status_code == 428
    assert step(client, "POST", url, MEMBER_E, "claimant", body, "file-family-pension", "100000000901").status_code == 404   # not family
    r = step(client, "POST", url, widow, "claimant", body, "file-family-pension", "100000000901")
    assert r.status_code == 201, r.json()
    c = r.json()["data"]
    # GANESH DEMO: 14 years' service at ₹15,000 → ₹15,000 x 14 / 70 = ₹3,000; the spouse gets 50%
    assert (c["kind"], c["pension_from"], c["estimate"]["monthly_paise"]) == ("SPOUSE", "2026-07-16", 150000)
    assert c["family"]["deceased_name"] == "GANESH DEMO" and c["name"] == "LAKSHMI DEMO"
    cid = c["claim_id"]
    c = step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets", DA_ACC, "fo.da_accounts",
             {"service_months": 171, "pensionable_salary_paise": 1500000, "note": "Service to the date of death checked"}).json()["data"]
    ids = c["ids"]["ids_id"]
    step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets/{ids}/approvals", AO, "fo.ao",
         {"decision": "APPROVE", "note": "IDS in order"}, "approve-ids", ids)
    ws = step(client, "POST", "/api/v1/office/pensions/worksheets", DA_P, "fo.da_pension", {"claim_id": cid}).json()["data"]["worksheet"]
    assert ws["monthly_paise"] == 150000 and "50%" in ws["working"]
    step(client, "POST", f"/api/v1/office/pensions/worksheets/{ws['worksheet_id']}/approvals", APFC_P, "fo.apfc_pension",
         {"decision": "APPROVE", "note": "Worksheet checked"}, "approve-worksheet", ws["worksheet_id"])
    ppo = step(client, "POST", "/api/v1/office/pensions/ppo-issuances", DA_P, "fo.da_pension", {"claim_id": cid}, "issue-ppo", cid).json()["data"]["ppo_id"]
    assert q(f"SELECT subject, name FROM pensioners WHERE ppo_id='{ppo}'") == [(widow, "LAKSHMI DEMO")]
    mine = step(client, "GET", url, widow, "claimant").json()["data"]
    assert mine[0]["ppo_id"] == ppo and mine[0]["kind"] == "SPOUSE"
