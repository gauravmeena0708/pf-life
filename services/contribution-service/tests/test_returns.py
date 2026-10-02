"""Phase 2, slice 7a: supplementary and arrear returns after a posted regular return; cancelling an unpaid TRRN;
the office rejecting a return or a stuck payment; demands for late payment (14B / 7Q), a miscellaneous direct
challan and the knock-off (DA Compliance proposes, SS approves); administrative charges; the returns dashboard."""
import json

from tests.test_ecr_api import EST, MONTH, SEED, _deliver, approved, ctx, ecr_line, hdr, signatory  # noqa: F401

S = SEED["keycloak_subjects"]
DA, CASH, DA_C, SS = S["do-caseworker"], S["ro-cashier"], S["ro-da-compliance"], S["ro-ss"]
MEMBERS = SEED["members"]


def office(subject, role, step_up=None):
    return hdr(subject, role, [], step_up, establishment=None)


def submit(client, f, total):
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    r = client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                    headers=signatory(step, **{"Idempotency-Key": f"k-{f['filing_id']}", "If-Match": str(f["version"])}))
    assert r.status_code == 201, r.json()
    return r.json()["data"]["trrn"]


def pay(trrn, total, payment_id):
    from app.infra.messaging import handle_payment_confirmed
    _deliver(handle_payment_confirmed, {"payment_id": payment_id, "purpose": "CHALLAN", "reference_type": "trrn", "reference_id": trrn,
                                        "amount_paise": total, "mock": True}, "PaymentConfirmed.v1")


def file_return(client, content, kind):
    return client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": content, "type": kind},
                       headers=hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"]))


def regular_posted(client):
    f, total = approved(client)
    trrn = submit(client, f, total)
    pay(trrn, total, "PAY-REG")
    return f, total, trrn


def test_supplementary_and_arrear_returns_need_the_posted_regular_return(ctx):
    client, q = ctx
    supp = ecr_line(MEMBERS[4]["uan"], MEMBERS[4]["name"])
    early = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": MONTH, "format": "ECR_TXT", "content": supp, "type": "SUPPLEMENTARY"},
                        headers=hdr(S["emp-preparer"], "employer.operator", ["ecr.prepare"]))
    assert early.status_code == 409 and early.json()["type"] == "/problems/regular-return-not-posted"
    f, _, _ = regular_posted(client)
    assert q(f"SELECT state FROM ecr_filings WHERE id='{f['filing_id']}'")[0][0] == "POSTED"
    s = file_return(client, supp, "SUPPLEMENTARY").json()["data"]
    assert s["filing"]["type"] == "SUPPLEMENTARY" and s["validation_report"]["valid"], s["validation_report"]["issues"]
    assert not any(i["code"] == "W-MISSING-MEMBER" for i in s["validation_report"]["issues"])
    dup = file_return(client, ecr_line(MEMBERS[0]["uan"], MEMBERS[0]["name"]), "SUPPLEMENTARY").json()["data"]["validation_report"]
    assert any(i["code"] == "E-SUPP-ALREADY-FILED" for i in dup["issues"])
    arrear = file_return(client, ecr_line(MEMBERS[0]["uan"], MEMBERS[0]["name"]), "ARREAR").json()["data"]
    assert arrear["validation_report"]["valid"]
    missing = file_return(client, supp, "ARREAR").json()["data"]["validation_report"]
    assert any(i["code"] == "E-ARREAR-NOT-FILED" for i in missing["issues"])


