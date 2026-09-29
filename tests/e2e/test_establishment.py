"""Phase 2, slice 6a on the running stack: the owner keeps the establishment record (KYC through the mock
registry, a branch, Form 5A signed with a one-time code) and asks for an address change that the APFC decides; a
new registration goes through OLRE — DA Compliance scrutiny and e-file, then the APFC's coverage decision."""
import uuid

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def test_owner_keeps_the_record_and_the_office_decides_a_change(persona):
    owner = persona("emp-owner", "/employer/establishment")
    ensure_verified_and_granted(owner)
    status, r = call(owner, "POST", "/api/v1/employers/me/kyc/TAN", {"value": "DELD12345A"},
                     {"X-Step-Up-Token": step_up(owner, "seed-establishment-kyc", f"{EST}:TAN")})
    assert status == 201 and r["data"]["result"] == "VERIFIED", r
    status, r = call(owner, "POST", "/api/v1/employers/me/branches",
                     {"name": f"Dyeing unit {uuid.uuid4().hex[:4]}", "kind": "DEPARTMENT",
                      "address": {"line": "Plot 7", "city": "New Delhi", "district": "Central Delhi", "pincode": "110001"}})
    assert status == 201 and r["data"]["sub_code"].startswith("DEMO/00001/000/"), r
    form = {"nature_of_business": "Textile manufacturing", "persons": [
        {"name": "Ravi Demo", "designation": "Director", "role": "DIRECTOR", "pan": "ABCPD1234E", "share_pct": 100}]}
    status, r = call(owner, "PUT", "/api/v1/employers/me/ownership-declaration", form, {"X-Step-Up-Token": step_up(owner, "sign-form-5a", EST)})
    assert status == 200 and r["data"]["filed"], r
    pin = f"1100{uuid.uuid4().int % 90 + 10}"
    status, r = call(owner, "PATCH", "/api/v1/employers/me",
                     {"address": {"line": "Plot 9", "city": "New Delhi", "district": "Central Delhi", "pincode": pin}, "reason": "Moved to a new building"},
                     {"X-Step-Up-Token": step_up(owner, "request-establishment-change", EST)})
    if status == 409:                                              # left pending by an earlier run: decide that one
        r = {"data": next(x for x in call(owner, "GET", "/api/v1/employers/me/change-requests")[1]["data"]
                          if x["state"] == "PENDING" and x["kind"] == "PROFILE")}
        pin = r["data"]["changes"].get("pincode", {}).get("to", pin)
    else:
        assert status == 200, r
    apfc = persona("ro-apfc", "/office/olre")
    request_id = r["data"]["request_id"]
    assert any(x["request_id"] == request_id for x in call(apfc, "GET", "/api/v1/office/establishment-change-requests")[1]["data"])
    status, r = call(apfc, "POST", f"/api/v1/office/establishments/{EST}/change-requests/{request_id}/decisions",
                     {"decision": "APPROVE", "note": "Rent deed checked"}, {"X-Step-Up-Token": step_up(apfc, "decide-establishment-change", request_id)})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    assert call(owner, "GET", "/api/v1/employers/me/configuration")[1]["data"]["address"]["pincode"] == pin


def test_olre_scrutiny_and_coverage_of_a_new_registration(persona):
    owner = persona("emp-owner", "/employer")
    status, reg = call(owner, "POST", "/api/v1/employers/registration-requests", {"legal_name": f"Demo Foods {uuid.uuid4().hex[:4]}", "pan": "AAAFD1234K"})
    assert status == 201, reg
    req = reg["data"]["request_id"]
    assert call(owner, "POST", f"/api/v1/employers/registration-requests/{req}/verification-evidence", {"pan": "AAAFD1234K"})[1]["data"]["state"] == "VERIFIED"
    da = persona("ro-da-compliance", "/office/olre")
    assert any(x["request_id"] == req for x in call(da, "GET", "/api/v1/office/establishment-registrations")[1]["data"])
    assert call(da, "GET", f"/api/v1/office/establishment-registrations/{req}/documents")[0] == 200
    status, r = call(da, "POST", f"/api/v1/office/establishment-registrations/{req}/scrutiny-notes",
                     {"checks": ["PAN verified", "Address checked"], "note": "Documents in order; compliance e-file opened"})
    assert status == 201 and r["data"]["efile_no"], r
    apfc = persona("ro-apfc", "/office/olre")
    status, r = call(apfc, "POST", f"/api/v1/office/establishment-registrations/{req}/coverage-decisions",
                     {"decision": "COVER", "coverage_date": "2026-09-01", "coverage_type": "STATUTORY", "reason": "Twenty or more employees on the rolls"},
                     {"X-Step-Up-Token": step_up(apfc, "decide-coverage", req)})
    assert status == 200 and r["data"]["stage"] == "COVERAGE_DECIDED", r
