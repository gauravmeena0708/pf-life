"""Phase 2, slice 7c on the running stack: a member who left with less than 9½ years of service takes the pension
withdrawal benefit (Form 10C, Table D) through the DA and SS and is paid from the EPS fund; member A reads the
annual statement and the taxable-interest split."""
import uuid
from pathlib import Path

import yaml

from tests.e2e.officers import decide, recommend
from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)
from tests.e2e.test_policy_money import publish_today


def _types(member):
    return {t["claim_type"]: t for a in call(member, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]
            for t in a["types"] if a["account_link_id"] == "AL-0006"}


def test_form_10c_withdrawal_benefit_is_paid(persona):
    member = persona("member-c", "/member/claims")
    if "PENSION_WITHDRAWAL" not in _types(member):   # a rule set published before the type existed is in force: publish it
        spec = yaml.safe_load(open(Path(__file__).resolve().parents[2] / "config" / "demo-rules.yaml"))["claims"]["types"]["PENSION_WITHDRAWAL"]
        publish_today(persona, lambda d: d["claims"]["types"].setdefault("PENSION_WITHDRAWAL", spec), "Form 10C pension withdrawal benefit")
        wait_for(lambda: "PENSION_WITHDRAWAL" in _types(member), timeout=30)
    w = _types(member)["PENSION_WITHDRAWAL"]
    if not w["eligible"]:                                                         # taken on an earlier run: once per member ID
        assert any("once every" in r for r in w["reasons"]), w
        return
    status, r = call(member, "POST", "/api/v1/members/me/claims", {"account_link_id": "AL-0006", "claim_type": "PENSION_WITHDRAWAL",
                                                                   "amount_paise": w["max_amount_paise"]}, {"Idempotency-Key": str(uuid.uuid4())})
    if status == 409 and r.get("type") == "/problems/claim-already-open":        # left by an earlier run
        claim = call(member, "GET", f"/api/v1/members/me/claims/{r['claim_id']}")[1]["data"]
    elif status == 422 and r.get("type") == "/problems/not-eligible":             # taken on an earlier run: once per member ID
        return
    else:
        assert status == 201, (r, w)
        c = r["data"]["confirmation"]
        status, r = call(member, "POST", f"/api/v1/members/me/claims/{c['resource_id']}/confirmations", None,
                         {"X-Step-Up-Token": step_up(member, c["action"], c["resource_id"], c["resource_version"], c["amount_paise"])})
        assert status == 200 and r["data"]["state"] == "UNDER_REVIEW", r
        claim = r["data"]
    cid = claim["claim_id"]

    def mine(page):
        return next((x for x in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"] if x["claim_id"] == cid), None)
    if claim["state"] == "UNDER_REVIEW":
        da = persona("do-caseworker", "/office/work-queue")
        case = wait_for(lambda: mine(da), timeout=30)
        assert recommend(da, case, "Service under 9½ years; Table D factor checked")[0] == 200
    if call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] in ("UNDER_REVIEW", "RECOMMENDED"):
        ss = persona("ro-ss", "/office/work-queue")
        case = wait_for(lambda: mine(ss), timeout=30)
        assert decide(ss, case, "decisions")[0] == 200
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] in ("APPROVED", "PAYMENT_PENDING", "SETTLED"), timeout=30)
    if call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] == "APPROVED":
        cashier = persona("ro-cashier", "/office/work-queue")
        wait_for(lambda: call(cashier, "POST", f"/api/v1/office/claims/{cid}/payment-instructions", {"demo_scenario": "SUCCESS"},
                              {"X-Step-Up-Token": step_up(cashier, "instruct-payment", cid, None, claim["amount_paise"]),
                               "Idempotency-Key": str(uuid.uuid4())})[0] == 200, timeout=30, every=2)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] == "SETTLED", timeout=30)


def test_annual_statement_and_taxable_interest(persona):
    member = persona("member-a", "/member/passbook")
    status, s = call(member, "GET", "/api/v1/members/me/annual-statements/2026-27")
    assert status == 200 and s["data"]["accounts"][0]["closing_total_paise"] > 0, s
    status, t = call(member, "GET", "/api/v1/members/me/tax/taxable-interest?financialYear=2025-26")
    assert status == 200 and t["data"]["illustrative"] is True, t
