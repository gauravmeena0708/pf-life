"""Phase 2, slice 8b: employer attestation of claims (Aadhaar not verified), switching a claim's bank account
before payment, auto-transfer on a change of job, and e-nominations reaching the nominees on record."""
from tests.test_claims_api import SUBJECTS, confirm, create, ctx, events, hdr, member  # noqa: F401

MEMBER_A, MEMBER_F, MEMBER_G = SUBJECTS["member-a"], SUBJECTS["member-f"], SUBJECTS["member-g"]
SIGNATORY = SUBJECTS["emp-signatory"]


def signatory(step_up=None, establishment="EST-DEMO-0001"):
    return hdr(SIGNATORY, "employer.signatory", step_up, establishment_id=establishment)


def _filed_by_member_f(client):
    created = create(client, amount=500000, account="AL-0904", subject=MEMBER_F).json()["data"]
    return confirm(client, created, subject=MEMBER_F).json()["data"]


def test_a_claim_without_verified_aadhaar_waits_for_the_employer_then_goes_on(ctx):
    client, q, _ = ctx
    claim = _filed_by_member_f(client)
    assert claim["state"] == "PENDING_EMPLOYER_ATTESTATION"
    assert not [e for e in events(q, "ClaimSubmitted.v1") if e["claim_id"] == claim["claim_id"]]   # the office sees nothing yet
    listed = client.get("/api/v1/employers/me/claim-attestations", headers=signatory()).json()["data"]
    item = next(i for i in listed if i["claim_id"] == claim["claim_id"])
    assert item["uan"] == "100000000904"
    assert client.get("/api/v1/employers/me/claim-attestations", headers=signatory(establishment="EST-DEMO-0002")).json()["data"] == []
    url = f"/api/v1/employers/me/claim-attestations/{claim['claim_id']}/decisions"
    body = {"decision": "ATTEST", "note": "Service and wages checked"}
    assert client.post(url, json=body, headers=signatory()).status_code == 428
    done = client.post(url, json=body, headers=signatory({"action": "attest-claim", "resource_id": claim["claim_id"],
                                                          "resource_version": item["version"]}))
    assert done.status_code == 200, done.text
    assert done.json()["data"]["state"] in ("AUTO_APPROVED", "UNDER_REVIEW")
    assert [e for e in events(q, "ClaimSubmitted.v1") if e["claim_id"] == claim["claim_id"]]


def test_the_employer_can_reject_with_a_reason(ctx):
    client, *_ = ctx
    claim = _filed_by_member_f(client)
    item = next(i for i in client.get("/api/v1/employers/me/claim-attestations", headers=signatory()).json()["data"]
                if i["claim_id"] == claim["claim_id"])
    r = client.post(f"/api/v1/employers/me/claim-attestations/{claim['claim_id']}/decisions",
                    json={"decision": "REJECT", "note": "Not our employee on these dates"},
                    headers=signatory({"action": "attest-claim", "resource_id": claim["claim_id"], "resource_version": item["version"]}))
    assert r.json()["data"]["state"] == "REJECTED_BY_EMPLOYER"
    assert "Not our employee" in r.json()["data"]["decision_reason"]


def test_a_claim_can_be_switched_to_another_verified_account_before_payment(ctx):
    client, q, _ = ctx
    created = create(client, amount=40000000).json()["data"]                  # above the auto limit: stays with the office
    claim = confirm(client, created).json()["data"]
    url = f"/api/v1/members/me/claims/{claim['claim_id']}/bank-details"
    options = client.get(url, headers=member()).json()["data"]
    assert options["switchable"] and {"bank_ifsc": "DEMO0000101", "bank_account_last4": "4321"} in options["verified_accounts"]
    step = {"action": "switch-claim-bank", "resource_id": claim["claim_id"], "resource_version": claim["version"]}
    bad = client.put(url, json={"bank_ifsc": "HDFC0000001", "bank_account_last4": "9999"}, headers=member(step_up=step))
    assert bad.status_code == 422 and bad.json()["type"].endswith("bank-not-verified")
    r = client.put(url, json={"bank_ifsc": "DEMO0000101", "bank_account_last4": "4321"}, headers=member(step_up=step))
    assert r.status_code == 200, r.text
    assert q(f"SELECT payee_account_last4 FROM claims WHERE claim_id='{claim['claim_id']}'")[0][0] == "4321"
    assert any("ending 4321" in t["note"] for t in r.json()["data"]["timeline"])