def test_cancel_an_unpaid_trrn_and_the_office_rejects(ctx):
    client, q = ctx
    f, total = approved(client)
    trrn = submit(client, f, total)
    url = f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/cancellations"
    body = {"reason": "Wrong wage month selected"}
    assert client.post(url, json=body, headers=signatory()).status_code == 428
    r = client.post(url, json=body, headers=signatory({"action": "cancel-trrn", "resource_id": f["filing_id"], "amount_paise": total}))
    assert r.status_code == 200 and r.json()["data"]["state"] == "CANCELLED", r.json()
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='ChallanStatusChanged.v1'")
    assert json.loads(payload)["envelope"]["payload"] == {"trrn": trrn, "status": "CANCELLED", "reason": "Wrong wage month selected"}
    f2, total2 = approved(client)                                       # the wage month is free again
    submit(client, f2, total2)
    rej = f"/api/v1/office/ecr-filings/{f2['filing_id']}/rejections"
    done = client.post(rej, json={"reason": "Return for a closed member ID"}, headers=office(DA, "fo.da_accounts", {"action": "reject-ecr", "resource_id": f2["filing_id"]}))
    assert done.json()["data"]["state"] == "REJECTED"
    f3, total3 = approved(client)
    submit(client, f3, total3)
    stuck = client.post(f"/api/v1/office/ecr-filings/{f3['filing_id']}/payment-rejections", json={"reason": "Bank reports no credit after 3 days"},
                        headers=office(CASH, "fo.cash", {"action": "reject-ecr-payment", "resource_id": f3["filing_id"]}))
    assert stuck.json()["data"]["state"] == "PAYMENT_FAILED"
    assert q(f"SELECT status FROM challans WHERE filing_id='{f3['filing_id']}'")[0][0] == "FAILED"


def test_late_payment_raises_demands_paid_by_a_misc_challan_and_knocked_off(ctx):
    client, q = ctx
    regular_posted(client)                                               # 2026-08 paid after 15 September
    demands = client.get("/api/v1/employers/me/demands", headers=signatory()).json()["data"]
    kinds = {d["kind"]: d for d in demands["items"]}
    assert set(kinds) == {"DAMAGES_14B", "INTEREST_7Q"} and demands["open_paise"] > 0 and "days late" in kinds["DAMAGES_14B"]["working"]
    owed = demands["open_paise"]
    body = {"kind": "MISC_14B_7Q", "damages_14b_paise": kinds["DAMAGES_14B"]["amount_paise"], "interest_7q_paise": kinds["INTEREST_7Q"]["amount_paise"],
            "reason": "14B and 7Q for August 2026"}
    ch = client.post("/api/v1/employers/me/direct-challans", json=body, headers=signatory({"action": "raise-direct-challan", "resource_id": EST, "amount_paise": owed}))
    assert ch.status_code == 201, ch.json()
    trrn = ch.json()["data"]["trrn"]
    assert "ChallanGenerated.v1" in [e[0] for e in q("SELECT event_type FROM outbox")]
    ko = {"trrn": trrn, "demand_ids": [d["demand_id"] for d in demands["items"]]}
    step = {"action": "propose-knock-off", "resource_id": EST, "amount_paise": owed}
    unpaid = client.post(f"/api/v1/office/establishments/{EST}/damages-knock-offs", json=ko, headers=office(DA_C, "fo.da_compliance", step))
    assert unpaid.status_code == 422                                     # the challan is not paid yet
    pay(trrn, owed, "PAY-MISC")
    lines = q("SELECT account_code, side FROM journal_lines jl JOIN journals j ON j.id = jl.journal_id WHERE j.kind='DIRECT_CHALLAN'")
    assert sorted(lines) == [("BANK_COLLECTION", "debit"), ("DAMAGES_14B", "credit"), ("INTEREST_7Q", "credit")]
    proposed = client.post(f"/api/v1/office/establishments/{EST}/damages-knock-offs", json=ko, headers=office(DA_C, "fo.da_compliance", step)).json()["data"]
    assert proposed["state"] == "PROPOSED" and proposed["amount_paise"] == owed
    url = f"/api/v1/office/damages-knock-offs/{proposed['knock_off_id']}/approvals"
    decision = {"decision": "APPROVE", "note": "Challan amounts match the demands"}
    done = client.post(url, json=decision, headers=office(SS, "fo.ss", {"action": "approve-knock-off", "resource_id": proposed["knock_off_id"], "amount_paise": owed}))
    assert done.json()["data"]["state"] == "APPROVED"
    after = client.get("/api/v1/employers/me/demands", headers=signatory()).json()["data"]
    assert after["open_paise"] == 0 and {d["state"] for d in after["items"]} == {"KNOCKED_OFF"}


