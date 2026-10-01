"""Phase 2, slice 12b on the running stack: the demo establishment's signatory asks for voluntary coverage, closure and
a transfer to another office; the office sees each request and turns it down (so the demo establishment stays open,
in its office and compulsorily covered — the approvals and what they set off are covered by the unit tests). As a
contractor of Demo Engineering Works, the establishment tags a submitted return's workers to that principal, whose
owner then sees the month in the contractor's compliance. Repeatable."""
import random
import uuid

from tests.e2e.test_journey_a_ecr import SEED, call, ecr_line, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST, PRINCIPAL = "EST-DEMO-0001", "EST-DEMO-0002"


def test_voluntary_coverage_closure_and_office_transfer_are_requested_and_decided(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    signatory = persona("emp-signatory", "/employer")
    apfc = persona("ro-apfc", "/office/olre")

    def reject_pending():
        for r in call(apfc, "GET", "/api/v1/office/establishment-change-requests")[1]["data"]:
            if r["establishment_id"] == EST and r["kind"] in ("VOLUNTARY_COVERAGE", "CLOSURE", "OFFICE_TRANSFER"):
                call(apfc, "POST", f"/api/v1/office/establishments/{EST}/change-requests/{r['request_id']}/decisions",
                     {"decision": "REJECT", "note": "Closed by the next e2e run"},
                     {"X-Step-Up-Token": step_up(apfc, "decide-establishment-change", r["request_id"])})
    reject_pending()                                                     # left by an interrupted earlier run

    def asked():
        return {"X-Step-Up-Token": step_up(signatory, "request-establishment-change", EST)}
    status, r = call(signatory, "POST", "/api/v1/employers/voluntary-coverage-requests",
                     {"employees": 25, "employees_consenting": 20, "effective_from": "2026-10-01", "reason": "Workers asked for coverage"}, asked())
    assert status == 409 and r["type"] == "/problems/covered-compulsorily", r
    status, voluntary = call(signatory, "POST", "/api/v1/employers/voluntary-coverage-requests",
                             {"employees": 12, "employees_consenting": 8, "effective_from": "2026-10-01", "reason": "Workers asked for coverage"}, asked())
    assert status == 201 and voluntary["data"]["kind"] == "VOLUNTARY_COVERAGE", voluntary
    status, closure = call(signatory, "POST", "/api/v1/employers/me/closure-requests",
                           {"closed_on": "2026-09-30", "reason": "BUSINESS_DISCONTINUED", "last_wage_month": "2026-09", "note": "Demonstration request"},
                           {"X-Step-Up-Token": step_up(signatory, "request-closure", EST)})
    assert status == 201 and closure["data"]["kind"] == "CLOSURE", closure
    status, transfer = call(signatory, "POST", "/api/v1/employers/me/office-transfer-requests",
                            {"to_office_id": "RO-DEMO-02", "reason": "The works moved across the city", "effective_from": "2026-11-01"},
                            {"X-Step-Up-Token": step_up(signatory, "request-office-transfer", EST)})
    assert status == 201 and transfer["data"]["kind"] == "OFFICE_TRANSFER", transfer

    queued = {r["request_id"] for r in call(apfc, "GET", "/api/v1/office/establishment-change-requests")[1]["data"]}
    assert {voluntary["data"]["request_id"], closure["data"]["request_id"], transfer["data"]["request_id"]} <= queued
    reject_pending()
    mine = {r["request_id"]: r["state"] for r in call(signatory, "GET", "/api/v1/employers/me/change-requests")[1]["data"]}
    assert all(mine[r["data"]["request_id"]] == "REJECTED" for r in (voluntary, closure, transfer))
    assert call(signatory, "GET", "/api/v1/employers/me")[1]["data"]["office_id"] == "RO-DEMO-01"


def test_contractor_tags_workers_and_the_principal_sees_compliance(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    preparer, signatory = persona("emp-preparer", "/employer/ecr"), persona("emp-signatory", "/employer/ecr")
    month = f"{random.randint(1980, 1989)}-{random.randint(1, 12):02d}"
    a, b = SEED["members"][0], SEED["members"][1]
    content = "\n".join([ecr_line(a["uan"], a["name"], 15000), ecr_line(b["uan"], b["name"], 15000)])
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings", {"wage_month": month, "format": "ECR_TXT", "content": content})
    assert status == 201, created
    f, total = created["data"]["filing"], created["data"]["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    status, r = call(preparer, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/principal-employer-tags",
                     {"principal_establishment_id": PRINCIPAL, "work_order_ref": "WO/DEW/2026/014", "uans": [a["uan"]]})
    assert status == 409, r                                                      # not submitted yet
    call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", {"decision": "APPROVE"},
         {"X-Step-Up-Token": step_up(signatory, "approve-ecr", f["filing_id"], f["version"], total)})
    status, sub = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions", None,
                       {"X-Step-Up-Token": step_up(signatory, "submit-ecr", f["filing_id"], f["version"], total),
                        "Idempotency-Key": str(uuid.uuid4()), "If-Match": str(f["version"])})
    assert status == 201, sub
    status, r = call(preparer, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/principal-employer-tags",
                     {"principal_establishment_id": PRINCIPAL, "work_order_ref": "WO/DEW/2026/014", "uans": [a["uan"], "999999999999"]})
    assert status == 422, r                                                      # not a worker on this return
    status, r = call(preparer, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/principal-employer-tags",
                     {"principal_establishment_id": PRINCIPAL, "work_order_ref": "WO/DEW/2026/014", "uans": [a["uan"], b["uan"]]})
    assert status == 201 and r["data"]["members"] == 2 and r["data"]["paid"] is False, r

    principal = persona("principal-owner", "/employer")
    contractors = call(principal, "GET", "/api/v1/employers/me/contractors")[1]["data"]
    assert any(c.get("establishment_id") == EST for c in contractors), contractors
    compliance = wait_for(lambda: next((m for m in call(principal, "GET", f"/api/v1/employers/me/contractors/{EST}/compliance")[1]
                                        .get("data", {}).get("months", []) if m["filing_id"] == f["filing_id"]), None), timeout=30)
    assert compliance["members"] == 2 and compliance["paid"] is False
    assert call(preparer, "GET", f"/api/v1/employers/me/contractors/{EST}/compliance")[0] in (403, 404)   # not the principal
