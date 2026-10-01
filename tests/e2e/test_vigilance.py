"""Phase 2, slice 10a on the running stack: a staff complaint referred to vigilance by the CAIU; the CVO assigns a
preliminary inquiry to the zone; zonal vigilance sees the case with the complainant masked and reports findings; the
CVO orders minor penalty proceedings. A signal the CAIU found benign cannot be referred; other roles cannot read cases.
Repeatable: every run opens a new case."""
import secrets

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_vigilance_case_from_referral_to_decision(persona):
    caiu = persona("caiu-investigator", "/caiu/signals")
    tag = secrets.token_hex(3)
    status, r = call(caiu, "POST", "/api/v1/vigilance/referrals", {
        "source": "STAFF_COMPLAINT", "subject_type": "OFFICIAL", "subject_ref": "ro-da-accounts", "office_id": "RO-DEMO-01",
        "allegation": f"Claims approved without the bank verification the manual requires (synthetic {tag}).",
        "evidence": [{"kind": "OFFICE_CASE", "ref": f"CASE-{tag}"}], "complainant": {"name": "A Colleague", "contact": "desk 4"}})
    assert status == 201 and r["data"]["vcn"].startswith("VIG/"), r
    case_id = r["data"]["case_id"]
    benign = [s for s in call(caiu, "GET", "/api/v1/caiu/synthetic-risk-signals")[1]["data"]["signals"] if s["status"] == "BENIGN"]
    if benign:                                                                        # left by Journey D
        status, r = call(caiu, "POST", "/api/v1/vigilance/referrals", {
            "source": "CAIU_SIGNAL", "source_ref": benign[0]["signal_id"], "subject_type": "MEMBER", "subject_ref": benign[0]["subject_ref"],
            "office_id": "RO-DEMO-01", "allegation": "A benign signal must not become a vigilance case (synthetic)."})
        assert status == 409 and r["type"] == "/problems/signal-not-confirmed", r
    assert call(caiu, "GET", f"/api/v1/vigilance/cases/{case_id}")[0] == 403

    cvo = persona("vigilance-investigator", "/vigilance")
    assert call(cvo, "GET", f"/api/v1/vigilance/cases/{case_id}")[1]["data"]["complainant"]["name"] == "A Colleague"

    def decide(decision, note):
        return call(cvo, "POST", f"/api/v1/vigilance/cases/{case_id}/decisions", {"decision": decision, "note": note},
                    {"X-Step-Up-Token": step_up(cvo, "decide-vigilance-case", case_id)})
    status, r = decide("ASSIGN_INQUIRY", "Preliminary inquiry by the zone")
    assert status == 200 and r["data"]["state"] == "PI_ASSIGNED" and r["data"]["zone_id"] == "ZO-DEMO-01", r

    zone = persona("zo-vigilance", "/vigilance")
    assert any(c["case_id"] == case_id for c in call(zone, "GET", "/api/v1/vigilance/cases")[1]["data"]["cases"])
    seen = call(zone, "GET", f"/api/v1/vigilance/cases/{case_id}")[1]["data"]
    assert seen["complainant"] == {"masked": True} and seen["evidence"] == [{"kind": "OFFICE_CASE", "ref": f"CASE-{tag}"}]
    status, r = call(zone, "POST", f"/api/v1/vigilance/cases/{case_id}/findings", {
        "finding": "PARTLY_SUBSTANTIATED", "recommendation": "Minor penalty proceedings and a system check.",
        "report": "The approvals were made without the bank verification; no gain to the official was found (synthetic).",
        "evidence_examined": [f"CASE-{tag}"]}, {"X-Step-Up-Token": step_up(zone, "report-vigilance-findings", case_id)})
    assert status == 200 and r["data"]["state"] == "PI_REPORTED" and r["data"]["late"] is False, r

    status, r = decide("MINOR_PENALTY_PROCEEDINGS", "Accepting the zone's recommendation")
    assert status == 200 and r["data"]["state"] == "ACTION_ORDERED", r
    history = [h["action"] for h in call(cvo, "GET", f"/api/v1/vigilance/cases/{case_id}")[1]["data"]["history"]]
    assert history == ["REFERRED", "ASSIGN_INQUIRY", "FINDINGS_REPORTED", "MINOR_PENALTY_PROCEEDINGS"]

    cvo.goto(cvo.url.split("/vigilance")[0] + f"/vigilance?case={case_id}")
    cvo.get_by_role("heading", name="Vigilance cases").wait_for()
    cvo.get_by_text(r["data"]["vcn"]).first.wait_for()


