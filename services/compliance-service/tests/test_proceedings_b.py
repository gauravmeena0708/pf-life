"""Phase 2, slice 11b (Compliance Manual): the 14B / 7Q proceeding from the auto-calculated demands, review under 7B after
the next-higher officer's view, setting aside an ex-parte order, 7C for an escaped amount, administrative scrutiny."""
import json
from datetime import UTC, datetime

from tests.test_compliance import EST, S, ctx, demand, hdr  # noqa: F401
from tests.test_proceedings import APFC, BASE, DA, OIC, OWNER, RPFC2, SS, as_, inspected, register, summoned

DUES = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
         "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]
OWNER_H = hdr(OWNER, "employer.owner", establishment=EST)


def heard(client, case, present=True):
    summoned(client, case)
    r = client.post(f"{BASE}/cases/{case}/hearings", json={"held_at": datetime.now(UTC).isoformat(), "employer_present": present,
                                                           "eo_present": True, "proceedings": "Heard; reserved", "concluded": True}, headers=as_(APFC))
    assert r.status_code == 200, r.json()


def ordered_7a(client, present=True, total=4500000):
    case = register(client, 120, inspected(client)).json()["data"]["case_id"]
    heard(client, case, present)
    r = client.post(f"{BASE}/cases/{case}/orders", json={"kind": "7A", "dues": DUES, "reasoning": "Muster roll", "ex_parte": not present},
                    headers=as_(APFC, {"action": "pass-order", "resource_id": case, "amount_paise": total}))
    assert r.status_code == 200, r.json()
    return case


def raised(q):
    return [json.loads(p)["envelope"]["payload"] for (p,) in q("SELECT payload FROM outbox WHERE event_type='DemandRaised.v1' ORDER BY id")]


def test_a_desk_review_notice_takes_every_open_demand(ctx):
    client, _, deliver = ctx
    demand(deliver, "DEM-14B-9", "DAMAGES_14B", 300000)
    demand(deliver, "DEM-7Q-9", "INTEREST_7Q", 120000)
    r = client.post(f"{BASE}/cases", json={"establishment_id": EST, "kind": "INQUIRY_14B", "contributory_uans": 40, "note": "Periodic desk review"}, headers=as_(DA))
    assert r.status_code == 201 and set(r.json()["data"]["demand_ids"]) >= {"DEM-14B-9", "DEM-7Q-9"}, r.json()


