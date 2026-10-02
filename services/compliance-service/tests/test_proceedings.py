"""Phase 2, slice 11a: an inspection through DA / SS / circle officer, the inquiry registered with a diary number and
allocated by size, summons, hearings and daily orders, the employer's replies and the 7A order (Compliance Manual ch. 2)."""
import json
import time
from datetime import UTC, datetime, timedelta

from tests.test_compliance import EST, S, ctx, hdr  # noqa: F401

APFC, RPFC2, OIC, EO, DA, SS = S["ro-apfc"], S["ro-rpfc2"], S["ro-oic"], S["ro-eo"], S["ro-da-compliance"], S["ro-ss"]
OWNER = S["emp-owner"]
BASE = "/api/v1/office/compliance"


def officer_of(subject):
    return {APFC: "fo.apfc", RPFC2: "fo.apfc", OIC: "fo.oic", EO: "fo.eo", DA: "fo.da_compliance", SS: "fo.ss"}[subject]


def as_(subject, step_up=None):
    return hdr(subject, officer_of(subject), step_up)


def inspected(client):
    """An inspection taken up to the circle officer's decision to initiate a 7A inquiry."""
    r = client.post(f"{BASE}/inspections", json={"establishment_id": EST, "purpose": "COMPLAINT", "period_from": "2025-04",
                                                 "period_to": "2025-09", "eo_subject": EO, "note": "Complaint by workers"}, headers=as_(APFC))
    assert r.status_code == 201, r.json()
    iid = r.json()["data"]["inspection_id"]
    report = {"visited_on": datetime.now(UTC).date().isoformat(), "employees_found": 40, "employees_not_enrolled": 12,
              "wages_paise_monthly": 1500000, "findings": "12 workers not enrolled", "dues_estimate_paise": 5000000,
              "recommendation": "INITIATE_7A_DUES"}
    assert client.post(f"{BASE}/inspections/{iid}/reports", json=report, headers=as_(APFC)).status_code == 403        # only the EO
    assert client.post(f"{BASE}/inspections/{iid}/reports", json=report, headers=as_(EO)).status_code == 200
    assert client.post(f"{BASE}/inspections/{iid}/processing-notes", json={"note": "SS first"}, headers=as_(SS)).status_code == 409
    for who in (DA, SS):
        assert client.post(f"{BASE}/inspections/{iid}/processing-notes", json={"note": "Processed"}, headers=as_(who)).status_code == 200
    r = client.post(f"{BASE}/inspections/{iid}/processing-notes", json={"note": "Fit case", "decision": "INITIATE_7A"}, headers=as_(APFC))
    assert r.status_code == 200 and r.json()["data"]["state"] == "DECIDED_INITIATE", r.json()
    stages = [s["stage"] for s in r.json()["data"]["steps"]]
    assert stages == ["REPORT", "DA_NOTE", "SS_NOTE", "DECISION"]
    return iid


def register(client, uans, inspection_id=None, note="From the inspection report", oic_approval=None):
    body = {"establishment_id": EST, "kind": "INQUIRY_7A", "dispute": "DUES", "period_from": "2025-04", "period_to": "2025-09",
            "contributory_uans": uans, "note": note, **({"inspection_id": inspection_id} if inspection_id else {}),
            **({"oic_approval": oic_approval} if oic_approval else {})}
    return client.post(f"{BASE}/cases", json=body, headers=as_(SS))


