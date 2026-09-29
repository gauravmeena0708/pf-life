"""Phase 2, slice 5b on the running stack: a nominee files the PF (Form 20) claim on a member's death; the APFC
records a share already settled earlier; the officers approve and the cash section pays it in the beneficiaries'
shares; the EDLI claim (Form 5IF) is worked out from the rules; the PRO counter inwards a paper updation that
lands on the pension office's tracker and matches a filer with the member record."""
import uuid

from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.officers import recommend
from tests.e2e.test_journey_b_claim import case_for, decide
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

UAN = "100000000901"


def file(claimant, form):
    status, r = call(claimant, "POST", "/api/v1/claimants/death-claims", {"form_type": form, "deceased_uan": UAN},
                     {"X-Step-Up-Token": step_up(claimant, "file-death-claim", UAN)})
    if status == 409 and r.get("type") == "/problems/claim-already-open":        # filed on an earlier run: carry on with it
        return call(claimant, "GET", f"/api/v1/claimants/death-claims/{r['claim_id']}")[1]["data"]
    assert status == 201, r
    return r["data"]


def test_nominee_claims_pf_and_edli_and_is_paid_in_shares(persona):
    claimant = persona("claimant-a", "/claimant")
    c = file(claimant, "FORM_20")
    assert c["claim_type"] == "DEATH_PF" and [b["name"] for b in c["beneficiaries"]][:2] == ["LAKSHMI DEMO", "ARJUN DEMO"]
    claim_id = c["claim_id"]
    apfc = persona("ro-apfc", "/office/claim-tools")
    if c["state"] == "UNDER_REVIEW":
        son = c["beneficiaries"][1]["beneficiary_id"]
        status, r = call(apfc, "PUT", f"/api/v1/office/death-claims/{claim_id}/beneficiaries/{son}/shares",
                         {"share_bp": 4000, "legacy_settled_paise": 100000, "reason": "LEGACY_SETTLEMENT_OFFSET", "note": "₹1,000 paid in the legacy system"},
                         {"X-Step-Up-Token": step_up(apfc, "amend-share", son)})
        assert status == 200 and r["data"]["payable"], r
        da = persona("do-caseworker", "/office/work-queue")
        case = wait_for(lambda: case_for(da, claim_id))
        status, r = recommend(da, case, "Nominee's claim", checks=("Death certificate seen", "Nomination on record"))
        assert status == 200, r
        ao = persona("ro-ao", "/office/work-queue")
        case = wait_for(lambda: case_for(ao, claim_id))
        status, r = decide(ao, case, "decisions", reason="Nomination in order")
        assert status == 200, r
    track = lambda: call(claimant, "GET", f"/api/v1/claimants/death-claims/{claim_id}")[1]["data"]  # noqa: E731
    if track()["state"] != "SETTLED":
        wait_for(lambda: track()["state"] == "APPROVED", timeout=30)
        cashier = persona("ro-cashier", "/office/work-queue")
        status, paid = wait_for(lambda: (lambda r: r if r[0] == 200 else None)(call(
            cashier, "POST", f"/api/v1/office/claims/{claim_id}/payment-instructions", {"demo_scenario": "SUCCESS"},
            {"X-Step-Up-Token": step_up(cashier, "instruct-payment", claim_id, None, c["amount_paise"]), "Idempotency-Key": str(uuid.uuid4())})),
            timeout=30, every=2)
        wait_for(lambda: track()["state"] == "SETTLED", timeout=30)
    summary = call(apfc, "GET", f"/api/v1/office/death-claims/{claim_id}/shares-summary")[1]["data"]
    assert summary["state"] == "SETTLED" and summary["totals"]["pending_paise"] == 0, summary
    assert summary["beneficiaries"][1]["legacy_settled_paise"] == 100000

    edli = file(claimant, "FORM_5IF")
    assert edli["claim_type"] == "DEATH_EDLI" and edli["amount_paise"] >= 25000000 and "EDLI" in edli["summary"]


def test_pro_counter_inwards_a_paper_updation_and_checks_identity(persona):
    pro = persona("ro-pro-counter", "/office/pro-counter")
    status, r = call(pro, "POST", "/api/v1/office/physical-claims", {"form_type": "PHYSICAL_LC_UPDATION", "uan": "100000000001",
                                                                      "ppo_id": "PPO-DEMO-0001", "filed_by": "PENSIONER", "details": {"remarks": "Signed by bank manager"}})
    assert status == 201 and r["data"]["state"] == "ROUTED", r
    intake_id = r["data"]["intake_id"]
    da_p = persona("ro-da-pension", "/office/pensions")
    wait_for(lambda: any(a["details"].get("intake_id") == intake_id for a in call(
        da_p, "GET", "/api/v1/office/pensions/updation-activities?status=NEW")[1]["data"]), timeout=30)
    status, r = call(pro, "POST", "/api/v1/office/physical-claims", {"form_type": "FORM_19", "uan": "100000000002", "filed_by": "MEMBER"})
    assert status == 201 and r["data"]["state"] == "INWARDED", r
    status, v = call(pro, "POST", f"/api/v1/office/physical-claims/{r['data']['intake_id']}/identity-validations",
                     {"uan": "100000000002", "name": "BHARAT DEMO", "date_of_birth": "1985-11-02", "evidence": "AADHAAR_OTP"})
    assert status == 201 and v["data"]["result"] == "MATCHED", v
