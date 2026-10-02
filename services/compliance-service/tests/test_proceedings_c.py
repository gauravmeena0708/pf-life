"""Phase 2, slice 11c: a 26B membership dispute, an appeal under s.7-I with the s.7-O pre-deposit and the Tribunal's
waiver, the legal case register and the effect of orders (remand, partial allowance, stay), and prosecution."""
import asyncio
import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from tests.test_compliance import EST, S, ctx, hdr  # noqa: F401
from tests.test_proceedings import APFC, BASE, DA, EO, OIC, OWNER, RPFC2, SS, as_
from tests.test_proceedings_b import OWNER_H, ordered_7a, raised, summoned

LEGAL_SUBJECT = S["ro-legal"]
LEGAL_BASE = "/api/v1/office/legal"


def legal(step_up=None):
    return hdr(LEGAL_SUBJECT, "fo.legal", step_up)


def officer(subject, step_up=None):
    return hdr(subject, {APFC: "fo.apfc", RPFC2: "fo.apfc", OIC: "fo.oic", EO: "fo.eo"}[subject], step_up)


def sql(statement):
    import app.infra.db as db

    async def run():
        async with db.engine().begin() as c:
            await c.execute(text(statement))
    asyncio.run(run())


def test_membership_dispute_under_26b(ctx):
    client, q, _ = ctx
    body = {"establishment_id": EST, "trigger": "EMPLOYEE_COMPLAINT", "contributory_uans": 40, "note": "Two apprentices say they are workers",
            "employees": [{"name": "SYNTH WORKER A", "claimed_from": "2025-01-01"}, {"name": "SYNTH WORKER B", "claimed_from": "2025-03-01"}]}
    url = f"{BASE}/membership-disputes"
    assert client.post(url, json=body, headers=as_(SS)).status_code == 428                                      # one-time code
    r = client.post(url, json=body, headers=as_(SS, {"action": "register-26b", "resource_id": EST}))
    assert r.status_code == 201, r.json()
    case = r.json()["data"]
    assert case["section"] == "26B" and case["officer_rank"] == "RPFC-II" and case["officer_subject"] == RPFC2     # never below RPFC-II
    summoned(client, case["case_id"], officer=RPFC2)
    assert client.post(f"{BASE}/cases/{case['case_id']}/hearings", json={"held_at": datetime.now(UTC).isoformat(), "employer_present": True,
                       "eo_present": True, "proceedings": "Heard", "concluded": True}, headers=officer(RPFC2)).status_code == 200
    step = officer(RPFC2, {"action": "pass-order", "resource_id": case["case_id"], "amount_paise": 0})
    one = [{"name": "SYNTH WORKER A", "eligible": True, "from_date": "2025-01-01"}]
    order_url = f"{BASE}/cases/{case['case_id']}/orders"
    assert client.post(order_url, json={"kind": "7A", "dues": [], "reasoning": "x", "ex_parte": False}, headers=step).status_code == 422
    assert client.post(order_url, json={"kind": "26B", "decisions": one, "reasoning": "x", "ex_parte": False}, headers=step).status_code == 422
    both = one + [{"name": "SYNTH WORKER B", "eligible": False}]
    done = client.post(order_url, json={"kind": "26B", "decisions": both, "reasoning": "A works on the shop floor; B is a genuine apprentice",
                                        "ex_parte": False}, headers=step)
    assert done.status_code == 200 and "PARA 26B" in done.json()["data"]["text"] and "a member from 2025-01-01" in done.json()["data"]["text"]
    assert not [e for e in raised(q) if e["demand_id"].startswith("D") and case["case_id"] in e["demand_id"]]      # 26B raises no demand