def test_inspection_to_registration_and_allocation_by_size(ctx):
    client, q, _ = ctx
    iid = inspected(client)
    assert register(client, 39, iid).status_code == 422                       # fewer than the EO counted
    r = register(client, 120, iid)
    assert r.status_code == 201, r.json()
    inquiry = r.json()["data"]
    assert inquiry["diary_no"].startswith("EPR/RO-DEMO-01/") and inquiry["officer_rank"] == "APFC" and inquiry["officer_subject"] == APFC
    assert register(client, 600, note="no inspection").status_code == 422    # without an inspection, the OIC's approval is recorded
    medium = register(client, 600, note="A complaint with payslips", oic_approval="OIC approved on e-office file C-17")
    assert medium.status_code == 201, medium.json()
    assert medium.json()["data"]["officer_rank"] == "RPFC-II" and medium.json()["data"]["officer_subject"] == RPFC2
    large = register(client, 5000, note="Information from GSTN", oic_approval="OIC approved on e-office file C-18")
    assert large.json()["data"]["officer_rank"] == "RPFC-I" and large.json()["data"]["officer_subject"] == OIC
    numbers = [x.json()["data"]["diary_no"] for x in (r, medium, large)]
    assert len(set(numbers)) == 3
    events = [e for (e,) in q("SELECT event_type FROM outbox ORDER BY id")]
    assert events.count("InquiryRegistered.v1") == 3 and "InspectionReported.v1" in events
    detail = client.get(f"{BASE}/cases/{inquiry['case_id']}", headers=as_(DA)).json()["data"]
    assert detail["inquiry"]["diary_no"] == inquiry["diary_no"]

    case = medium.json()["data"]["case_id"]
    move = {"officer_subject": APFC, "reason": "TRANSFER", "note": "Officer transferred"}
    assert client.post(f"{BASE}/cases/{case}/allocations", json=move, headers=as_(OIC)).status_code == 428       # step-up
    step = {"action": "reallocate-inquiry", "resource_id": case}
    assert client.post(f"{BASE}/cases/{case}/allocations", json=move, headers=as_(OIC, step)).status_code == 422  # not the same rank
    ok = client.post(f"{BASE}/cases/{case}/allocations", json={**move, "officer_subject": OIC}, headers=as_(OIC, step))
    assert ok.status_code == 200 and ok.json()["data"]["officer_subject"] == OIC


def summoned(client, case, officer=APFC):
    hearing_at = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    step = {"action": "issue-summons", "resource_id": case}
    r = client.post(f"{BASE}/cases/{case}/notices", json={"hearing_at": hearing_at, "scope": "Dues of 12 workers", "period": "Apr-Sep 2025"},
                    headers=as_(officer, step))
    assert r.status_code == 200, r.json()
    time.sleep(1.2)
    return hearing_at


