"""Phase 2, slice 7a on the running stack: an arrear return for a paid month, submitted and its TRRN cancelled;
the demands a late payment raised are paid with a miscellaneous direct challan through the mock bank, then knocked
off by the DA (Compliance) and approved by the SS; the returns dashboard and the office's list of unpaid returns."""
import uuid

from tests.e2e.test_journey_a_ecr import SEED, call, ecr_line, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def test_arrear_return_cancelled_and_demands_knocked_off(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    signatory = persona("emp-signatory", "/employer/returns")
    months = call(signatory, "GET", "/api/v1/employers/me/returns/dashboard")[1]["data"]
    paid = next((m for m in months if m["status"] == "PAID"), None)
    assert paid, "Journey A leaves a paid month behind"

    preparer = persona("emp-preparer", "/employer/ecr")
    m0 = SEED["members"][0]
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings",
                           {"wage_month": paid["wage_month"], "format": "ECR_TXT", "content": ecr_line(m0["uan"], m0["name"], 2000), "type": "ARREAR"})
    assert status == 201 and created["data"]["filing"]["state"] == "VALIDATED", created
    f, total = created["data"]["filing"], created["data"]["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    status, r = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", {"decision": "APPROVE"},
                     {"X-Step-Up-Token": step_up(signatory, "approve-ecr", f["filing_id"], f["version"], total)})
    assert status == 200, r
    status, sub = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions", None,
                       {"X-Step-Up-Token": step_up(signatory, "submit-ecr", f["filing_id"], f["version"], total),
                        "Idempotency-Key": str(uuid.uuid4()), "If-Match": str(f["version"])})
    assert status == 201, sub
    da = persona("do-caseworker", "/office/returns")
    assert any(x["filing_id"] == f["filing_id"] for x in call(da, "GET", "/api/v1/office/ecr-filings")[1]["data"])
    status, r = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/cancellations", {"reason": "Arrear amount to be revised"},
                     {"X-Step-Up-Token": step_up(signatory, "cancel-trrn", f["filing_id"], None, total)})
    assert status == 200 and r["data"]["state"] == "CANCELLED", r

    demands = call(signatory, "GET", "/api/v1/employers/me/demands")[1]["data"]
    open_items = [d for d in demands["items"] if d["state"] == "OPEN" and d["kind"] in ("DAMAGES_14B", "INTEREST_7Q")
                  and d["trrn"] not in (None, "-") and not d["demand_id"].startswith(("D14B-", "D7Q-"))]   # auto-calculated, not an order's
    if not open_items:                                   # earlier runs knocked them all off: pay a return late, as the employer did
        from tests.e2e.test_compliance import pay_a_return_late
        pay_a_return_late(persona, signatory)
        demands = wait_for(lambda: (lambda d: d if any(x["state"] == "OPEN" and x["kind"] in ("DAMAGES_14B", "INTEREST_7Q") and x["trrn"] not in (None, "-")
                                                       and not x["demand_id"].startswith(("D14B-", "D7Q-")) for x in d["items"]) else None)(
            call(signatory, "GET", "/api/v1/employers/me/demands")[1]["data"]), timeout=60, every=3)
        open_items = [d for d in demands["items"] if d["state"] == "OPEN" and d["kind"] in ("DAMAGES_14B", "INTEREST_7Q")
                      and d["trrn"] not in (None, "-") and not d["demand_id"].startswith(("D14B-", "D7Q-"))]
    assert open_items, "a late payment raises 14B / 7Q demands"
    by_trrn = open_items[0]["trrn"]
    chosen = [d for d in open_items if d["trrn"] == by_trrn]
    amounts = {d["kind"]: d["amount_paise"] for d in chosen}
    owed = sum(amounts.values())
    status, ch = call(signatory, "POST", "/api/v1/employers/me/direct-challans",
                      {"kind": "MISC_14B_7Q", "damages_14b_paise": amounts.get("DAMAGES_14B", 0), "interest_7q_paise": amounts.get("INTEREST_7Q", 0),
                       "reason": f"14B / 7Q on {by_trrn}"}, {"X-Step-Up-Token": step_up(signatory, "raise-direct-challan", EST, None, owed)})
    assert status == 201, ch
    trrn = ch["data"]["trrn"]
    wait_for(lambda: call(signatory, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(signatory, "pay-challan", trrn, None, owed), "Idempotency-Key": str(uuid.uuid4())})[0] == 202,
             timeout=20, every=1)
    wait_for(lambda: call(signatory, "GET", f"/api/v1/employers/me/challans/{trrn}")[1]["data"]["status"] == "PAID", timeout=30)

    dac = persona("ro-da-compliance", "/office/returns")
    status, ko = call(dac, "POST", f"/api/v1/office/establishments/{EST}/damages-knock-offs", {"trrn": trrn, "demand_ids": [d["demand_id"] for d in chosen]},
                      {"X-Step-Up-Token": step_up(dac, "propose-knock-off", EST, None, owed)})
    assert status == 201, ko
    ss = persona("ro-ss", "/office/returns")
    status, r = call(ss, "POST", f"/api/v1/office/damages-knock-offs/{ko['data']['knock_off_id']}/approvals", {"decision": "APPROVE", "note": "Amounts match"},
                     {"X-Step-Up-Token": step_up(ss, "approve-knock-off", ko["data"]["knock_off_id"], None, owed)})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    after = {d["demand_id"]: d["state"] for d in call(signatory, "GET", "/api/v1/employers/me/demands")[1]["data"]["items"]}
    assert all(after[d["demand_id"]] == "KNOCKED_OFF" for d in chosen)