def test_damages_and_interest_proceeding(ctx):
    client, q, deliver = ctx
    demand(deliver, "DEM-14B-1", "DAMAGES_14B", 300000)
    demand(deliver, "DEM-7Q-1", "INTEREST_7Q", 120000)
    body = {"establishment_id": EST, "kind": "INQUIRY_14B", "demand_ids": ["DEM-14B-1", "DEM-7Q-1"], "contributory_uans": 120,
            "note": "Periodic desk review: delayed remittances"}
    assert client.post(f"{BASE}/cases", json=body, headers=as_(SS)).status_code == 422                    # the DA drafts it
    draft = client.post(f"{BASE}/cases", json=body, headers=as_(DA))
    assert draft.status_code == 201 and draft.json()["data"]["state"] == "NOTICE_DRAFTED", draft.json()
    case = draft.json()["data"]["case_id"]
    assert client.post(f"{BASE}/cases", json=body, headers=as_(DA)).status_code == 409                    # the demands are noticed already
    assert client.post(f"{BASE}/cases", json={**body, "demand_ids": []}, headers=as_(DA)).status_code == 422   # nothing left to notice
    assert client.post(f"{BASE}/cases/{case}/approvals", json={"note": "ok"}, headers=as_(APFC)).status_code == 409   # SS first
    assert client.post(f"{BASE}/cases/{case}/approvals", json={"note": "Endorsed"}, headers=as_(SS)).status_code == 200
    approved = client.post(f"{BASE}/cases/{case}/approvals", json={"note": "Approved"}, headers=as_(APFC)).json()["data"]
    assert approved["state"] == "REGISTERED" and approved["diary_no"].startswith("EPR/") and approved["officer_rank"] == "APFC"
    heard(client, case)
    step = lambda amount: as_(APFC, {"action": "pass-order", "resource_id": case, "amount_paise": amount})  # noqa: E731
    url = f"{BASE}/cases/{case}/orders"
    assert client.post(url, json={"kind": "7A", "dues": DUES, "reasoning": "x", "ex_parte": False}, headers=step(4500000)).status_code == 422
    assert client.post(url, json={"kind": "14B", "levies": [{"demand_id": "DEM-14B-1", "amount_paise": 400000}], "reasoning": "x",
                                  "ex_parte": False}, headers=step(400000)).status_code == 422                # more than worked out
    reduced = client.post(url, json={"kind": "14B", "levies": [{"demand_id": "DEM-14B-1", "amount_paise": 200000}],
                                     "reasoning": "Delay owing to a bank strike, proved", "ex_parte": False}, headers=step(200000))
    assert reduced.status_code == 200 and "DAMAGES UNDER SECTION 14B" in reduced.json()["data"]["text"], reduced.json()
    assert client.post(url, json={"kind": "7Q", "levies": [{"demand_id": "DEM-7Q-1", "amount_paise": 100000}], "reasoning": "x",
                                  "ex_parte": False}, headers=step(100000)).status_code == 422                # 7Q cannot be varied
    interest = client.post(url, json={"kind": "7Q", "levies": [{"demand_id": "DEM-7Q-1", "amount_paise": 120000}], "reasoning": "Statutory",
                                      "ex_parte": False}, headers=step(120000))
    assert interest.status_code == 200
    events = raised(q)
    assert [(e["demand_type"], e["amount_paise"], e["supersedes_demand_ids"]) for e in events] == [
        ("DAMAGES_14B", 200000, ["DEM-14B-1"]), ("INTEREST_7Q", 120000, ["DEM-7Q-1"])]
    assert q(f"SELECT state FROM inquiries WHERE case_id='{case}'")[0][0] == "ORDERED"


def test_review_needs_the_next_higher_view_and_replaces_the_order(ctx):
    client, q, _ = ctx
    case = ordered_7a(client)
    apply = client.post(f"/api/v1/employers/me/proceedings/{case}/applications",
                        json={"kind": "REVIEW_7B", "grounds": "NEW_EVIDENCE", "text": "Wage register found after the order"}, headers=OWNER_H)
    assert apply.status_code == 201, apply.json()
    app_id = apply.json()["data"]["application_id"]
    assert client.post(f"/api/v1/employers/me/proceedings/{case}/applications", json={"kind": "SET_ASIDE", "grounds": "NOT_SERVED",
                       "text": "x"}, headers=OWNER_H).status_code == 409                                     # one at a time
    review = {"application_id": app_id, "view_by_rank": "RPFC-I", "view_note": "x", "decision": "GRANTED", "note": "New evidence"}
    step = as_(APFC, {"action": "review-order", "resource_id": case})
    assert client.post(f"{BASE}/cases/{case}/reviews-7b", json=review, headers=step).status_code == 422     # an APFC asks the RPFC-II
    granted = client.post(f"{BASE}/cases/{case}/reviews-7b", json={**review, "view_by_rank": "RPFC-II", "view_note": "Fit for review"}, headers=step)
    assert granted.status_code == 200 and granted.json()["data"]["state"] == "REGISTERED", granted.json()
    heard(client, case)
    revised = [{**DUES[0], "ac1_employee_paise": 1080000}]
    r = client.post(f"{BASE}/cases/{case}/orders", json={"kind": "7A", "dues": revised, "reasoning": "Half were contract workers", "ex_parte": False},
                    headers=as_(APFC, {"action": "pass-order", "resource_id": case, "amount_paise": 3420000}))
    assert r.status_code == 200 and "under review" in r.json()["data"]["text"]
    last = raised(q)[-1]
    assert last["demand_id"] == f"D7A-{case}-R1" and last["supersedes_demand_ids"] == [f"D7A-{case}"] and last["amount_paise"] == 3420000
    mine = next(p for p in client.get("/api/v1/employers/me/proceedings", headers=OWNER_H).json()["data"] if p["case_id"] == case)
    assert mine["order"]["detail"]["total_paise"] == 3420000 and mine["applications"][0]["detail"]["status"] == "GRANTED"


