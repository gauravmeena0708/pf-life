"""Phase 2, slice 5b: death claims (Form 20 PF, Form 5IF EDLI) filed by a nominee, beneficiaries and their shares,
and paper claims inwarded at the PRO counter."""
from tests.test_claims_api import CASHIER, SUBJECTS, ctx, events, hdr  # noqa: F401

CLAIMANT, APFC, PRO = SUBJECTS["claimant-a"], SUBJECTS["ro-apfc"], SUBJECTS["ro-pro-counter"]
UAN = "100000000901"
BALANCE = 40000000                                   # ₹4,00,000 opening balance of AL-0901


def claimant(step_up=None):
    return hdr(CLAIMANT, "claimant", step_up)


def file(client, form="FORM_20", **extra):
    body = {"form_type": form, "deceased_uan": UAN, **extra}
    return client.post("/api/v1/claimants/death-claims", json=body,
                       headers=claimant({"action": "file-death-claim", "resource_id": UAN}))


def approve(deliver, claim_id):
    base = {"case_id": "CASE-D", "claim_id": claim_id, "officer_subject": "x", "reason": None, "next_role": None}
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "RECOMMEND", "officer_role": "fo.da_accounts", "approval_level": 0, "final": False}, "workflow-service")
    deliver("CaseDecisionSubmitted.v1", {**base, "decision": "APPROVE", "officer_role": "fo.ao", "approval_level": 1, "final": True,
                                         "reason": "Nomination in order"}, "workflow-service")


def test_nominee_files_form_20_and_is_paid_in_shares(ctx):
    client, q, deliver = ctx
    body = {"form_type": "FORM_20", "deceased_uan": UAN}
    assert client.post("/api/v1/claimants/death-claims", json=body, headers=claimant()).status_code == 428
    r = file(client)
    assert r.status_code == 201, r.json()
    c = r.json()["data"]
    assert (c["claim_type"], c["form_type"], c["amount_paise"], c["state"]) == ("DEATH_PF", "20", BALANCE, "UNDER_REVIEW")
    assert [(b["name"], b["share_pct"]) for b in c["beneficiaries"]] == [("LAKSHMI DEMO", 60), ("ARJUN DEMO", 40)]
    assert events(q, "ClaimSubmitted.v1")[0]["route"] == "REVIEW"
    assert file(client).status_code == 409                                      # one Form 20 at a time
    assert client.get(f"/api/v1/claimants/death-claims/{c['claim_id']}", headers=claimant()).json()["data"]["claim_id"] == c["claim_id"]
    approve(deliver, c["claim_id"])
    [decision] = events(q, "ClaimDecisionRecorded.v1")
    assert decision["fund"] == "MEMBER_ACCOUNT" and decision["account_link_id"] == "AL-0901"
    deliver("ClaimDebitPosted.v1", {"journal_id": "JD", "claim_id": c["claim_id"], "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": BALANCE}]}, "contribution-service")
    step = {"action": "instruct-payment", "resource_id": c["claim_id"], "amount_paise": BALANCE}
    paid = client.post(f"/api/v1/office/claims/{c['claim_id']}/payment-instructions", json={},
                       headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "d1"}))
    assert paid.status_code == 200, paid.json()
    deliver("PaymentConfirmed.v1", {"payment_id": paid.json()["data"]["payment_id"], "purpose": "CLAIM_SETTLEMENT", "reference_type": "claim",
                                    "reference_id": c["claim_id"], "amount_paise": BALANCE, "mock": True}, "payment-simulator")
    summary = client.get(f"/api/v1/office/death-claims/{c['claim_id']}/shares-summary", headers=hdr(APFC, "fo.apfc")).json()["data"]
    assert summary["state"] == "SETTLED" and [b["disbursed_paise"] for b in summary["beneficiaries"]] == [24000000, 16000000]


