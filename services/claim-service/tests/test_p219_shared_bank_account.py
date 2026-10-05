"""P2.19b: One bank account for many members.

When a claim's payee bank account (account number + IFSC, or bank_ifsc + bank_account_last4)
is already the payee of claims of N or more OTHER members (N=3, configurable), the claim is
held for office review with a clear reason (a known fraud pattern) instead of auto-settling;
an officer can clear the hold. Family members legitimately sharing (a nominee being paid for
several deceased members' claims) is allowed when the payee is the recorded nominee. Tests both ways.
"""
import asyncio
from datetime import datetime, UTC
from sqlalchemy import text
from tests.test_claims_api import CASHIER, MEMBER_A, MEMBER_B, S_APFC, SUBJECTS, ctx, events, hdr, member


def db_exec(sql, params=None):
    from app.infra.db import engine
    async def run():
        async with engine().begin() as conn:
            await conn.execute(text(sql), params or {})
    asyncio.run(run())


def test_shared_bank_account_held_for_office_review_and_cleared_by_officer(ctx):
    """When a payee bank account is shared with N=3 other members, claim is held for office review, then cleared."""
    client, q, deliver = ctx
    apfc = SUBJECTS["ro-apfc"]

    # Seed 3 other members' claims with the same bank account: IFSC="DEMO0000001", last4="7777"
    # Member subjects: subject-m1, subject-m2, subject-m3
    db_exec("""
        INSERT INTO claims (claim_id, member_subject, account_link_id, claim_type, form_type, amount_paise,
                            state, version, rule_version, office_id, evaluation, summary, payee_ifsc, payee_account_last4)
        VALUES
        ('CLM-M1', 'subject-m1', 'AL-0002', 'ADVANCE_ILLNESS', '31', 500000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Test 1', 'DEMO0000001', '7777'),
        ('CLM-M2', 'subject-m2', 'AL-0003', 'ADVANCE_ILLNESS', '31', 500000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Test 2', 'DEMO0000001', '7777'),
        ('CLM-M3', 'subject-m3', 'AL-0004', 'ADVANCE_ILLNESS', '31', 500000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Test 3', 'DEMO0000001', '7777')
    """)

    # Member A (subject-1) has UAN 100000000001. Add this shared bank account to member A's verified accounts with latest verified_at.
    now = datetime.now(UTC).isoformat()
    db_exec(f"INSERT INTO member_bank_accounts (uan, bank_ifsc, bank_account_last4, verified_at) VALUES ('100000000001', 'DEMO0000001', '7777', '{now}')")

    # Member A creates a claim within the auto-settle limit (e.g. 5,000 paise / ₹50)
    created = client.post("/api/v1/members/me/claims", json={
        "account_link_id": "AL-0001",
        "claim_type": "ADVANCE_ILLNESS",
        "amount_paise": 500000,
    }, headers=member(MEMBER_A)).json()["data"]
    claim_id = created["claim_id"]

    # Confirm claim - normally would auto-settle (<= auto limit of ₹1,00,000)
    c = created["confirmation"]
    conf_step = {"action": "confirm-claim", "resource_id": claim_id,
                 "resource_version": c["resource_version"], "amount_paise": 500000}
    confirmed = client.post(f"/api/v1/members/me/claims/{claim_id}/confirmations", headers=member(MEMBER_A, conf_step))
    assert confirmed.status_code == 200
    res_data = confirmed.json()["data"]

    # MUST NOT be AUTO_APPROVED; must be held for office review due to shared bank account fraud pattern
    assert res_data["state"] in ("ON_HOLD_OFFICE_REVIEW", "UNDER_REVIEW")
    assert res_data["state"] != "AUTO_APPROVED"
    timeline_notes = " ".join(t["note"] for t in res_data["timeline"])
    assert "fraud pattern" in timeline_notes or "shared" in timeline_notes.lower()

    # An officer clears the hold
    clear_res = client.post(f"/api/v1/office/claims/{claim_id}/clear-hold",
                            json={"note": "Verified member identity and bank account documentation; genuine claimant"},
                            headers=hdr(apfc, "fo.apfc"))
    assert clear_res.status_code == 200, clear_res.text
    cleared_claim = clear_res.json()["data"]
    # Once hold is cleared, the claim auto-settles (within auto-limit)
    assert cleared_claim["state"] == "AUTO_APPROVED"


def test_family_member_nominee_sharing_bank_account_is_allowed(ctx):
    """Nominee claiming death benefits for multiple deceased members sharing bank account is allowed."""
    client, q, deliver = ctx
    meena = SUBJECTS["claimant-b"]
    uan1 = "100000000916"   # VIJAY DEMO

    # Ensure 3 past claims already exist for meena's bank account (DEMO0000001, 8888) from other deceased members
    db_exec("""
        INSERT INTO claims (claim_id, member_subject, account_link_id, claim_type, form_type, amount_paise,
                            state, version, rule_version, office_id, evaluation, summary, payee_ifsc, payee_account_last4, death_of_uan)
        VALUES
        ('CLM-D1', 'claimant-b', 'AL-0910', 'DEATH_PF', '20', 5000000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Death 1', 'DEMO0000001', '8888', '100000000910'),
        ('CLM-D2', 'claimant-b', 'AL-0911', 'DEATH_PF', '20', 5000000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Death 2', 'DEMO0000001', '8888', '100000000911'),
        ('CLM-D3', 'claimant-b', 'AL-0912', 'DEATH_PF', '20', 5000000, 'SETTLED', 1, '2026.1', 'RO-DELHI-C', '{}', 'Death 3', 'DEMO0000001', '8888', '100000000912')
    """)

    # Mark death for VIJAY DEMO (uan1)
    deliver("MemberExitMarked.v1", {"uan": uan1, "account_link_id": "AL-0960", "date_of_exit": "2026-09-30",
                                    "reason": "DEATH_IN_SERVICE", "marked_by": "CIVIL_REGISTRY"}, "member-service")
    deliver("MemberDeathRecorded.v1", {"uan": uan1, "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY",
                                       "registration_no": "D-2026-DL-0001"}, "member-service")

    # Update nomination to specify the bank account
    db_exec("UPDATE nominations SET bank_ifsc='DEMO0000001', bank_account_last4='8888' WHERE uan='100000000916' AND subject='claimant-b'")

    # Meena files Form 20 death claim
    step = {"action": "file-death-claim", "resource_id": uan1}
    body = {
        "form_type": "FORM_20",
        "deceased_uan": uan1,
        "process_as": "E_NOMINATION",
    }
    r = client.post("/api/v1/claimants/death-claims", json=body, headers=hdr(meena, "claimant", step))
    assert r.status_code == 201, r.text
    claim = r.json()["data"]

    # Since payee is the recorded nominee for the deceased member, it is NOT held for fraud
    assert claim["state"] != "ON_HOLD_OFFICE_REVIEW"
    timeline_notes = " ".join(t["note"] for t in claim["timeline"])
    assert "fraud pattern" not in timeline_notes
