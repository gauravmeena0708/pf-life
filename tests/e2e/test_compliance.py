"""Phase 2, slice 8a on the running stack: the DA (Compliance) sees defaulters and opens a case; the establishment
appears on the public defaulter list; the employer applies under VISHWAS for its open 14B demands, the APFC approves,
and the revised demand is paid directly through the mock bank."""
import uuid

import random

from tests.e2e.test_journey_a_ecr import SEED, call, ecr_line, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def test_defaulters_case_and_public_list(persona):
    da = persona("ro-da-compliance", "/office/compliance")
    status, d = call(da, "GET", "/api/v1/office/compliance/defaulters")
    assert status == 200 and "defaulters" in d["data"], d
    status, r = call(da, "POST", "/api/v1/office/compliance/cases", {"establishment_id": EST, "kind": "NON_FILING", "wage_months": ["2026-08"],
                                                                     "amount_paise": 0, "note": "No return filed for August 2026"})
    assert status == 201 or r.get("type") == "/problems/case-open", r
    cases = call(da, "GET", "/api/v1/office/compliance/cases?status=OPEN")[1]["data"]
    assert any(c["establishment_id"] == EST and c["kind"] == "NON_FILING" for c in cases)
    public = persona("member-a", "/public")
    listed = call(public, "GET", "/api/v1/public/defaulting-establishments")[1]["data"]
    assert any(e["establishment_id"] == EST for e in listed["establishments"]), listed


def pay_a_return_late(persona, sig):
    """File and pay a return for a past month: paid after its due date, it raises 14B / 7Q demands."""
    preparer = persona("emp-preparer", "/employer/ecr")
    month = f"{random.randint(1990, 2000)}-{random.randint(1, 12):02d}"
    m = SEED["members"][0]
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings",
                           {"wage_month": month, "format": "ECR_TXT", "content": ecr_line(m["uan"], m["name"], 15000)})
    assert status == 201, created
    f, total = created["data"]["filing"], created["data"]["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    call(sig, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", {"decision": "APPROVE"},
         {"X-Step-Up-Token": step_up(sig, "approve-ecr", f["filing_id"], f["version"], total)})
    status, sub = call(sig, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions", None,
                       {"X-Step-Up-Token": step_up(sig, "submit-ecr", f["filing_id"], f["version"], total),
                        "Idempotency-Key": str(uuid.uuid4()), "If-Match": str(f["version"])})
    assert status == 201, sub
    trrn = sub["data"]["trrn"]
    wait_for(lambda: call(sig, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(sig, "pay-challan", trrn, None, total), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
             timeout=20, every=1)


def test_vishwas_settlement_and_direct_payment_of_the_revised_demand(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    sig = persona("emp-signatory", "/employer/returns")
    if not call(sig, "GET", "/api/v1/employers/me/vishwas-applications")[1]["data"]["open_14b_demands"]:
        pay_a_return_late(persona, sig)
    mine = wait_for(lambda: (lambda d: d if d["open_14b_demands"] else None)(
        call(sig, "GET", "/api/v1/employers/me/vishwas-applications")[1]["data"]), timeout=30)
    chosen = [mine["open_14b_demands"][0]["demand_id"]]
    status, r = call(sig, "POST", "/api/v1/employers/me/vishwas-applications", {"demand_ids": chosen, "declaration": True})
    assert status == 201, r
    app_id, damages = r["data"]["application_id"], r["data"]["damages_paise"]
    revised = damages * 3000 // 10000 // 100 * 100
    apfc = persona("ro-apfc", "/office/compliance")
    status, r = call(apfc, "POST", f"/api/v1/office/compliance/vishwas-applications/{app_id}/decisions",
                     {"decision": "APPROVE", "note": "Dispute settled under the scheme (illustrative)"},
                     {"X-Step-Up-Token": step_up(apfc, "decide-vishwas", app_id, None, revised)})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    new_id = f"DEM-{app_id}"

    def demand_state():
        items = {d["demand_id"]: d for d in call(sig, "GET", "/api/v1/employers/me/demands")[1]["data"]["items"]}
        return items.get(new_id, {}).get("state"), items.get(chosen[0], {}).get("state")
    wait_for(lambda: demand_state() == ("OPEN", "WAIVED"), timeout=30)
    if revised:
        wait_for(lambda: call(sig, "POST", f"/api/v1/employers/me/demands/{new_id}/payment-intents", {"channel": "NET_BANKING"},
                              {"X-Step-Up-Token": step_up(sig, "pay-demand", new_id, None, revised), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
                 timeout=30, every=2)
        wait_for(lambda: demand_state()[0] == "PAID", timeout=30)