def test_edli_is_worked_out_and_paid_from_the_edli_fund(ctx):
    client, q, deliver = ctx
    c = file(client, "FORM_5IF").json()["data"]
    assert c["claim_type"] == "DEATH_EDLI" and c["amount_paise"] >= 25000000           # at least the assured minimum
    approve(deliver, c["claim_id"])                                                      # admitted: the EDLI section decides (P2.8c)
    assert q(f"SELECT state FROM claims WHERE claim_id='{c['claim_id']}'")[0][0] == "PENDING_EDLI_DECISION"
    assert events(q, "ClaimDecisionRecorded.v1") == []
    edli = hdr(SUBJECTS["ro-edli"], "fo.edli")
    amount = client.post(f"/api/v1/office/edli-claims/{c['claim_id']}/benefit-previews", json={"average_monthly_wages_paise": 1500000},
                         headers=edli).json()["data"]
    step = {"action": "decide-edli", "resource_id": c["claim_id"], "resource_version": amount["version"], "amount_paise": amount["amount_paise"]}
    r = client.post(f"/api/v1/office/edli-claims/{c['claim_id']}/decisions",
                    json={"decision": "APPROVE", "average_monthly_wages_paise": 1500000, "reason": "Wages verified on Form 5IF"},
                    headers=hdr(SUBJECTS["ro-edli"], "fo.edli", step))
    assert r.status_code == 200 and r.json()["data"]["state"] == "APPROVED", r.json()
    assert events(q, "ClaimDecisionRecorded.v1")[0]["fund"] == "EDLI"


def test_composite_files_both_claims_with_one_reference_and_separate_events(ctx):
    client, q, _ = ctx
    headers = claimant({"action": "file-death-claim", "resource_id": UAN}) | {"Idempotency-Key": "ccf-death-1"}
    body = {"form_type": "CCF_DEATH", "deceased_uan": UAN}
    r = client.post("/api/v1/claimants/death-claims", json=body, headers=headers)
    assert r.status_code == 201, r.json()
    data = r.json()["data"]
    assert data["composite_ref"].startswith("CCF-")
    assert "Form 10D" in data["next_step"] and "PRO counter" in data["next_step"]
    pf, edli = data["claims"]
    assert [(c["claim_type"], c["form_type"], c["state"]) for c in (pf, edli)] == [
        ("DEATH_PF", "20", "UNDER_REVIEW"), ("DEATH_EDLI", "5IF", "UNDER_REVIEW")]
    assert pf["amount_paise"] == BALANCE and edli["amount_paise"] >= 25000000
    assert pf["composite_ref"] == edli["composite_ref"] == data["composite_ref"]
    assert [(b["name"], b["relation"], b["share_pct"]) for b in pf["beneficiaries"]] == [
        (b["name"], b["relation"], b["share_pct"]) for b in edli["beneficiaries"]]
    assert q("SELECT claim_type, composite_ref FROM claims WHERE composite_ref IS NOT NULL ORDER BY claim_type") == [
        ("DEATH_EDLI", data["composite_ref"]), ("DEATH_PF", data["composite_ref"])]
    submitted = events(q, "ClaimSubmitted.v1")
    assert [(e["claim_id"], e["claim_type"], e["route"]) for e in submitted] == [
        (pf["claim_id"], "DEATH_PF", "REVIEW"), (edli["claim_id"], "DEATH_EDLI", "REVIEW")]
    assert client.get(f"/api/v1/claimants/death-claims/{edli['claim_id']}", headers=claimant()).json()["data"]["composite_ref"] == data["composite_ref"]
    replay = client.post("/api/v1/claimants/death-claims", json=body, headers=headers)
    assert replay.status_code == 201 and replay.json()["data"] == data
    assert len(events(q, "ClaimSubmitted.v1")) == 2
    reused = client.post("/api/v1/claimants/death-claims", json={**body, "process_as": "LSM"}, headers=headers)
    assert reused.status_code == 422 and reused.json()["type"] == "/problems/idempotency-key-reused"


def test_composite_rolls_back_pf_when_edli_is_ineligible(ctx, monkeypatch):
    client, q, _ = ctx
    monkeypatch.setattr("app.api.death_routes.edli_benefit", lambda *args: {"amount_paise": 0, "working": "ineligible"})
    r = file(client, "CCF_DEATH")
    assert r.status_code == 422 and r.json()["type"] == "/problems/not-eligible"
    assert q("SELECT claim_id FROM claims WHERE death_of_uan IS NOT NULL") == []
    assert events(q, "ClaimSubmitted.v1") == []


def test_composite_with_existing_edli_does_not_create_pf(ctx):
    client, q, _ = ctx
    assert file(client, "FORM_5IF").status_code == 201
    r = file(client, "CCF_DEATH")
    assert r.status_code == 409 and r.json()["type"] == "/problems/claim-already-open"
    assert q("SELECT claim_type FROM claims WHERE death_of_uan IS NOT NULL") == [("DEATH_EDLI",)]
    assert len(events(q, "ClaimSubmitted.v1")) == 1


