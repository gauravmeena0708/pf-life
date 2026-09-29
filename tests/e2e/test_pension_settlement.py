"""Phase 2, slice 4 on the running stack: a retired member's Form 10D goes desk by desk to a PPO in payment, then
CPPS disburses a month, reconciles it with the (mock) sponsor bank, and the APFC (Pension) prepares the BRS.

Member E (synthetic) retired on 31 January 2026. DA (Accounts) prepares the Input Data Sheet, the AO approves it,
the DA (Pension) generates the worksheet under the formula in force, the APFC (Pension) approves it, the DA (Pension)
issues the PPO and proposes the initial arrear, the SS (Pension) checks it, the APFC (Pension) e-signs the PPO and
the DA (Pension) dispatches it. A rerun continues from the claim's current state."""
from datetime import UTC, datetime

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def ok(r, state=None):
    status, body = r
    assert status in (200, 201), body
    if state:
        assert body["data"]["state"] == state, body
    return body["data"]


def test_form_10d_to_a_pension_in_payment(persona):
    member = persona("member-e", "/member/pension")
    mine = call(member, "GET", "/api/v1/members/me/pension-applications")[1]["data"]
    c = mine[0] if mine else ok(call(member, "POST", "/api/v1/members/me/pension-applications", {}), "SUBMITTED")
    cid = c["claim_id"]
    desks = {name: persona(name, "/office/pension-claims") for name in ("do-caseworker", "ro-ao", "ro-da-pension", "ro-pension", "ro-ss-pension")}
    da, ao, dap, apfc, ssp = (desks[n] for n in ("do-caseworker", "ro-ao", "ro-da-pension", "ro-pension", "ro-ss-pension"))
    if c["state"] == "SUBMITTED":
        c = ok(call(da, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets",
                    {"service_months": c["service_months"], "pensionable_salary_paise": c["pensionable_salary_paise"],
                     "note": "Service and wages checked with the ledger"}), "IDS_PREPARED")
    if c["state"] == "IDS_PREPARED":
        ids = c["ids"]["ids_id"]
        c = ok(call(ao, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets/{ids}/approvals", {"decision": "APPROVE", "note": "IDS in order"},
                    {"X-Step-Up-Token": step_up(ao, "approve-ids", ids)}), "IDS_APPROVED")
    if c["state"] == "IDS_APPROVED":
        c = ok(call(dap, "POST", "/api/v1/office/pensions/worksheets", {"claim_id": cid}), "WORKSHEET_PREPARED")
    if c["state"] == "WORKSHEET_PREPARED":
        ws = c["worksheet"]["worksheet_id"]
        c = ok(call(apfc, "POST", f"/api/v1/office/pensions/worksheets/{ws}/approvals", {"decision": "APPROVE", "note": "Worksheet checked"},
                    {"X-Step-Up-Token": step_up(apfc, "approve-worksheet", ws)}), "WORKSHEET_APPROVED")
    if c["state"] == "WORKSHEET_APPROVED":
        c = ok(call(dap, "POST", "/api/v1/office/pensions/ppo-issuances", {"claim_id": cid}, {"X-Step-Up-Token": step_up(dap, "issue-ppo", cid)}), "PPO_ISSUED")
    ppo = c["ppo_id"]
    if c["state"] == "PPO_ISSUED":
        c = ok(call(dap, "POST", f"/api/v1/office/pensions/ppos/{ppo}/initial-arrears", {"action": "PROPOSE", "note": "Initial arrear proposed"}), "ARREAR_PROPOSED")
    if c["state"] == "ARREAR_PROPOSED":
        c = ok(call(ssp, "POST", f"/api/v1/office/pensions/ppos/{ppo}/initial-arrears", {"action": "CHECK", "note": "Arrear checked"}), "ARREAR_CHECKED")
    if c["state"] == "ARREAR_CHECKED":
        c = ok(call(apfc, "POST", f"/api/v1/office/pensions/ppos/{ppo}/e-signatures", {"decision": "APPROVE", "note": "PPO e-signed"},
                    {"X-Step-Up-Token": step_up(apfc, "esign-ppo", ppo, None, c["arrears"]["amount_paise"])}), "PPO_SIGNED")
    if c["state"] == "PPO_SIGNED":
        c = ok(call(dap, "POST", f"/api/v1/office/pensions/ppos/{ppo}/dispatches"), "DISPATCHED")
    assert c["state"] == "DISPATCHED"
    enquiry = call(dap, "GET", f"/api/v1/office/pensions/enquiries?ppo={ppo}")[1]["data"]
    assert enquiry["ppo_details"]["status"] == "IN_PAYMENT" and enquiry["ppo_details"]["monthly_paise"] == c["worksheet"]["monthly_paise"]
    assert len([p for p in enquiry["pension_payment_details"] if p["kind"] == "MONTHLY"]) >= len(c["arrears"]["months"])
    SHOTS.mkdir(exist_ok=True)
    member.goto(f"{WEB}/member/pension")
    member.get_by_role("heading", name="Monthly pension (Form 10D)").wait_for()
    member.screenshot(path=str(SHOTS / "p2-form10d-member.png"), full_page=True)
    dap.goto(f"{WEB}/office/pension-claims")
    dap.get_by_role("heading", name="Pension claims", exact=True).wait_for()
    dap.screenshot(path=str(SHOTS / "p2-pension-claims.png"), full_page=True)


def test_cpps_run_reconciliation_and_brs(persona):
    cpps, apfc = persona("ndc-cpps", "/cpps"), persona("ro-pension", "/cpps")
    today = datetime.now(UTC).date()
    month = f"{today.year - (today.month == 1)}-{(today.month - 2) % 12 + 1:02d}"      # the last completed month
    status, r = call(cpps, "POST", "/api/v1/cpps/disbursement-runs", {"month": month}, {"X-Step-Up-Token": step_up(cpps, "run-disbursement", month)})
    assert status in (201, 409), r                                                     # 409: already run on an earlier pass
    run = next(x for x in call(cpps, "GET", "/api/v1/cpps/disbursement-runs")[1]["data"] if x["month"] == month)
    assert run["pensions"] >= 2 and run["total_paise"] > 0
    if run["state"] != "RECONCILED":
        run = ok(call(cpps, "POST", "/api/v1/cpps/reconciliations", {"run_id": run["run_id"]},
                      {"X-Step-Up-Token": step_up(cpps, "reconcile-disbursement", run["run_id"])}), "RECONCILED")
    brs = ok(call(apfc, "POST", "/api/v1/office/pensions/brs-reconciliations", {"month": month}, {"X-Step-Up-Token": step_up(apfc, "prepare-brs", month)}))
    assert brs["scroll_total_paise"] - brs["bank_debit_total_paise"] == brs["difference_paise"]
    cpps.goto(f"{WEB}/cpps")
    cpps.get_by_role("heading", name="Monthly disbursement runs").wait_for()
    cpps.screenshot(path=str(SHOTS / "p2-cpps.png"), full_page=True)
