"""Officer steps on a claim case as the CITES manuals set them (P2.5d): each officer generates the Claim Approval
Docket before acting, and every recommendation or decision is confirmed with a one-time code."""
from tests.e2e.test_journey_a_ecr import call, step_up, wait_for


def docket(page, case):
    status, r = call(page, "POST", f"/api/v1/office/claims/{case['claim_id']}/cad")
    assert status == 201, r
    return wait_for(lambda: (lambda d: d if d.get("docket_ready") else None)(
        call(page, "GET", f"/api/v1/office/cases/{case['case_id']}")[1]["data"]), timeout=30, every=1)


def recommend(page, case, note="Documents in order", recommendation="APPROVE", checks=("KYC verified",), reason_code=None):
    case = docket(page, case)
    return call(page, "POST", f"/api/v1/office/cases/{case['case_id']}/recommendations",
                {"checks": list(checks), "note": note, "recommendation": recommendation, "account_status": "OPERATIVE",
                 **({"reason_code": reason_code} if reason_code else {})},
                {"X-Step-Up-Token": step_up(page, "recommend-case", case["case_id"], case["version"])})


def decide(page, case, path="decisions", decision="APPROVE", reason=None):
    case = docket(page, case)
    return call(page, "POST", f"/api/v1/office/cases/{case['case_id']}/{path}", {"decision": decision, "reason": reason},
                {"X-Step-Up-Token": step_up(page, "decide-case", case["case_id"], case["version"], case["amount_paise"])})
