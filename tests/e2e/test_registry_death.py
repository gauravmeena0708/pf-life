"""P2.21b on the running stack: the civil registry (mock, its own machine login) reports VIJAY DEMO's death; his member ID
closes without the employer; his wife and nominee MEENA DEMO (claimant-b) sees the PF and EDLI claims worked out and files
them in one go, then the family pension; the PRO sees the record, and one that matched nobody. A member's e-UAN card
reaches DigiLocker (mock); the Concurrent Audit Cell's extract counts the claims settled automatically and samples them.
Repeatable: a later run finds the death already recorded and the claims filed, and checks the same outcome."""
import importlib.util
import secrets
from pathlib import Path

from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

UAN = "100000000916"
_spec = importlib.util.spec_from_file_location("crs_death_feed", Path(__file__).resolve().parents[2] / "scripts" / "crs_death_feed.py")
crs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crs)


def test_registry_death_reaches_the_nominee_worked_out(persona):
    number = f"D-2026-DL-{secrets.token_hex(4).upper()}"
    status, r = crs.report(number, "VIJAY DEMO", "1982-11-11", "2026-09-30", "DEMO-AADHAAR-100000000916")
    assert status == 201 and r["data"]["matched_uan"] == UAN and r["data"]["outcome"] in ("RECORDED", "ALREADY_RECORDED"), r
    assert crs.report(number, "VIJAY DEMO", "1982-11-11", "2026-09-30", "DEMO-AADHAAR-100000000916")[0] == 200     # sent twice: once
    nobody = f"D-2026-DL-{secrets.token_hex(4).upper()}"
    status, r = crs.report(nobody, "NOBODY DEMO", "1950-01-01", "2026-09-01", None)
    assert status == 201 and r["data"]["outcome"] == "NOT_A_MEMBER", r

    meena = persona("claimant-b", "/claimant")
    offers = lambda: [o for o in call(meena, "GET", "/api/v1/claimants/me/death-claim-offers")[1]["data"] if o["deceased_uan"] == UAN]  # noqa: E731
    [offer] = wait_for(offers, timeout=30)                                   # claim-service learns the death from the event
    assert offer["deceased_name"] == "VIJAY DEMO" and offer["relation"] == "SPOUSE" and offer["forms"][0]["amount_paise"] > 0, offer
    if offer["open"]:
        form = "CCF_DEATH" if len(offer["open"]) == 2 else offer["open"][0]
        status, r = call(meena, "POST", "/api/v1/claimants/death-claims", {"form_type": form, "deceased_uan": UAN},
                         {"X-Step-Up-Token": step_up(meena, "file-death-claim", UAN)})
        assert status == 201, r
    [offer] = offers()
    assert offer["open"] == [] and all(f["filed_claim_id"] for f in offer["forms"]), offer

    def family_pension():
        status, r = call(meena, "POST", "/api/v1/claimants/family-pension-applications", {"form_type": "FORM_10D", "deceased_uan": UAN},
                         {"X-Step-Up-Token": step_up(meena, "file-family-pension", UAN)})
        return (status, r) if status in (201, 409) else None               # 422 until pension-service has the death
    status, r = wait_for(family_pension, timeout=30, every=2)
    assert status == 409 or r["data"]["pension_from"] == "2026-10-01", r

    pro = persona("ro-pro", "/office/registry-deaths")
    seen = {x["registration_no"]: x for x in call(pro, "GET", "/api/v1/office/civil-registry/deaths")[1]["data"]}
    assert seen[number]["matched_uan"] == UAN and seen[nobody]["outcome"] == "NOT_A_MEMBER"


def test_e_uan_card_reaches_digilocker_and_the_audit_samples_automatic_settlements(persona):
    member = persona("member-a", "/member")
    status, r = call(member, "POST", "/api/v1/members/me/digilocker-documents", {"doc_type": "UAN_CARD"})
    assert status == 202, r
    issued = lambda: next((d for d in call(member, "GET", "/api/v1/members/me/digilocker-documents")[1]["data"]  # noqa: E731
                           if d["doc_type"] == "UAN_CARD" and d["state"] == "ISSUED"), None)
    card = wait_for(issued, timeout=30)
    assert card["uri"].startswith("in.gov.epfindia.demo-UAN_CARD-"), card

    auditor = persona("zo-audit", "/audit/concurrent")
    status, r = call(auditor, "GET", "/api/v1/audit/concurrent/extracts")
    assert status == 200 and r["data"]["auto_settlements"]["one_in"] >= 1, r
    sampled = [i for i in r["data"]["items"] if "AUTO_SETTLEMENT_SAMPLE" in i["flags"]]
    assert len(sampled) == r["data"]["auto_settlements"]["sampled"] <= r["data"]["auto_settlements"]["settled"]
