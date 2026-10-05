"""P2.19d: Minor nominee or no nomination on a death claim.

A minor nominee is paid through a guardian (the claim records the guardian; payment to the
guardian's account; the guardian must not be the deceased's employer); with no nomination
the amount goes to the family in equal shares (EPF Scheme para 70). Tests.
"""
from tests.test_claims_api import CASHIER, MEMBER_A, S_APFC, SUBJECTS, ctx, events, hdr, member

CLAIMANT = SUBJECTS["claimant-a"]
UAN = "100000000901"
BALANCE = 40000000


def claimant(step_up=None):
    return hdr(CLAIMANT, "claimant", step_up)


def test_minor_nominee_paid_through_guardian_and_employer_forbidden(ctx):
    """A minor nominee records guardian; payment to guardian account; employer cannot be guardian."""
    client, q, deliver = ctx

    # 1. Employer as guardian must be rejected (EPF Scheme para 70 / 72)
    step = {"action": "file-death-claim", "resource_id": UAN}
    employer_as_guardian = {
        "form_type": "FORM_20",
        "deceased_uan": UAN,
        "process_as": "NEW_BENEFICIARIES",
        "beneficiaries": [
            {
                "name": "BABY DEMO",
                "relation": "DAUGHTER",
                "share_bp": 10000,
                "minor": True,
                "guardian_name": "EST-0001",   # Deceased's employer establishment
                "bank_account_last4": "9999",
            }
        ]
    }
    bad = client.post("/api/v1/claimants/death-claims", json=employer_as_guardian, headers=claimant(step))
    assert bad.status_code == 422, bad.text
    assert bad.json()["type"] == "/problems/employer-cannot-be-guardian" or "employer" in bad.json()["detail"].lower()

    # 2. Legitimate guardian is accepted, guardian recorded, payment to guardian's account
    legitimate = {
        "form_type": "FORM_20",
        "deceased_uan": UAN,
        "process_as": "NEW_BENEFICIARIES",
        "beneficiaries": [
            {
                "name": "BABY DEMO",
                "relation": "DAUGHTER",
                "share_bp": 10000,
                "minor": True,
                "guardian_name": "SARITA DEMO",
                "bank_account_last4": "5678",   # Guardian's bank account
            }
        ]
    }
    r = client.post("/api/v1/claimants/death-claims", json=legitimate, headers=claimant(step))
    assert r.status_code == 201, r.text
    claim = r.json()["data"]
    b = claim["beneficiaries"][0]
    assert b["minor"] is True
    assert b["guardian_name"] == "SARITA DEMO"
    assert b["bank_account_last4"] == "5678"


def test_no_nomination_distributed_in_equal_shares_under_epf_scheme_para_70(ctx):
    """When no nomination exists, amount goes to family members in equal shares (EPF Scheme para 70)."""
    client, q, deliver = ctx
    uan_no_nom = "100000000001"   # Member A has no nominations in synthetic seed (only member 901/916 have)

    # Mark death for Member A
    deliver("MemberExitMarked.v1", {"uan": uan_no_nom, "account_link_id": "AL-0001", "date_of_exit": "2026-09-30",
                                    "reason": "DEATH_IN_SERVICE", "marked_by": "CIVIL_REGISTRY"}, "member-service")
    deliver("MemberDeathRecorded.v1", {"uan": uan_no_nom, "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY",
                                       "registration_no": "D-2026-DL-0050"}, "member-service")

    # Family members (SPOUSE, SON, DAUGHTER) file death claim with no nomination
    step = {"action": "file-death-claim", "resource_id": uan_no_nom}
    body = {
        "form_type": "FORM_20",
        "deceased_uan": uan_no_nom,
        "process_as": "NEW_BENEFICIARIES",
        "beneficiaries": [
            {"name": "ANITA SHARMA", "relation": "SPOUSE", "bank_account_last4": "1111"},
            {"name": "ROHIT SHARMA", "relation": "SON", "bank_account_last4": "2222"},
            {"name": "POOJA SHARMA", "relation": "DAUGHTER", "bank_account_last4": "3333"},
        ]
    }
    r = client.post("/api/v1/claimants/death-claims", json=body, headers=claimant(step))
    assert r.status_code == 201, r.text
    claim = r.json()["data"]

    # Under EPF Scheme para 70, 3 family members receive equal shares totaling 100% (10,000 bp)
    beneficiaries = claim["beneficiaries"]
    assert len(beneficiaries) == 3
    shares = [b["share_pct"] for b in beneficiaries]
    # 33.34% + 33.33% + 33.33% = 100.0%
    assert sum(shares) == 100.0
    assert abs(shares[0] - 33.34) < 0.01
    assert abs(shares[1] - 33.33) < 0.01
    assert abs(shares[2] - 33.33) < 0.01
