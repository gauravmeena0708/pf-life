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
    m = SEED["members"][0]
    for _ in range(30):                       # another month if an earlier run already filed it
        month = f"{random.randint(1990, 2000)}-{random.randint(1, 12):02d}"
        status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings",
                               {"wage_month": month, "format": "ECR_TXT", "content": ecr_line(m["uan"], m["name"], 15000)})
        if status != 409:
            break
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


def pay_demand(sig, demand_id, amount):
    wait_for(lambda: call(sig, "POST", f"/api/v1/employers/me/demands/{demand_id}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(sig, "pay-demand", demand_id, None, amount), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
             timeout=30, every=2)


def test_vishwas_settlement_and_direct_payment_of_the_revised_demand(persona):
    """VISHWAS, 2026: an old default's damages recalculated at the monthly rate once its 7Q interest is paid."""
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    sig = persona("emp-signatory", "/employer/returns")
    mine = call(sig, "GET", "/api/v1/employers/me/vishwas-applications")[1]["data"]
    eligible = [a for a in mine["assessment"] if a["eligible"]]
    only_7q = ["Pay the 7Q interest on this default first."]
    if not eligible and not any(a["reasons"] == only_7q for a in mine["assessment"]):
        pay_a_return_late(persona, sig)                  # a default from the 1990s: 14B and 7Q demands
        mine = wait_for(lambda: (lambda m: m if any(a["reasons"] == only_7q or a["eligible"] for a in m["assessment"]) else None)(
            call(sig, "GET", "/api/v1/employers/me/vishwas-applications")[1]["data"]), timeout=60, every=3)
        eligible = [a for a in mine["assessment"] if a["eligible"]]
    if not eligible:                                     # an old default whose only bar is its 7Q interest: pay that first
        blocked = next(a for a in mine["assessment"] if a["reasons"] == only_7q)
        months = {d["wage_month"] for d in blocked["defaults"]}
        items = call(sig, "GET", "/api/v1/employers/me/demands")[1]["data"]["items"]
        owed = [d for d in items if d["kind"] == "INTEREST_7Q" and d["state"] == "OPEN" and (
            d["wage_month"] in months or any(m in (d.get("working") or "") for m in months))]
        assert owed, "the 7Q interest that bars the old default"
        for d in owed:
            pay_demand(sig, d["demand_id"], d["amount_paise"])
        mine = wait_for(lambda: (lambda m: m if any(a["eligible"] for a in m["assessment"]) else None)(
            call(sig, "GET", "/api/v1/employers/me/vishwas-applications")[1]["data"]), timeout=60, every=3)
        eligible = [a for a in mine["assessment"] if a["eligible"]]
    chosen = [eligible[0]["demand_id"]]
    assert all(d["rate_pct_per_month"] in (0.25, 0.5, 1.0) for d in eligible[0]["defaults"])
    status, r = call(sig, "POST", "/api/v1/employers/me/vishwas-applications", {"demand_ids": chosen, "declaration": True})
    assert status == 201, r
    app_id, revised = r["data"]["application_id"], r["data"]["estimated_settlement_paise"]
    assert 0 < revised <= r["data"]["damages_paise"]
    apfc = persona("ro-apfc", "/office/compliance")
    status, r = call(apfc, "POST", f"/api/v1/office/compliance/vishwas-applications/{app_id}/decisions",
                     {"decision": "APPROVE", "note": "Dispute settled under VISHWAS, 2026"},
                     {"X-Step-Up-Token": step_up(apfc, "decide-vishwas", app_id, None, revised)})
    assert status == 200 and r["data"]["state"] == "APPROVED" and r["data"]["revised_paise"] == revised, r
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