def test_appeal_pre_deposit_waiver_and_remand(ctx):
    client, q, _ = ctx
    case = ordered_7a(client)
    url = f"{BASE}/cases/{case}/appeals"
    filed = {"case_no": "ATA-101/2026", "filed_on": date.today().isoformat()}
    assert client.post(url, json=filed, headers=as_(APFC)).status_code == 403                                   # the Legal Cell
    r = client.post(url, json=filed, headers=legal())
    assert r.status_code == 201, r.json()
    appeal = r.json()["data"]
    assert appeal["amount_paise"] == 4500000 and appeal["pre_deposit_required_paise"] == 3375000 and appeal["heard"] is False
    assert client.post(url, json=filed, headers=legal()).status_code == 409
    assert client.post(f"/api/v1/employers/me/proceedings/{case}/applications", json={"kind": "REVIEW_7B", "grounds": "NEW_EVIDENCE",
                       "text": "x"}, headers=OWNER_H).status_code == 409                                         # no review once appealed
    order = {"order_date": date.today().isoformat(), "outcome": "REMANDED", "note": "Decide afresh on the contract workers"}
    assert client.post(f"{LEGAL_BASE}/cases/{appeal['legal_case_id']}/orders", json=order, headers=legal()).status_code == 422   # not heard yet
    deposit = {"amount_paise": 2250000, "reference": "TRRN-PD-1", "deposited_on": date.today().isoformat()}
    dep_url = f"{url}/{appeal['legal_case_id']}/pre-deposits"
    assert client.post(dep_url, json=deposit, headers=legal()).json()["data"]["heard"] is False
    assert client.post(dep_url, json=deposit, headers=legal()).json()["data"]["pre_deposited_paise"] == 2250000  # recorded once
    waiver = {"percent": 50, "tribunal_order_ref": "ATA-101/2026 order of the day", "order_date": date.today().isoformat()}
    w_url = f"{url}/{appeal['legal_case_id']}/pre-deposit-waivers"
    assert client.post(w_url, json=waiver, headers=legal()).status_code == 428
    reduced = client.post(w_url, json=waiver, headers=legal({"action": "record-pre-deposit-waiver", "resource_id": appeal["legal_case_id"]}))
    assert reduced.json()["data"]["pre_deposit_required_paise"] == 2250000 and reduced.json()["data"]["heard"] is True
    remand = client.post(f"{LEGAL_BASE}/cases/{appeal['legal_case_id']}/orders", json=order, headers=legal())
    assert remand.status_code == 200 and remand.json()["data"]["effect"] == "remanded to the RPFC-II", remand.json()
    state, rank, subject = q(f"SELECT state, officer_rank, officer_subject FROM inquiries WHERE case_id='{case}'")[0]
    assert (state, rank, subject) == ("REGISTERED", "RPFC-II", RPFC2)                                            # one level higher (2.9)
    assert raised(q)[-1]["amount_paise"] == 0 and raised(q)[-1]["supersedes_demand_ids"] == [f"D7A-{case}"]


def test_partly_allowed_stay_and_the_time_to_appeal(ctx):
    client, q, _ = ctx
    case = ordered_7a(client)
    sql(f"UPDATE inquiries SET ordered_at='{(datetime.now(UTC) - timedelta(days=70)).isoformat()}' WHERE case_id='{case}'")
    url = f"{BASE}/cases/{case}/appeals"
    late = {"case_no": "ATA-102/2026", "filed_on": date.today().isoformat()}
    assert client.post(url, json=late, headers=legal()).status_code == 422                                      # out of time
    appeal = client.post(url, json={**late, "delay_condonation": True}, headers=legal()).json()["data"]
    assert appeal["delay_condonation"] is True
    ord_url = f"{LEGAL_BASE}/cases/{appeal['legal_case_id']}/orders"
    stay = client.post(ord_url, json={"order_date": date.today().isoformat(), "outcome": "INTERIM_STAY", "note": "Recovery stayed"}, headers=legal())
    assert stay.json()["data"]["stayed"] is True
    client.post(f"{url}/{appeal['legal_case_id']}/pre-deposits", json={"amount_paise": 3375000, "reference": "TRRN-PD-2",
                "deposited_on": date.today().isoformat()}, headers=legal())
    partly = {"order_date": date.today().isoformat(), "outcome": "PARTLY_ALLOWED", "note": "Half the workers were the contractor's"}
    assert client.post(ord_url, json=partly, headers=legal()).status_code == 422                                # the amount left payable
    done = client.post(ord_url, json={**partly, "revised_amount_paise": 2000000}, headers=legal())
    assert done.status_code == 200 and done.json()["data"]["state"] == "DECIDED" and done.json()["data"]["stayed"] is False
    last = raised(q)[-1]
    assert last["amount_paise"] == 2000000 and last["supersedes_demand_ids"] == [f"D7A-{case}"]
    assert client.post(ord_url, json={**partly, "revised_amount_paise": 1}, headers=legal()).status_code == 409   # decided