def test_summons_hearings_submissions_and_the_7a_order(ctx):
    client, q, _ = ctx
    case = register(client, 120, inspected(client)).json()["data"]["case_id"]
    dues = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
             "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]
    order = {"kind": "7A", "dues": dues, "reasoning": "Wages of 12 workers found in the muster roll", "ex_parte": False}
    early = client.post(f"{BASE}/cases/{case}/orders", json=order, headers=as_(APFC, {"action": "pass-order", "resource_id": case}))
    assert early.status_code == 422                                            # no summons, no hearing
    assert client.post(f"{BASE}/cases/{case}/notices", json={"hearing_at": datetime.now(UTC).isoformat(), "scope": "x", "period": "y"},
                       headers=as_(RPFC2, {"action": "issue-summons", "resource_id": case})).status_code == 403   # not the officer
    hearing_at = summoned(client, case)

    held = datetime.now(UTC)
    first = {"held_at": held.isoformat(), "employer_present": True, "eo_present": True, "proceedings": "Employer asks for time",
             "next_hearing_at": (held + timedelta(days=10)).isoformat()}
    assert client.post(f"{BASE}/cases/{case}/hearings", json=first, headers=as_(APFC)).status_code == 422          # beyond 7 days
    first["next_hearing_at"] = (held + timedelta(days=7)).isoformat()
    assert client.post(f"{BASE}/cases/{case}/hearings", json=first, headers=as_(APFC)).status_code == 200

    owner = hdr(OWNER, "employer.owner", establishment=EST)
    mine = client.get("/api/v1/employers/me/proceedings", headers=owner).json()["data"]
    assert mine[0]["diary_no"] and "officer_subject" not in mine[0] and mine[0]["summons"][0]["detail"]["hearing_at"] == hearing_at
    reply = client.post(f"/api/v1/employers/me/proceedings/{case}/submissions",
                        json={"kind": "REPLY", "text": "They are contract workers", "documents": ["contracts.pdf"]}, headers=owner)
    assert reply.status_code == 200
    assert client.post(f"/api/v1/employers/me/proceedings/{case}/submissions", json={"kind": "REPLY", "text": "x"},
                       headers=hdr(OWNER, "employer.owner", establishment="EST-OTHER")).status_code == 404

    last = {"held_at": datetime.now(UTC).isoformat(), "employer_present": True, "eo_present": True,
            "proceedings": "Arguments heard; reserved for orders", "concluded": True}
    concluded = client.post(f"{BASE}/cases/{case}/hearings", json=last, headers=as_(APFC))
    assert concluded.status_code == 200 and concluded.json()["data"]["order_due_at"]

    step = {"action": "pass-order", "resource_id": case, "amount_paise": 4500000}       # the code is bound to the amount
    assert client.post(f"{BASE}/cases/{case}/orders", json={**order, "ex_parte": True}, headers=as_(APFC, step)).status_code == 422   # employer was present
    assert client.post(f"{BASE}/cases/{case}/orders", json={**order, "kind": "14B"}, headers=as_(APFC, step)).status_code == 422   # a 7A case takes a 7A order
    outside = [{**dues[0], "wage_month": "2026-01"}]
    assert client.post(f"{BASE}/cases/{case}/orders", json={**order, "dues": outside}, headers=as_(APFC, step)).status_code == 422
    passed = client.post(f"{BASE}/cases/{case}/orders", json=order, headers=as_(APFC, step))
    assert passed.status_code == 200, passed.json()
    data = passed.json()["data"]
    assert data["total_paise"] == 4500000 and data["late"] is False and "₹45,000" in data["text"] and data["demand_id"] == f"D7A-{case}"
    raised = [json.loads(p) for (p,) in q("SELECT payload FROM outbox WHERE event_type='DemandRaised.v1'")]
    payload = raised[-1]["envelope"]["payload"]
    assert payload["demand_type"] == "DUES_7A" and json.loads(payload["working"])[0]["ac10_pension_paise"] == 1500000
    assert client.post(f"/api/v1/employers/me/proceedings/{case}/submissions", json={"kind": "REPLY", "text": "late"}, headers=owner).status_code == 409
    assert client.get("/api/v1/employers/me/proceedings", headers=owner).json()["data"][0]["order"]["detail"]["total_paise"] == 4500000


def test_ex_parte_only_after_service_and_absence(ctx):
    client, _, _ = ctx
    case = register(client, 120, inspected(client)).json()["data"]["case_id"]
    summoned(client, case)
    absent = {"held_at": datetime.now(UTC).isoformat(), "employer_present": False, "eo_present": True,
              "proceedings": "Employer absent despite service", "concluded": True}
    assert client.post(f"{BASE}/cases/{case}/hearings", json=absent, headers=as_(APFC)).status_code == 200
    order = {"kind": "7A", "dues": [{"wage_month": "2025-05", "ac1_employee_paise": 100, "ac1_employer_paise": 100,
                                     "ac10_pension_paise": 0, "ac21_edli_paise": 0, "ac2_admin_paise": 0}],
             "reasoning": "On the record", "ex_parte": True}
    r = client.post(f"{BASE}/cases/{case}/orders", json=order, headers=as_(APFC, {"action": "pass-order", "resource_id": case, "amount_paise": 200}))
    assert r.status_code == 200 and r.json()["data"]["ex_parte"] is True


def test_order_due_date_counts_working_days():
    from app.api.proceedings import working_day_after
    friday = datetime(2026, 10, 2, 10, tzinfo=UTC)
    assert working_day_after(friday, 1).weekday() == 0                       # Friday + 1 working day = Monday
    assert (working_day_after(friday, 15) - friday).days == 21               # three weeks