def test_admin_charges_challan_and_the_dashboard(ctx):
    client, q = ctx
    regular_posted(client)
    r = client.post("/api/v1/employers/me/direct-challans", json={"kind": "ADMIN_CHARGES", "admin_paise": 50000, "reason": "Inspection charges"},
                    headers=signatory({"action": "raise-direct-challan", "resource_id": EST, "amount_paise": 50000}))
    assert r.status_code == 201 and r.json()["data"]["breakdown_paise"] == {"AC02_ADMIN": 50000}
    assert client.post("/api/v1/employers/me/direct-challans", json={"kind": "ADMIN_CHARGES", "admin_paise": 50050, "reason": "Paise"},
                       headers=signatory({"action": "raise-direct-challan", "resource_id": EST, "amount_paise": 50050})).status_code == 422
    month = next(m for m in client.get("/api/v1/employers/me/returns/dashboard", headers=signatory()).json()["data"] if m["wage_month"] == MONTH)
    assert month["wage_month"] == MONTH and month["status"] == "PAID" and month["due_date"] == "2026-09-15" and month["paid_late"] is True


def test_demands_are_published_revised_under_vishwas_and_paid_directly(ctx):
    client, q = ctx
    regular_posted(client)
    import json as _json
    published = [_json.loads(p)["envelope"]["payload"] for (p,) in q("SELECT payload FROM outbox WHERE event_type='DemandStateChanged.v1'")]
    assert {p["kind"] for p in published} == {"DAMAGES_14B", "INTEREST_7Q"} and {p["state"] for p in published} == {"OPEN"}
    d14b = next(p for p in published if p["kind"] == "DAMAGES_14B")
    from app.infra.demands import on_demand_paid, on_demand_raised
    _deliver(on_demand_raised, {"demand_id": "DEM-VIS-1", "establishment_id": EST, "demand_type": "DAMAGES_14B_VISHWAS", "amount_paise": 100,
                                "supersedes_demand_ids": [d14b["demand_id"]], "working": "VISHWAS: 30% (illustrative)", "rule_version": "r"},
             "DemandRaised.v1")
    states = dict(q("SELECT demand_id, state FROM demands"))
    assert states[d14b["demand_id"]] == "WAIVED" and states["DEM-VIS-1"] == "OPEN"
    _deliver(on_demand_paid, {"payment_id": "PAY-DEM-1", "purpose": "DEMAND", "reference_type": "demand", "reference_id": "DEM-VIS-1",
                              "amount_paise": 100, "mock": True}, "PaymentConfirmed.v1")
    assert dict(q("SELECT demand_id, state FROM demands"))["DEM-VIS-1"] == "PAID"
    assert sorted(q("SELECT jl.account_code, jl.side FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id WHERE j.kind='DEMAND_PAYMENT'")) == [
        ("BANK_COLLECTION", "debit"), ("DAMAGES_14B", "credit")]


def test_a_7a_order_raises_dues_paid_into_their_accounts(ctx):
    """P2.11a: a 7A order's dues (DemandRaised.v1, DUES_7A) — paid directly, they are credited to the accounts the order split them into."""
    client, q = ctx
    import json as _json
    from app.infra.demands import on_demand_paid, on_demand_raised
    dues = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
             "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]
    _deliver(on_demand_raised, {"demand_id": "D7A-CMP-1", "establishment_id": EST, "demand_type": "DUES_7A", "amount_paise": 4500000,
                                "supersedes_demand_ids": [], "working": _json.dumps(dues), "rule_version": "r"}, "DemandRaised.v1")
    assert dict(q("SELECT demand_id, kind FROM demands"))["D7A-CMP-1"] == "DUES_7A"
    _deliver(on_demand_paid, {"payment_id": "PAY-7A-1", "purpose": "DEMAND", "reference_type": "demand", "reference_id": "D7A-CMP-1",
                              "amount_paise": 4500000, "mock": True}, "PaymentConfirmed.v1")
    assert dict(q("SELECT demand_id, state FROM demands"))["D7A-CMP-1"] == "PAID"
    lines = sorted(q("SELECT jl.account_code, jl.side, jl.amount_paise FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id "
                     "WHERE j.business_key='PAY-7A-1'"))
    assert lines == [("AC01_EPF", "credit", 2820000), ("AC02_ADMIN", "credit", 90000), ("AC10_EPS", "credit", 1500000),
                     ("AC21_EDLI", "credit", 90000), ("BANK_COLLECTION", "debit", 4500000)]


