"""P2.19 edge case (a): A vanished contractor (EPF Act s.8A).

Tests first:
1. Field report records "not traceable" finding when contractor cannot be traced.
2. Traceable contractor with its own EPF code number is liable itself; principal is not.
3. Untraceable contractor's dues are assessed against the principal employer under EPF Act s.8A.
4. Principal employer records the recovery from the contractor (deduction or debt) as information.
"""
from datetime import UTC, date, datetime, timedelta
import json
import pytest

from tests.test_compliance import EST, S, ctx, hdr

APFC = S["ro-apfc"]
EO = S["ro-eo"]
DA = S["ro-da-compliance"]
SS = S["ro-ss"]
OIC = S["ro-oic"]
OWNER = S["emp-owner"]
BASE = "/api/v1/office/compliance"


def as_(subject, step_up=None, establishment=None):
    roles = {
        APFC: "fo.apfc",
        EO: "fo.eo",
        DA: "fo.da_compliance",
        SS: "fo.ss",
        OIC: "fo.oic",
        OWNER: "employer.owner",
    }
    return hdr(subject, roles[subject], step_up=step_up, establishment=establishment)


def _setup_inspection_and_inquiry(client):
    # 1. Schedule inspection
    r = client.post(
        f"{BASE}/inspections",
        json={
            "establishment_id": EST,
            "purpose": "COMPLAINT",
            "period_from": "2025-04",
            "period_to": "2025-09",
            "eo_subject": EO,
            "note": "Complaint regarding contract workers",
        },
        headers=as_(APFC),
    )
    assert r.status_code == 201, r.json()
    iid = r.json()["data"]["inspection_id"]

    # 2. EO reports with untraceable contractor finding
    report = {
        "visited_on": datetime.now(UTC).date().isoformat(),
        "employees_found": 30,
        "employees_not_enrolled": 10,
        "wages_paise_monthly": 1500000,
        "findings": "Contractor M/s Vanished Security not traceable at site; 10 contract workers unpaid",
        "dues_estimate_paise": 4500000,
        "recommendation": "INITIATE_7A_DUES",
        "contractors": [
            {
                "contractor_name": "M/s Vanished Security",
                "contractor_establishment_id": None,
                "traceable": False,
                "unpaid_dues_paise": 4500000,
                "workers_count": 10,
                "work_order_ref": "WO-SEC-2025",
                "findings": "Contractor vanished and not traceable",
            }
        ],
    }
    r = client.post(f"{BASE}/inspections/{iid}/reports", json=report, headers=as_(EO))
    assert r.status_code == 200, r.json()
    rep_data = r.json()["data"]["report"]
    assert "not traceable" in rep_data.get("findings", "").lower() or any(
        c.get("traceable") is False for c in rep_data.get("contractors", [])
    )

    # 3. Processing notes
    for who in (DA, SS):
        assert client.post(f"{BASE}/inspections/{iid}/processing-notes", json={"note": "Processed"}, headers=as_(who)).status_code == 200
    r = client.post(f"{BASE}/inspections/{iid}/processing-notes", json={"note": "Initiate 7A", "decision": "INITIATE_7A"}, headers=as_(APFC))
    assert r.status_code == 200, r.json()

    # 4. Register inquiry
    r = client.post(
        f"{BASE}/cases",
        json={
            "establishment_id": EST,
            "kind": "INQUIRY_7A",
            "dispute": "DUES",
            "period_from": "2025-04",
            "period_to": "2025-09",
            "contributory_uans": 30,
            "note": "Untraceable contractor dues under s.8A",
            "inspection_id": iid,
        },
        headers=as_(SS),
    )
    assert r.status_code == 201, r.json()
    case_id = r.json()["data"]["case_id"]

    # 5. Summons and conclude hearing
    import time
    hearing_at = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    r = client.post(
        f"{BASE}/cases/{case_id}/notices",
        json={"hearing_at": hearing_at, "scope": "Contractor dues s.8A", "period": "2025-04 to 2025-09"},
        headers=as_(APFC, {"action": "issue-summons", "resource_id": case_id}),
    )
    assert r.status_code == 200, r.json()
    time.sleep(1.2)

    last = {
        "held_at": datetime.now(UTC).isoformat(),
        "employer_present": True,
        "eo_present": True,
        "proceedings": "Arguments concluded on contractor liability",
        "concluded": True,
    }
    assert client.post(f"{BASE}/cases/{case_id}/hearings", json=last, headers=as_(APFC)).status_code == 200

    return case_id, iid