def test_only_a_nominee_files_and_the_apfc_amends_shares_before_payment(ctx):
    client, q, deliver = ctx
    stranger = client.post("/api/v1/claimants/death-claims", json={"form_type": "FORM_20", "deceased_uan": UAN},
                           headers=hdr(SUBJECTS["member-a"], "claimant", {"action": "file-death-claim", "resource_id": UAN}))
    assert stranger.status_code == 404
    c = file(client).json()["data"]
    added = client.post(f"/api/v1/claimants/death-claims/{c['claim_id']}/beneficiaries",
                        json={"name": "Meera Demo", "relation": "DAUGHTER"}, headers=claimant())
    assert added.status_code == 201 and added.json()["data"]["beneficiaries"][2]["share_pct"] == 0
    son, daughter = c["beneficiaries"][1]["beneficiary_id"], f"{c['claim_id']}-B3"
    url = f"/api/v1/office/death-claims/{c['claim_id']}/beneficiaries"
    body = {"share_bp": 3000, "reason": "COURT_ORDER", "note": "Succession certificate dated 2026-08-01"}
    assert client.put(f"{url}/{daughter}/shares", json=body, headers=hdr(APFC, "fo.apfc")).status_code == 428
    over = client.put(f"{url}/{daughter}/shares", json=body, headers=hdr(APFC, "fo.apfc", {"action": "amend-share", "resource_id": daughter}))
    assert over.json()["type"] == "/problems/shares-exceed"                     # 60 + 40 + 30 > 100
    approve(deliver, c["claim_id"])
    assert client.put(f"{url}/{son}/shares", json={**body, "share_bp": 2000}, headers=hdr(APFC, "fo.apfc", {"action": "amend-share", "resource_id": son})).status_code == 200
    deliver("ClaimDebitPosted.v1", {"journal_id": "JD2", "claim_id": c["claim_id"], "postings": [
        {"account_code": "CLAIMS_PAYABLE", "side": "credit", "amount_paise": BALANCE}]}, "contribution-service")
    step = {"action": "instruct-payment", "resource_id": c["claim_id"], "amount_paise": BALANCE}
    blocked = client.post(f"/api/v1/office/claims/{c['claim_id']}/payment-instructions", json={},
                          headers=hdr(CASHIER, "fo.cash", step, **{"Idempotency-Key": "d2"}))
    assert blocked.json()["type"] == "/problems/shares-incomplete"             # 60 + 20 + 0 = 80 %
    fixed = client.put(f"{url}/{daughter}/shares", json={**body, "share_bp": 2000},
                       headers=hdr(APFC, "fo.apfc", {"action": "amend-share", "resource_id": daughter})).json()["data"]
    assert fixed["payable"] is True and fixed["shares_total_pct"] == 100
    amended = events(q, "BeneficiaryShareAmended.v1")
    assert [(e["previous_share_bp"], e["new_share_bp"]) for e in amended] == [(4000, 2000), (0, 2000)]


def test_pro_counter_inwards_paper_claims_and_pension_updations(ctx):
    client, q, _ = ctx
    body = {"form_type": "FORM_19", "uan": "100000000001", "filed_by": "MEMBER", "details": {"pages": 3}}
    assert client.post("/api/v1/office/physical-claims", json=body, headers=hdr(SUBJECTS["member-a"], "member")).status_code == 403
    r = client.post("/api/v1/office/physical-claims", json=body, headers=hdr(PRO, "fo.pro_intake"))
    assert r.status_code == 201 and r.json()["data"]["state"] == "INWARDED"
    lc = {"form_type": "PHYSICAL_LC_UPDATION", "uan": "100000000001", "filed_by": "PENSIONER"}
    assert client.post("/api/v1/office/physical-claims", json=lc, headers=hdr(PRO, "fo.pro_intake")).status_code == 422   # needs the PPO
    routed = client.post("/api/v1/office/physical-claims", json={**lc, "ppo_id": "PPO-DEMO-1"}, headers=hdr(PRO, "fo.pro_intake")).json()["data"]
    assert routed["state"] == "ROUTED"
    assert [e["form_type"] for e in events(q, "PhysicalClaimInwarded.v1")] == ["FORM_19", "PHYSICAL_LC_UPDATION"]