def test_register_writ_and_list(ctx):
    client, _, _ = ctx
    r = client.post(f"{LEGAL_BASE}/cases", json={"establishment_id": EST, "kind": "WRIT", "forum": "High Court of Delhi", "case_no": "WP(C) 77/2026",
                                                 "filed_on": date.today().isoformat()}, headers=legal())
    assert r.status_code == 201
    wid = r.json()["data"]["legal_case_id"]
    assert client.post(f"{LEGAL_BASE}/cases/{wid}/orders", json={"order_date": date.today().isoformat(), "outcome": "CONVICTED", "note": "x"},
                       headers=legal()).status_code == 422                                                       # writs are not prosecutions
    listed = client.get(f"{LEGAL_BASE}/cases?kind=WRIT", headers=legal()).json()["data"]
    assert [c["legal_case_id"] for c in listed] == [wid]
    assert client.get(f"{LEGAL_BASE}/cases", headers=hdr(OWNER, "employer.owner", establishment=EST)).status_code == 403


def test_prosecution_from_notice_to_conviction(ctx):
    client, q, _ = ctx
    case = client.post(f"{BASE}/cases", json={"establishment_id": EST, "kind": "NON_FILING", "wage_months": ["2026-07"], "amount_paise": 0,
                                              "note": "No return for July 2026"}, headers=as_(DA)).json()["data"]["case_id"]
    url = f"{BASE}/cases/{case}/prosecutions"
    body = {"offence": "NON_FILING_RETURNS", "particulars": "Returns for July 2026 not filed despite notices"}
    step = as_(APFC, {"action": "issue-prosecution-scn", "resource_id": case})
    r = client.post(url, json=body, headers=step)
    assert r.status_code == 201, r.json()
    pid = r.json()["data"]["prosecution_id"]
    assert client.post(url, json={**body, "offence": "NON_PAYMENT"}, headers=step).status_code == 422           # assess under 7A first
    steps = f"{BASE}/prosecutions/{pid}/steps"
    assert client.post(steps, json={"step": "SANCTION", "note": "x"}, headers=officer(OIC)).status_code == 409   # reply time not over
    mine = client.get("/api/v1/employers/me/prosecutions", headers=OWNER_H).json()["data"]
    assert mine[0]["prosecution_id"] == pid and "created_by" not in mine[0]
    reply = client.post(f"/api/v1/employers/me/prosecutions/{pid}/replies", json={"text": "The return was delayed by a software failure"}, headers=OWNER_H)
    assert reply.json()["data"]["state"] == "REPLIED"
    assert client.post(steps, json={"step": "SANCTION", "note": "x"}, headers=as_(APFC)).status_code == 403
    assert client.post(steps, json={"step": "SANCTION", "note": "Reply not satisfactory"}, headers=officer(OIC)).json()["data"]["state"] == "SANCTIONED"
    assert client.post(steps, json={"step": "COMPLAINT", "note": "x"}, headers=officer(EO)).status_code == 422
    filed = client.post(steps, json={"step": "COMPLAINT", "note": "Filed", "court": "Court of the CJM, Delhi", "complaint_no": "CC 55/2026"},
                        headers=officer(EO)).json()["data"]
    assert filed["state"] == "COMPLAINT_FILED" and filed["legal_case_id"]
    assert client.post(steps, json={"step": "DROP", "note": "x"}, headers=as_(APFC)).status_code == 409
    verdict = client.post(f"{LEGAL_BASE}/cases/{filed['legal_case_id']}/orders", json={"order_date": date.today().isoformat(),
                          "outcome": "CONVICTED", "note": "Fine imposed"}, headers=legal())
    assert verdict.status_code == 200
    assert q(f"SELECT state FROM prosecutions WHERE prosecution_id='{pid}'")[0][0] == "CONVICTED"
    kinds = [json.loads(p)["envelope"]["payload"]["step"] for (p,) in q("SELECT payload FROM outbox WHERE event_type='ProsecutionStepTaken.v1'")]
    assert kinds == ["SCN_ISSUED", "SANCTION", "COMPLAINT"]