def test_a_new_verified_bank_account_can_be_chosen(ctx):
    client, q, deliver = ctx
    deliver("MemberKycUpdated.v1", {"uan": "100000000001", "kyc_type": "BANK", "status": "VERIFIED", "pan_verified": True,
                                    "bank_ifsc": "DEMO0000102", "bank_account_last4": "5555"}, "member-service")
    assert ("DEMO0000102", "5555") in [tuple(r) for r in q("SELECT bank_ifsc, bank_account_last4 FROM member_bank_accounts WHERE uan='100000000001'")]


def test_auto_transfer_is_offered_confirmed_and_posted(ctx):
    client, q, deliver = ctx
    status = client.get("/api/v1/members/me/transfers/auto", headers=member(MEMBER_G)).json()["data"]
    assert status["primary_account_link_id"] == "AL-0906"
    [item] = status["eligible"]
    assert item["from_account_link_id"] == "AL-0905" and item["amount_paise"] == 8000000
    url = f"/api/v1/members/me/transfers/auto/{item['transfer_id']}/confirmations"
    assert client.post(url, headers=member(MEMBER_G)).status_code == 428
    step = {"action": "confirm-auto-transfer", "resource_id": item["transfer_id"], "amount_paise": item["amount_paise"]}
    r = client.post(url, headers=member(MEMBER_G, step))
    assert r.status_code == 201, r.text
    [event] = events(q, "AutoTransferConfirmed.v1")
    assert event == {"transfer_id": item["transfer_id"], "uan": "100000000905", "from_account_link_id": "AL-0905",
                     "to_account_link_id": "AL-0906"}
    assert client.post(url, headers=member(MEMBER_G, step)).status_code == 409          # not offered twice
    deliver("TransferPosted.v1", {"transfer_id": item["transfer_id"], "uan": "100000000905", "from_account_link_id": "AL-0905",
                                  "to_account_link_id": "AL-0906", "employee_paise": 4800000, "employer_paise": 3200000,
                                  "journal_id": "J-1", "postings": []}, "contribution-service")
    after = client.get("/api/v1/members/me/transfers/auto", headers=member(MEMBER_G)).json()["data"]
    assert after["eligible"] == [] and after["history"][0]["state"] == "POSTED"


def test_auto_transfer_needs_a_verified_aadhaar(ctx):
    client, *_ = ctx
    status = client.get("/api/v1/members/me/transfers/auto", headers=member(MEMBER_F)).json()["data"]
    assert status["eligible"] == [] and "verified Aadhaar" in status["reasons"][0]


def test_an_e_nomination_replaces_the_nominees_on_record(ctx):
    client, q, deliver = ctx
    deliver("NominationRegistered.v1", {"nomination_id": "NOM-X", "uan": "100000000901", "signed_with": "MOCK_AADHAAR_ESIGN",
                                        "nominees": [{"name": "LAKSHMI DEMO", "relation": "SPOUSE", "share_bp": 10000, "minor": False,
                                                      "guardian_name": None}]}, "member-service")
    rows = q("SELECT name, share_bp, subject FROM nominations WHERE uan='100000000901'")
    assert [(r[0], r[1]) for r in rows] == [("LAKSHMI DEMO", 10000)] and rows[0][2] == SUBJECTS["claimant-a"]   # her login is kept


def test_a_contribution_on_the_new_member_id_moves_the_old_balance_unasked(ctx):
    """P2.21: GIRISH's first contribution on his new primary ID (AL-0906) moves his exited ID's balance (AL-0905) — no request;
    he is told. A contribution on a non-primary ID moves nothing."""
    client, q, deliver = ctx
    posting = lambda link: {"journal_id": f"J-{link}", "payment_id": f"P-{link}", "filing_id": "F", "establishment_id": "EST-DEMO-0001",  # noqa: E731
                            "wage_month": "2026-09", "postings": [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": 180000,
                                                                   "account_link_id": link, "share": "employee"}]}
    deliver("ContributionPosted.v1", posting("AL-0905"), "contribution-service")              # the old ID: nothing moves
    assert events(q, "AutoTransferConfirmed.v1") == []
    deliver("ContributionPosted.v1", posting("AL-0906"), "contribution-service")
    [event] = events(q, "AutoTransferConfirmed.v1")
    assert (event["from_account_link_id"], event["to_account_link_id"]) == ("AL-0905", "AL-0906")
    told = [n for n in events(q, "NotificationRequested.v1") if n["template"] == "AUTO_TRANSFER_STARTED"]
    assert told and told[0]["recipient_subject"] == MEMBER_G
    status = client.get("/api/v1/members/me/transfers/auto", headers=member(MEMBER_G)).json()["data"]
    assert status["eligible"] == [] and status["history"][0]["state"] == "CONFIRMED"
    deliver("ContributionPosted.v1", {**posting("AL-0906"), "journal_id": "J-2"}, "contribution-service")
    assert len(events(q, "AutoTransferConfirmed.v1")) == 1                                    # once