def test_other_roles_cannot_read_vigilance_cases(persona):
    for name, landing in (("ro-oic", "/office/work-queue"), ("zo-fraud", "/zo/fraud-risk"), ("member-a", "/member")):
        page = persona(name, landing)
        assert call(page, "GET", "/api/v1/vigilance/cases")[0] == 403, name


def test_sensitive_posts_clearance_and_posting(persona):
    """P2.10b: rotation of sensitive posts; clearance withheld while a case names the officer and given once it is
    closed; a posting to a sensitive post only with a current clearance. Repeatable: the case is closed and the
    officer posted back."""
    hr = persona("hrm-employee", "/i/hrm")
    posts = call(hr, "GET", "/api/v1/vigilance/sensitive-posts")[1]["data"]
    cashier = next(o for o in posts["officers"] if o["username"] == "ro-cashier")
    assert cashier["rotation"] in ("ROTATION_DUE", "ROTATION_OVERDUE") and "ro-cashier" in posts["transfer_list"]

    cvo = persona("vigilance-investigator", "/vigilance")
    close_leftovers(persona, cvo, "ro-fa-accounts")
    caiu = persona("caiu-investigator", "/caiu/signals")
    status, r = call(caiu, "POST", "/api/v1/vigilance/referrals", {
        "source": "STAFF_COMPLAINT", "subject_type": "OFFICIAL", "subject_ref": "ro-fa-accounts", "office_id": "RO-DEMO-01",
        "allegation": f"Ledger postings made without the second check (synthetic {secrets.token_hex(3)})."})
    case_id = r["data"]["case_id"]
    status, r = call(hr, "POST", "/api/v1/vigilance/clearances", {"username": "ro-fa-accounts", "purpose": "PROMOTION"})
    assert status == 201 and r["data"]["cleared"] is False and "case_ids" not in r["data"], r
    assert case_id in next(c for c in call(cvo, "GET", "/api/v1/vigilance/clearances")[1]["data"]["clearances"]
                           if c["clearance_id"] == r["data"]["clearance_id"])["case_ids"]
    call(cvo, "POST", f"/api/v1/vigilance/cases/{case_id}/decisions", {"decision": "CLOSED_NO_SUBSTANCE", "note": "No substance in it"},
         {"X-Step-Up-Token": step_up(cvo, "decide-vigilance-case", case_id)})
    assert call(hr, "POST", "/api/v1/vigilance/clearances", {"username": "ro-fa-accounts", "purpose": "PROMOTION"})[1]["data"]["cleared"] is True

    def post(stakeholder):
        return call(hr, "POST", "/api/v1/hrm/postings", {"username": "ro-pro-counter", "stakeholder": stakeholder, "office_id": "RO-DEMO-01",
                                                         "reason": "Rotation of the cash section (synthetic)"},
                    {"X-Step-Up-Token": step_up(hr, "post-staff", "ro-pro-counter")})
    call(hr, "POST", "/api/v1/vigilance/clearances", {"username": "ro-pro-counter", "purpose": "POSTING_SENSITIVE"})
    status, r = post("fo.cash")
    assert status == 200, r
    status, r = post("fo.pro_intake")                                                 # back, so other tests find the officer
    assert status == 200, r


def close_leftovers(persona, cvo, username):
    """An interrupted earlier run can leave a case naming the officer open (it would withhold clearance); finish it
    through the normal steps: findings by the zone if the inquiry is open, then the CVO closes it."""
    def decide(case_id, decision):
        call(cvo, "POST", f"/api/v1/vigilance/cases/{case_id}/decisions", {"decision": decision, "note": "Closed by the next e2e run"},
             {"X-Step-Up-Token": step_up(cvo, "decide-vigilance-case", case_id)})
    for c in call(cvo, "GET", "/api/v1/vigilance/cases")[1]["data"]["cases"]:
        if c["subject_ref"] != username or c["state"] in ("CLOSED", "ACTION_ORDERED"):
            continue
        if c["state"] == "PI_ASSIGNED":
            zone = persona("zo-vigilance", "/vigilance")
            call(zone, "POST", f"/api/v1/vigilance/cases/{c['case_id']}/findings", {
                "finding": "NOT_SUBSTANTIATED", "recommendation": "Close the case (left by an earlier run).",
                "report": "Left open by an interrupted test run; nothing was examined and nothing was found (synthetic).",
                "evidence_examined": []}, {"X-Step-Up-Token": step_up(zone, "report-vigilance-findings", c["case_id"])})
        decide(c["case_id"], "CLOSED_NO_SUBSTANCE")

