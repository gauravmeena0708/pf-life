"""Phase 2, slice 5a: eligibility preview, documents, cancellation before a decision, audit trails, the CAD,
payment scrolls with return reconciliation, and the forms filed with a claim."""
import base64

from tests.test_claims_api import CASHIER, JOURNEY_B_AMOUNT, SUBJECTS, _approved_claim, confirm, create, ctx, events, hdr, member  # noqa: F401

FA = SUBJECTS["ro-fa-accounts"]
PDF = base64.b64encode(b"%PDF-1.4 synthetic treatment estimate").decode()


def debit(deliver, claim_id, amount=JOURNEY_B_AMOUNT):
    deliver("ClaimDebitPosted.v1", {"journal_id": f"J-{claim_id}", "claim_id": claim_id, "postings": [
        {"account_code": "AC01_EPF", "side": "debit", "amount_paise": amount, "account_link_id": "AL-0001", "share": "employee"},
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": amount}]}, "contribution-service")


def test_preview_documents_and_cancellation_before_a_decision(ctx):
    client, q, _ = ctx
    preview = client.get("/api/v1/members/me/claims/eligibility-preview?formType=31", headers=member()).json()["data"]
    assert preview["accounts"][0]["types"][0]["claim_type"] == "ADVANCE_ILLNESS"
    c = create(client).json()["data"]
    doc = client.post(f"/api/v1/members/me/claims/{c['claim_id']}/documents",
                      json={"filename": "estimate.pdf", "content_type": "application/pdf", "content_base64": PDF}, headers=member())
    assert doc.status_code == 201 and len(doc.json()["data"]["sha256"]) == 64
    fake = client.post(f"/api/v1/members/me/claims/{c['claim_id']}/documents",
                       json={"filename": "x.pdf", "content_type": "application/pdf", "content_base64": base64.b64encode(b"not a pdf").decode()}, headers=member())
    assert fake.status_code == 422
    confirm(client, c)
    url = f"/api/v1/members/me/claims/{c['claim_id']}/cancellations"
    assert client.post(url, headers=member()).status_code == 428
    done = client.post(url, headers=member(step_up={"action": "cancel-claim", "resource_id": c["claim_id"]}))
    assert done.status_code == 200 and done.json()["data"]["state"] == "CANCELLED"
    trail = client.get(f"/api/v1/members/me/claims/{c['claim_id']}/audit-trail", headers=member()).json()["data"]
    assert [e["state"] for e in trail["events"]][-1] == "CANCELLED"
    assert create(client).status_code == 201                                   # a cancelled claim no longer blocks a new one


def test_each_level_generates_the_claim_approval_docket_and_payment_follows_the_last(ctx):
    client, q, deliver = ctx
    claim_id = confirm(client, create(client).json()["data"]).json()["data"]["claim_id"]      # under review
    url = f"/api/v1/office/claims/{claim_id}/cad"
    assert client.post(url, headers=hdr(FA, "fo.fa_accounts")).status_code == 403              # scrutinising officers only
    da = client.post(url, headers=hdr(SUBJECTS["do-caseworker"], "fo.da_accounts"))
    assert da.status_code == 201, da.json()
    assert (da.json()["data"]["gross_paise"], da.json()["data"]["tds_paise"], da.json()["data"]["generated_by_role"]) == (JOURNEY_B_AMOUNT, 0, "fo.da_accounts")
    assert events(q, "CADGenerated.v1")[0]["officer_role"] == "fo.da_accounts"
    base = {"case_id": "CASE-1", "claim_id": claim_id, "officer_subject": "x", "reason": None, "next_role": None, "recommendation": "APPROVE"}
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts", "approval_level": 0, "final": False}, "workflow-service")
    assert client.post(url, headers=hdr(SUBJECTS["ro-ss"], "fo.ss")).status_code == 201           # regenerated at the next level
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "APPROVE", "officer_role": "fo.ss", "approval_level": 1, "final": False}, "workflow-service")
    last = client.post(url, headers=hdr(SUBJECTS["ro-apfc"], "fo.apfc")).json()["data"]
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "APPROVE", "officer_role": "fo.apfc", "approval_level": 2, "final": True}, "workflow-service")
    assert client.post(url, headers=hdr(SUBJECTS["ro-apfc"], "fo.apfc")).status_code == 409       # approved: no more dockets
    assert client.post(f"/api/v1/members/me/claims/{claim_id}/cancellations",
                       headers=member(step_up={"action": "cancel-claim", "resource_id": claim_id})).json()["type"] == "/problems/not-cancellable"
    view = client.get(url, headers=hdr(FA, "fo.fa_accounts")).json()["data"]
    assert view["cad_id"] == last["cad_id"] and [v["generated_by_role"] for v in view["versions"]] == ["fo.da_accounts", "fo.ss", "fo.apfc"]
    static = client.get("/api/v1/office/system/cad-static-data", headers=hdr(FA, "fo.fa_accounts")).json()["data"]
    assert static["loaded"] is True and static["bank_branch_master"]["branches"] > 0
    debit(deliver, claim_id)
    step = {"action": "instruct-payment", "resource_id": claim_id, "amount_paise": JOURNEY_B_AMOUNT}
    paid = client.post(f"/api/v1/office/claims/{claim_id}/payment-instructions", json={},
                       headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "cad-1"})).json()["data"]
    assert paid["net_paise"] == last["net_paise"]
    trail = client.get(f"/api/v1/office/claims/{claim_id}/audit-trail", headers=hdr(SUBJECTS["do-caseworker"], "fo.da_accounts")).json()["data"]
    assert trail["cad"]["cad_id"] == last["cad_id"] and trail["transitions"]


def test_payment_scroll_pays_every_approved_claim_and_reconciles_returns(ctx):
    client, q, deliver = ctx
    claim_id = _approved_claim(client, deliver)
    debit(deliver, claim_id)
    preview = client.get("/api/v1/office/payment-scrolls/ready", headers=hdr(CASHIER, "fo.cash")).json()["data"]
    assert [c["claim_id"] for c in preview["claims"]] == [claim_id]
    total = preview["total_paise"]
    body = {"demo_scenario": "RETURN"}
    assert client.post("/api/v1/office/payment-scrolls", json=body, headers=hdr(CASHIER, "fo.cash")).status_code == 428
    scroll = client.post("/api/v1/office/payment-scrolls", json=body,
                         headers=hdr(CASHIER, "fo.cash", {"action": "generate-scroll", "resource_id": "RO-DEMO-01", "amount_paise": total})).json()["data"]
    assert scroll["claims"] == 1 and events(q, "PaymentScrollGenerated.v1")[0]["claim_ids"] == [claim_id]
    [instructed] = events(q, "PaymentInstructed.v1")
    deliver("PaymentReturned.v1", {"payment_id": instructed["payment_id"], "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                   "reference": claim_id, "reference_id": claim_id, "return_reason": "Account closed (mock)", "mock": True}, "payment-simulator")
    rec = client.post(f"/api/v1/office/payment-scrolls/{scroll['scroll_id']}/return-reconciliations",
                      headers=hdr(CASHIER, "fo.cash", {"action": "reconcile-scroll", "resource_id": scroll["scroll_id"], "amount_paise": total})).json()["data"]
    assert rec["returned"] == [claim_id] and rec["returned_paise"] == JOURNEY_B_AMOUNT
    forms = client.get(f"/api/v1/office/claims/{claim_id}/additional-forms", headers=hdr(CASHIER, "fo.cash")).json()["data"]
    assert forms["claim_id"] == claim_id
