"""P2.19c: rectifying erroneous EPS contributions (HO circular WSU/2025/E-961539, 19 Dec 2025)."""
import json
from datetime import date

from app.domain.eps_rectification import months_after, work_out
from tests.test_ecr_api import EST, MONTH, SEED, ctx, ecr_line, hdr, preparer, signatory  # noqa: F401
from tests.test_returns import pay, submit

S = SEED["keycloak_subjects"]
DA, APFC, CASH = S["do-caseworker"], S["ro-apfc"], S["ro-cashier"]
A, B = SEED["members"][0], SEED["members"][1]
URL = "/api/v1/office/eps-rectifications"


def office(subject, role, action=None, resource=None, amount=None):
    step = {"action": action, "resource_id": resource, "resource_version": None, "amount_paise": amount} if action else None
    return hdr(subject, role, [], step, establishment=None)


def post_return(client, content, payment_id):
    r = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": content}, headers=preparer())
    data = r.json()["data"]
    f, total = data["filing"], data["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    step = {"action": "approve-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", json={"decision": "APPROVE"}, headers=signatory(step)).status_code == 200
    pay(submit(client, f, total), total, payment_id)


def no_eps(m, wages=15000):
    return "#~#".join(map(str, [m["uan"], m["name"], wages, wages, 0, wages, round(wages * 0.12), 0, round(wages * 0.12), 0, 0]))


def test_working_by_hand():
    months = [{"wage_month": "2025-04", "epf_wages_paise": 2000000, "eps_wages_paise": 1500000, "eps_paise": 125000, "ceiling_paise": 1500000, "eps_rate_bp": 833},
              {"wage_month": "2025-05", "epf_wages_paise": 2000000, "eps_wages_paise": 0, "eps_paise": 0, "ceiling_paise": 1500000, "eps_rate_bp": 833}]
    today = date(2026, 4, 15)
    allowed = work_out(months, "WRONGLY_ALLOWED", today, lambda m: 825)
    # April 2025's ₹1,250 for 11 months (May 2025 to March 2026) at 8.25%: ₹94.53 → ₹95
    assert allowed["months"] == [{"wage_month": "2025-04", "basis": "EPS remitted", "amount_paise": 125000, "rate_bp": 825, "months": 11, "interest_paise": 9500}]
    denied = work_out(months, "WRONGLY_DENIED", today, lambda m: 825)
    # May 2025: 8.33% of ₹15,000 (the ceiling, not the ₹20,000 wages) = ₹1,250 for 10 months
    assert [(x["wage_month"], x["amount_paise"], x["months"]) for x in denied["months"]] == [("2025-05", 125000, 10)]
    assert denied["total_paise"] == 125000 + denied["interest_paise"] and months_after("2026-03", today) == 0


def test_eps_wrongly_allowed_goes_back_to_the_pf_and_stops_on_later_returns(ctx):
    client, q = ctx
    post_return(client, ecr_line(A["uan"], A["name"]), "PAY-EPS-1")          # August 2026: ₹1,250 to EPS
    body = {"account_link_id": A["account_link_id"], "scenario": "WRONGLY_ALLOWED", "from_month": MONTH, "to_month": MONTH,
            "notesheet_no": "NS/EPS/1", "remarks": "Joined in 2016 on ₹40,000: not eligible for EPS (G.S.R. 609(E))."}
    assert client.post(URL, json=body, headers=office(DA, "fo.da_accounts")).status_code == 428          # one-time code
    ws = work_out([{"wage_month": MONTH, "epf_wages_paise": 0, "eps_wages_paise": 0, "eps_paise": 125000, "ceiling_paise": 0, "eps_rate_bp": 833}],
                  "WRONGLY_ALLOWED", date.today(), lambda m: 825)
    r = client.post(URL, json=body, headers=office(DA, "fo.da_accounts", "propose-eps-rectification", A["account_link_id"]))
    assert r.status_code == 201, r.text
    case = r.json()["data"]
    assert case["state"] == "PROPOSED" and case["total_paise"] == ws["total_paise"] and case["worksheet"]["amount_paise"] == 125000
    assert client.post(URL, json=body, headers=office(DA, "fo.da_accounts", "propose-eps-rectification", A["account_link_id"])).status_code == 409
    rid = case["rectification_id"]
    approve = lambda who, role: client.post(f"{URL}/{rid}/approvals", json={"decision": "APPROVE", "note": "Checked against Form 11"},  # noqa: E731
                                            headers=office(who, role, "approve-eps-rectification", rid, ws["total_paise"]))
    assert approve(DA, "fo.da_accounts").status_code == 403
    r = approve(APFC, "fo.apfc")
    assert r.status_code == 200 and r.json()["data"]["state"] == "APPROVED", r.text
    lines = q(f"SELECT account_code, side, amount_paise, account_link_id, share FROM journal_lines WHERE journal_id='{r.json()['data']['journal_id']}' ORDER BY id")
    assert lines == [("AC10_EPS", "debit", ws["total_paise"], None, None), ("AC01_EPF", "credit", ws["total_paise"], A["account_link_id"], "employer")]
    events = {t: json.loads(p)["envelope"]["payload"] if isinstance(p, str) else p["envelope"]["payload"]
              for t, p in q("SELECT event_type, payload FROM outbox WHERE event_type IN ('LedgerAdjusted.v1', 'EpsRectified.v1')")}
    assert events["EpsRectified.v1"]["scenario"] == "WRONGLY_ALLOWED" and events["EpsRectified.v1"]["months"] == 1
    assert events["LedgerAdjusted.v1"]["appendix_type"] == "EPS_RECTIFICATION"
    # from now on the member ID's returns carry no pension wages
    later = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": "2026-09", "format": "ECR_TXT", "content": ecr_line(A["uan"], A["name"])},
                        headers=preparer()).json()["data"]["validation_report"]
    assert any(i["code"] == "E-EPS-NOT-ELIGIBLE" and i["auto_fixable"] for i in later["issues"]), later["issues"]
    entries = client.get("/api/v1/members/me/passbook", headers=hdr(A["subject"], "member", [], establishment=None)).json()["data"]["accounts"][0]["entries"]
    assert any(e["kind"] == "EPS_RECTIFICATION" and "returned to your PF" in e["description"] for e in entries)