def test_traceable_coded_contractor_is_liable_itself(ctx):
    """Exception under EPF Act s.8A: a contractor with its own EPF code number who is traceable

    is liable itself — dues cannot be assessed against the principal employer.
    """
    client, _, _ = ctx
    case_id, _ = _setup_inspection_and_inquiry(client)

    dues = [{
        "wage_month": "2025-04",
        "ac1_employee_paise": 2160000,
        "ac1_employer_paise": 660000,
        "ac10_pension_paise": 1500000,
        "ac21_edli_paise": 90000,
        "ac2_admin_paise": 90000,
    }]
    # Attempt to assess against principal when contractor has code and is traceable
    order = {
        "kind": "7A",
        "dues": dues,
        "reasoning": "Contractor has code and is traceable at local office",
        "ex_parte": False,
        "contractor": {
            "contractor_name": "M/s Traceable Services",
            "contractor_establishment_id": "EST-CTR-9999",
            "traceable": True,
            "work_order_ref": "WO-2025-99",
        },
    }
    step = {"action": "pass-order", "resource_id": case_id, "amount_paise": 4500000}
    r = client.post(f"{BASE}/cases/{case_id}/orders", json=order, headers=as_(APFC, step))
    # Must fail because traceable coded contractor is liable itself (s.8A exception)
    assert r.status_code == 422, r.json()
    assert "contractor" in r.json()["detail"].lower() or "liable itself" in r.json()["detail"].lower() or "8a" in r.json()["detail"].lower()


def test_untraceable_contractor_assessed_against_principal(ctx):
    """EPF Act s.8A: when a contractor's dues are unpaid and contractor cannot be traced,

    the dues are assessed against the principal employer.
    """
    client, q, _ = ctx
    case_id, _ = _setup_inspection_and_inquiry(client)

    dues = [{
        "wage_month": "2025-04",
        "ac1_employee_paise": 2160000,
        "ac1_employer_paise": 660000,
        "ac10_pension_paise": 1500000,
        "ac21_edli_paise": 90000,
        "ac2_admin_paise": 90000,
    }]
    order = {
        "kind": "7A",
        "dues": dues,
        "reasoning": "Contractor vanished and untraceable; assessed against principal employer under EPF Act s.8A",
        "ex_parte": False,
        "contractor": {
            "contractor_name": "M/s Vanished Security",
            "contractor_establishment_id": None,
            "traceable": False,
            "work_order_ref": "WO-SEC-2025",
        },
    }
    step = {"action": "pass-order", "resource_id": case_id, "amount_paise": 4500000}
    r = client.post(f"{BASE}/cases/{case_id}/orders", json=order, headers=as_(APFC, step))
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["total_paise"] == 4500000
    assert "8a" in data["text"].lower() or "principal" in data["text"].lower() or data.get("contractor_liability")


def test_principal_records_recovery_from_contractor(ctx):
    """EPF Act s.8A: Principal employer may recover assessed dues from contractor by deduction

    from amounts payable or as a debt; record principal's recovery as information.
    """
    client, _, _ = ctx
    case_id, _ = _setup_inspection_and_inquiry(client)

    owner_hdr = as_(OWNER, establishment=EST)

    recovery_payload = {
        "case_id": case_id,
        "contractor_name": "M/s Vanished Security",
        "contractor_establishment_id": None,
        "work_order_ref": "WO-SEC-2025",
        "mode": "DEDUCTION_FROM_BILLS",
        "amount_paise": 4500000,
        "reference": "INV-DED-2026-001",
        "recovered_on": date.today().isoformat(),
        "note": "Deducted from security deposit / final bill as permitted by EPF Act s.8A",
    }
    r = client.post("/api/v1/employers/me/contractor-recoveries", json=recovery_payload, headers=owner_hdr)
    assert r.status_code == 201, r.json()
    rec = r.json()["data"]
    assert rec["recovery_id"]
    assert rec["mode"] == "DEDUCTION_FROM_BILLS"
    assert rec["amount_paise"] == 4500000
    assert rec["contractor_name"] == "M/s Vanished Security"

    # Query list
    r_list = client.get("/api/v1/employers/me/contractor-recoveries", headers=owner_hdr)
    assert r_list.status_code == 200, r_list.json()
    assert any(x["recovery_id"] == rec["recovery_id"] for x in r_list.json()["data"])
