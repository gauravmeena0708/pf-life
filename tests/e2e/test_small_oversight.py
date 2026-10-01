"""Phase 2, slice 12d on the running stack: zonal internal audit raises a para on the regional office, the OIC answers
and asks for it to be dropped, the Audit Division drops it; a member asks about their personal data and the data
protection officer answers; the PRO registers an RTI application and replies; another office's officer cannot reach
any of it. Repeatable: every run raises its own para, request and application."""
import secrets
from datetime import date

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_internal_audit_para_answered_and_dropped(persona):
    auditor = persona("zo-internal-audit", "/audit/internal")
    tag = secrets.token_hex(3)
    status, report = call(auditor, "POST", "/api/v1/audit/internal/reports",
                          {"office_id": "RO-DEMO-01", "period_from": "2026-04-01", "period_to": "2026-09-30",
                           "scope": f"Claims settled and ledger adjustments, first half of 2026-27 ({tag})"})
    assert status == 201, report
    status, para = call(auditor, "POST", f"/api/v1/audit/internal/reports/{report['data']['report_id']}/paras",
                        {"category": "CLAIMS", "observation": f"Two claims approved without the bank verification note ({tag}).",
                         "amount_at_risk_paise": 5000000, "references": ["CLM-A", "CLM-B"], "recommendation": "Record the verification."})
    assert status == 201 and para["data"]["state"] == "OPEN", para
    pid = para["data"]["para_id"]
    oic = persona("ro-oic", "/audit/concurrent")
    assert any(p["para_id"] == pid for p in call(oic, "GET", "/api/v1/audit/internal/paras")[1]["data"])
    status, r = call(oic, "POST", f"/api/v1/audit/internal/paras/{pid}/replies",
                     {"reply": "The verification notes were found in the e-files and are now recorded.", "action_taken": "Recorded", "request_drop": True})
    assert status == 200 and r["data"]["state"] == "REPLIED", r
    audit_division = persona("auditor", "/audit/log")
    assert call(audit_division, "POST", f"/api/v1/audit/internal/paras/{pid}/decisions", {"decision": "DROP", "note": "Complied"})[0] == 428
    status, r = call(audit_division, "POST", f"/api/v1/audit/internal/paras/{pid}/decisions", {"decision": "DROP", "note": "Complied with"},
                     {"X-Step-Up-Token": step_up(audit_division, "decide-audit-para", pid)})
    assert status == 200 and r["data"]["state"] == "DROPPED", r
    assert call(persona("member-a", "/member"), "GET", "/api/v1/audit/internal/paras")[0] == 403


def test_data_principal_request_and_rti_application(persona):
    member = persona("member-a", "/member/security")
    status, r = call(member, "POST", "/api/v1/members/me/privacy-requests", {"kind": "ACCESS", "details": "Please send me the personal data you hold."})
    assert status == 201 and r["data"]["state"] == "OPEN", r
    rid = r["data"]["request_id"]
    dpo = persona("ho-dpo", "/privacy")
    assert any(x["request_id"] == rid for x in call(dpo, "GET", "/api/v1/privacy/requests")[1]["data"])
    token = step_up(dpo, "decide-privacy-request", rid)
    assert call(dpo, "POST", f"/api/v1/privacy/requests/{rid}/decisions", {"decision": "REJECTED", "answer": "Not possible to answer this request."},
                {"X-Step-Up-Token": token})[0] in (400, 422)                       # a refusal needs its legal basis
    status, r = call(dpo, "POST", f"/api/v1/privacy/requests/{rid}/decisions",
                     {"decision": "FULFILLED", "answer": "A copy of your profile, KYC and nomination records is attached (synthetic)."},
                     {"X-Step-Up-Token": step_up(dpo, "decide-privacy-request", rid)})
    assert status == 200, r
    mine = next(x for x in call(member, "GET", "/api/v1/members/me/privacy-requests")[1]["data"] if x["request_id"] == rid)
    assert mine["state"] == "FULFILLED"

    pro = persona("ro-pro", "/office/grievances")
    body = {"applicant_name": "Synthetic Applicant", "received_on": date.today().isoformat(), "mode": "RTI_PORTAL",
            "subject": "Claims pending beyond 20 days", "information_sought": "The number of claims pending beyond 20 days in each month of 2026.",
            "fee_paid": False, "bpl": False}
    assert call(pro, "POST", "/api/v1/office/rti-requests", body)[0] == 422                  # no fee and no BPL card
    status, r = call(pro, "POST", "/api/v1/office/rti-requests", {**body, "fee_paid": True})
    assert status == 201 and r["data"]["registration_no"].startswith("RTI/"), r
    rti = r["data"]["request_id"]
    assert call(pro, "POST", f"/api/v1/office/rti-requests/{rti}/replies", {"outcome": "REFUSED", "reply": "Refused under the Act (synthetic)."})[0] in (400, 422)
    status, r = call(pro, "POST", f"/api/v1/office/rti-requests/{rti}/replies",
                     {"outcome": "INFORMATION_PROVIDED", "reply": "The monthly counts are enclosed (synthetic, illustrative)."})
    assert status == 200 and r["data"]["late"] is False, r
    assert call(persona("ro-oic", "/office/work-queue"), "POST", "/api/v1/office/rti-requests", {**body, "fee_paid": True})[0] == 403