def test_eps_wrongly_denied_moves_from_the_pf_to_the_pension_fund(ctx):
    client, q = ctx
    post_return(client, "\n".join([ecr_line(A["uan"], A["name"]), no_eps(B)]), "PAY-EPS-2")   # member B: no EPS, all 12% to EPF
    body = {"account_link_id": B["account_link_id"], "scenario": "WRONGLY_DENIED", "from_month": MONTH, "to_month": MONTH,
            "notesheet_no": "NS/EPS/2", "remarks": "Joined in 2019 on ₹12,000: eligible for EPS; the employer remitted none."}
    ws = work_out([{"wage_month": MONTH, "epf_wages_paise": 1500000, "eps_wages_paise": 0, "eps_paise": 0, "ceiling_paise": 1500000, "eps_rate_bp": 833}],
                  "WRONGLY_DENIED", date.today(), lambda m: 825)
    r = client.post(URL, json=body, headers=office(DA, "fo.da_accounts", "propose-eps-rectification", B["account_link_id"]))
    assert r.status_code == 201 and r.json()["data"]["worksheet"]["amount_paise"] == 125000, r.text
    rid = r.json()["data"]["rectification_id"]
    r = client.post(f"{URL}/{rid}/approvals", json={"decision": "APPROVE", "note": "Eligible: wages within the ceiling"},
                    headers=office(APFC, "fo.apfc", "approve-eps-rectification", rid, ws["total_paise"]))
    assert r.status_code == 200, r.text
    lines = q(f"SELECT account_code, side, account_link_id FROM journal_lines WHERE journal_id='{r.json()['data']['journal_id']}' ORDER BY id")
    assert lines == [("AC01_EPF", "debit", B["account_link_id"]), ("AC10_EPS", "credit", None)]
    nothing = client.post(URL, json={**body, "account_link_id": A["account_link_id"]},
                          headers=office(DA, "fo.da_accounts", "propose-eps-rectification", A["account_link_id"]))
    assert nothing.status_code == 422 and nothing.json()["type"] == "/problems/nothing-to-rectify"     # A's return already carries EPS
