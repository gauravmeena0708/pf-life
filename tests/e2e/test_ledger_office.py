"""Phase 2, slice 7b on the running stack: a cheque recorded by Cash pays a submitted return when the DA (Accounts)
allocates it to the TRRN (the mock bank then refuses an online payment for it); an Appendix E EPS diversion is
proposed by the DA and approved by the APFC, and the member's passbook shows the adjustment."""
import random
import uuid

from tests.e2e.test_journey_a_ecr import SEED, call, ecr_line, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"


def test_cheque_allocated_to_a_trrn_and_appendix_e(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    preparer, signatory = persona("emp-preparer", "/employer/ecr"), persona("emp-signatory", "/employer/ecr")
    m = SEED["members"][0]
    for _ in range(30):                       # a random past month; another one if an earlier run already filed it
        month = f"{random.randint(1990, 2000)}-{random.randint(1, 12):02d}"
        status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings", {"wage_month": month, "format": "ECR_TXT", "content": ecr_line(m["uan"], m["name"], 15000)})
        if status != 409:
            break
    assert status == 201 and created["data"]["filing"]["state"] == "VALIDATED", created
    f, total = created["data"]["filing"], created["data"]["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", {"decision": "APPROVE"},
         {"X-Step-Up-Token": step_up(signatory, "approve-ecr", f["filing_id"], f["version"], total)})
    status, sub = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions", None,
                       {"X-Step-Up-Token": step_up(signatory, "submit-ecr", f["filing_id"], f["version"], total),
                        "Idempotency-Key": str(uuid.uuid4()), "If-Match": str(f["version"])})
    assert status == 201, sub
    trrn = sub["data"]["trrn"]

    cash = persona("ro-cashier", "/office/ledger")
    ref = f"CHQ-{uuid.uuid4().hex[:6].upper()}"
    status, v = call(cash, "POST", "/api/v1/office/vdr-entries", {"establishment_id": EST, "instrument": "CHEQUE", "instrument_ref": ref,
                                                                   "amount_paise": total, "received_on": "2026-09-29"},
                     {"X-Step-Up-Token": step_up(cash, "record-vdr", ref, None, total)})
    assert status == 201, v
    da = persona("do-caseworker", "/office/ledger")
    status, r = call(da, "POST", f"/api/v1/office/receipts/{v['data']['vdr_id']}/trrn-adjustments", {"trrn": trrn},
                     {"X-Step-Up-Token": step_up(da, "adjust-trrn", v["data"]["vdr_id"], None, total)})
    assert status == 200 and r["data"]["state"] == "RECONCILED", r
    assert call(signatory, "GET", f"/api/v1/employers/me/challans/{trrn}")[1]["data"]["status"] == "PAID"
    wait_for(lambda: call(signatory, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents", {"channel": "NET_BANKING"},
                          {"X-Step-Up-Token": step_up(signatory, "pay-challan", trrn, None, total), "Idempotency-Key": str(uuid.uuid4())})[0] == 409,
             timeout=20, every=1)                                       # paid by cheque: no second payment online

    account = m["account_link_id"]
    status, adj = call(da, "POST", "/api/v1/office/ledger-adjustments", {"type": "APPENDIX_E", "appendix_type": "EPS_DIVERSION", "account_link_id": account,
                                                                        "employer_paise": 10000, "notesheet_no": f"NS/{uuid.uuid4().hex[:4]}",
                                                                        "notesheet_date": "2026-09-25", "remarks": "1.16% on higher wages (joint option)"},
                       {"X-Step-Up-Token": step_up(da, "propose-appendix-e", account, None, 10000)})
    assert status == 201, adj
    apfc = persona("ro-apfc", "/office/ledger")
    aid = adj["data"]["adjustment_id"]
    status, r = call(apfc, "POST", f"/api/v1/office/ledger-adjustments/{aid}/approvals", {"decision": "APPROVE", "note": "Joint option verified"},
                     {"X-Step-Up-Token": step_up(apfc, "approve-appendix-e", aid, None, 10000)})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    member = persona("member-a", "/member/passbook")
    wait_for(lambda: any(e["kind"] == "ADJUSTMENT" for a in call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]["accounts"]
                         for e in a["entries"]), timeout=20)