def test_interest_7q_demand_replaces_auto_calculated_demand(ctx):
    """A 7Q interest order (DemandRaised.v1, INTEREST_7Q) replaces an open auto-calculated 7Q interest demand."""
    client, q = ctx
    regular_posted(client)
    from app.infra.demands import on_demand_raised
    d7q_id = dict(q("SELECT kind, demand_id FROM demands WHERE state='OPEN'"))["INTEREST_7Q"]
    _deliver(on_demand_raised, {"demand_id": "DEM-7Q-ORD-1", "establishment_id": EST, "demand_type": "INTEREST_7Q", "amount_paise": 250000,
                                "supersedes_demand_ids": [d7q_id], "working": "7Q order: interest revised", "rule_version": "r"},
             "DemandRaised.v1")
    demands = {row[0]: row for row in q("SELECT demand_id, kind, state, settled_by, amount_paise FROM demands")}
    assert demands["DEM-7Q-ORD-1"][1] == "INTEREST_7Q"
    assert demands["DEM-7Q-ORD-1"][2] == "OPEN"
    assert demands["DEM-7Q-ORD-1"][4] == 250000
    assert demands[d7q_id][2] == "WAIVED"
    assert demands[d7q_id][3] == "DEM-7Q-ORD-1"


def test_amount_zero_withdraws_dues_7a_demand(ctx):
    """An order set aside with amount 0 (or withdraw true) marks superseded OPEN demands WITHDRAWN without creating a new row."""
    client, q = ctx
    import json as _json
    from app.infra.demands import on_demand_raised
    dues = [{"wage_month": "2025-04", "ac1_employee_paise": 2160000, "ac1_employer_paise": 660000, "ac10_pension_paise": 1500000,
             "ac21_edli_paise": 90000, "ac2_admin_paise": 90000}]
    _deliver(on_demand_raised, {"demand_id": "D7A-CMP-1", "establishment_id": EST, "demand_type": "DUES_7A", "amount_paise": 4500000,
                                "supersedes_demand_ids": [], "working": _json.dumps(dues), "rule_version": "r"}, "DemandRaised.v1")
    assert dict(q("SELECT demand_id, state FROM demands"))["D7A-CMP-1"] == "OPEN"
    _deliver(on_demand_raised, {"demand_id": "D7A-WITHDRAW-1", "establishment_id": EST, "demand_type": "DUES_7A", "amount_paise": 0,
                                "supersedes_demand_ids": ["D7A-CMP-1"], "working": "Order set aside", "rule_version": "r"}, "DemandRaised.v1")
    demands = dict(q("SELECT demand_id, state FROM demands"))
    assert "D7A-WITHDRAW-1" not in demands
    assert demands["D7A-CMP-1"] == "WITHDRAWN"
    assert dict(q("SELECT demand_id, settled_by FROM demands"))["D7A-CMP-1"] == "D7A-WITHDRAW-1"
    published = [_json.loads(p)["envelope"]["payload"] for (p,) in q("SELECT payload FROM outbox WHERE event_type='DemandStateChanged.v1'")]
    assert "D7A-WITHDRAW-1" not in {p["demand_id"] for p in published}
    withdrawn = next(p for p in published if p["demand_id"] == "D7A-CMP-1" and p["state"] == "WITHDRAWN")
    assert withdrawn["kind"] == "DUES_7A"
    _deliver(on_demand_raised, {"demand_id": "D7A-CMP-2", "establishment_id": EST, "demand_type": "DUES_7A", "amount_paise": 100000,
                                "supersedes_demand_ids": [], "working": "[]", "rule_version": "r"}, "DemandRaised.v1")
    _deliver(on_demand_raised, {"demand_id": "D7A-WITHDRAW-2", "establishment_id": EST, "demand_type": "DUES_7A", "amount_paise": 100000,
                                "supersedes_demand_ids": ["D7A-CMP-2"], "withdraw": True}, "DemandRaised.v1")
    demands2 = dict(q("SELECT demand_id, state FROM demands"))
    assert "D7A-WITHDRAW-2" not in demands2
    assert demands2["D7A-CMP-2"] == "WITHDRAWN"