def test_ex_parte_order_set_aside_on_application(ctx):
    client, q, _ = ctx
    present = ordered_7a(client)
    assert client.post(f"/api/v1/employers/me/proceedings/{present}/applications", json={"kind": "SET_ASIDE", "grounds": "NOT_SERVED",
                       "text": "x"}, headers=OWNER_H).status_code == 422                                     # not an ex-parte order
    case = ordered_7a(client, present=False)
    app_id = client.post(f"/api/v1/employers/me/proceedings/{case}/applications", json={"kind": "SET_ASIDE", "grounds": "NOT_SERVED",
                         "text": "The notice went to an old address"}, headers=OWNER_H).json()["data"]["application_id"]
    done = client.post(f"{BASE}/cases/{case}/set-asides", json={"application_id": app_id, "decision": "SET_ASIDE", "note": "Not duly served"},
                       headers=as_(APFC, {"action": "set-aside-order", "resource_id": case}))
    assert done.status_code == 200 and done.json()["data"]["state"] == "REGISTERED", done.json()
    withdrawal = raised(q)[-1]
    assert withdrawal["amount_paise"] == 0 and withdrawal["supersedes_demand_ids"] == [f"D7A-{case}"]


def test_escaped_amount_reopens_under_7c(ctx):
    client, q, _ = ctx
    case = ordered_7a(client)
    r = client.post(f"{BASE}/cases/{case}/escaped-assessments-7c", json={"reason_type": "INFORMATION_IN_POSSESSION",
                    "reason": "GSTN shows 20 more workers in the period"}, headers=as_(APFC, {"action": "escaped-assessment", "resource_id": case}))
    assert r.status_code == 201, r.json()
    child = r.json()["data"]
    assert child["section"] == "7C" and child["parent_case_id"] == case and child["officer_subject"] == APFC and child["diary_no"].startswith("EPR/")
    heard(client, child["case_id"])
    o = client.post(f"{BASE}/cases/{child['case_id']}/orders", json={"kind": "7A", "dues": DUES, "reasoning": "Escaped wages", "ex_parte": False},
                    headers=as_(APFC, {"action": "pass-order", "resource_id": child["case_id"], "amount_paise": 4500000}))
    assert o.status_code == 200 and "SECTION 7C" in o.json()["data"]["text"]
    assert raised(q)[-1]["demand_id"] == f"D7C-{child['case_id']}" and raised(q)[-1]["supersedes_demand_ids"] == []


def test_scrutiny_by_the_officer_next_above(ctx):
    client, _, _ = ctx
    case = ordered_7a(client)
    month = datetime.now(UTC).strftime("%Y-%m")
    listed = client.get(f"{BASE}/scrutinies?month={month}", headers=as_(RPFC2)).json()["data"]
    assert [x["case_id"] for x in listed] == [case] and listed[0]["scrutiny_due"].endswith("-15")
    assert client.post(f"{BASE}/cases/{case}/scrutinies", json={"observations": "x"}, headers=as_(APFC)).status_code == 403
    assert client.post(f"{BASE}/cases/{case}/scrutinies", json={"observations": "x"}, headers=as_(OIC)).status_code == 403
    ok = client.post(f"{BASE}/cases/{case}/scrutinies", json={"observations": "Month-wise dues recorded; reasons adequate"}, headers=as_(RPFC2))
    assert ok.status_code == 200 and ok.json()["data"]["by_rank"] == "RPFC-II"
    assert client.post(f"{BASE}/cases/{case}/scrutinies", json={"observations": "again"}, headers=as_(RPFC2)).status_code == 409
