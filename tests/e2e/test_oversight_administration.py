"""Phase 2, slice 8e on the running stack: a security incident reported to CERT-In (mock); the Concurrent Audit Cell's
daily extract, an alert to the regional office and the OIC's reply; an Issue Tracker freeze, de-freeze and login
notice executed by the IS Division; the zone's fraud-risk case list; HR re-posting an officer and back; the
district and employer dashboards; a member's location mapping. Repeatable."""
import secrets
from datetime import UTC, datetime, timedelta

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_security_incident_and_concurrent_audit(persona):
    analyst = persona("security-analyst", "/security")
    detected = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    body = {"title": "Credential stuffing against the member login", "category": "UNAUTHORISED_ACCESS", "severity": "HIGH",
            "detected_at": detected, "description": "Many failed logins from one address range against synthetic accounts.",
            "affected_systems": ["gateway"], "related_event_ids": []}
    status, r = call(analyst, "POST", "/api/v1/security/incidents", body,
                     {"X-Step-Up-Token": step_up(analyst, "record-security-incident", "UNAUTHORISED_ACCESS:HIGH")})
    assert status == 201 and r["data"]["cert_in"]["required"] and r["data"]["cert_in"]["acknowledgement"], r
    assert any(i["incident_id"] == r["data"]["incident_id"] for i in call(analyst, "GET", "/api/v1/security/incidents")[1]["data"])

    cell = persona("zo-audit", "/audit/concurrent")
    extract = call(cell, "GET", "/api/v1/audit/concurrent/extracts")[1]["data"]
    assert extract["events_scanned"] >= 0 and isinstance(extract["items"], list)
    item = extract["items"][0] if extract["items"] else {"reference": "MANUAL-CHECK", "event_id": None, "flags": []}
    status, alert = call(cell, "POST", "/api/v1/audit/concurrent/alerts", {
        "office_id": "RO-DEMO-01", "reference": item["reference"] or "MANUAL-CHECK", "event_id": item["event_id"],
        "flags": item["flags"], "finding": "Please confirm the approval was checked against the documents."})
    assert status == 201 and alert["data"]["state"] == "OPEN", alert
    oic = persona("ro-oic", "/office/work-queue")
    assert any(a["alert_id"] == alert["data"]["alert_id"] for a in call(oic, "GET", "/api/v1/audit/concurrent/alerts")[1]["data"])
    status, r = call(oic, "POST", f"/api/v1/audit/concurrent/alerts/{alert['data']['alert_id']}/replies",
                     {"reply": "Checked with the dealing assistant; the documents were on file.", "action_taken": "No action needed"})
    assert status == 200 and r["data"]["state"] == "REPLIED" and r["data"]["reply"]["late"] is False, r


def test_issue_tracker_freeze_defreeze_and_login_notice(persona):
    oic = persona("ro-oic", "/office/work-queue")
    isd = persona("ndc-is", "/ndc/issue-tracker")
    uan = "100000000909"                                       # LALIT DEMO: no login, used by no other flow

    def raise_and_execute(kind, **extra):
        status, r = call(oic, "POST", "/api/v1/ndc/issue-tracker/requests", {
            "kind": kind, "target_uan": extra.pop("uan", uan), "order_ref": f"DEMO/ORDER/{secrets.token_hex(3).upper()}",
            "reason": "Order of the competent authority (synthetic)", **extra})
        assert status == 201 and r["data"]["state"] == "RAISED", r
        rid = r["data"]["request_id"]
        status, r = call(isd, "POST", f"/api/v1/ndc/issue-tracker/requests/{rid}/executions", {"decision": "EXECUTE", "note": "Done as ordered"},
                         {"X-Step-Up-Token": step_up(isd, "execute-issue-tracker", rid)})
        assert status == 200 and r["data"]["state"] == "EXECUTED", r
        return rid

    zo = persona("zo-fraud", "/zo/fraud-risk")
    raise_and_execute("FREEZE_MEMBER")
    da = persona("do-caseworker", "/office/work-queue")
    state = lambda: call(da, "GET", f"/api/v1/office/members/{uan}?purpose=Checking+the+Issue+Tracker+order")[1]["data"]["account_state"]  # noqa: E731
    wait_for(lambda: state() == "FROZEN", timeout=30)
    raise_and_execute("DEFREEZE_MEMBER")
    wait_for(lambda: state() == "ACTIVE", timeout=30)
    notice = f"Please update your KYC at the regional office ({secrets.token_hex(2)})."
    rid = raise_and_execute("LOGIN_NOTICE", uan="100000000001", notice=notice)
    member = persona("member-a", "/member")
    wait_for(lambda: any(rid in str(n) for n in call(member, "GET", "/api/v1/members/me/notifications")[1]["data"]), timeout=30)
    cases = call(zo, "GET", "/api/v1/zo/fraud-risk/cases")[1]["data"]
    assert cases["zone_id"] == "ZO-DEMO-01" and isinstance(cases["cases"], list)


def test_hr_posting_moves_an_officer_and_back(persona):
    hr = persona("hrm-employee", "/hrm")

    def post(office):
        status, r = call(hr, "POST", "/api/v1/hrm/postings", {"username": "ro-pro-counter", "stakeholder": "fo.pro_intake",
                                                              "office_id": office, "reason": "Temporary deployment (synthetic)"},
                         {"X-Step-Up-Token": step_up(hr, "post-staff", "ro-pro-counter")})
        assert status == 200 and r["data"]["office_id"] == office, r
        return r["data"]["previous"]
    assert post("RO-DEMO-02")["office_id"] == "RO-DEMO-01"
    assert post("RO-DEMO-01")["office_id"] == "RO-DEMO-02"          # and back, so other tests find the officer at home


def test_dashboards_and_location_mapping(persona):
    do = persona("do-oic", "/do/dashboard")
    status, d = call(do, "GET", "/api/v1/do/dashboards")
    assert status == 200 and d["data"]["office_id"] == "RO-DEMO-01" and "claims" in d["data"] and "grievances" in d["data"], d
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    operator = persona("emp-preparer", "/employer/members")                    # operator of EST-DEMO-0001
    status, e = call(operator, "GET", "/api/v1/employers/me/dashboard")
    assert status == 200 and e["data"]["establishment_id"] == "EST-DEMO-0001" and isinstance(e["data"]["alerts"], list), e
    status, r = call(operator, "POST", "/api/v1/employers/me/members/100000000001/location-mappings",
                     {"account_link_id": "AL-0001", "branch_code": "BR-01", "district": "Central Delhi", "pincode": "110001"})
    assert status == 200 and r["data"]["location"]["district"] == "CENTRAL DELHI", r
    listed = next(m for m in call(operator, "GET", "/api/v1/employers/me/members")[1]["data"] if m["account_link_id"] == "AL-0001")
    assert listed["location"]["branch_code"] == "BR-01"
