"""Phase 2, slice 11d (Recovery Manual): the certificate on an order left unpaid, the demand notice and its 15 days,
attachment and sale, the 8F notice to a bank, instalments, the defaulter's payment closing it, arrest only after a notice
to show cause, a court's stay, the employer's view and the HO reports."""
import json
from datetime import date

from tests.test_compliance import S, ctx, hdr  # noqa: F401
from tests.test_proceedings import APFC, BASE, OIC, as_
from tests.test_proceedings_b import ordered_7a, raised  # noqa: F401
from tests.test_proceedings_c import legal

SEEDED, ENG = "CMP-SEED-0002", "EST-DEMO-0002"
RO = S["ro-recovery"]
REC = "/api/v1/office/recovery"


def ro(step_up=None):
    return hdr(RO, "fo.recovery_officer", step_up)


def certified(client):
    r = client.post(f"{BASE}/cases/{SEEDED}/recovery-certificates", json={"note": "Order of 10 June 2026 unpaid"},
                    headers=as_(APFC, {"action": "issue-recovery-certificate", "resource_id": SEEDED}))
    assert r.status_code == 201, r.json()
    return r.json()["data"]


def realisations(q):
    return [json.loads(p)["envelope"]["payload"] for (p,) in q("SELECT payload FROM outbox WHERE event_type='RecoveryRealised.v1' ORDER BY id")]


def test_certificate_notice_attachment_sale_8f_instalments_payment(ctx):
    client, q, _ = ctx
    fresh = ordered_7a(client)
    assert client.post(f"{BASE}/cases/{fresh}/recovery-certificates", json={"note": "x"},
                       headers=as_(APFC, {"action": "issue-recovery-certificate", "resource_id": fresh})).status_code == 409   # 15 days not over
    rc = certified(client)
    assert rc["amount_paise"] == 3000000 and rc["state"] == "CERTIFIED" and rc["recovery_officer"] == RO
    assert client.post(f"{BASE}/cases/{SEEDED}/recovery-certificates", json={"note": "x"},
                       headers=as_(APFC, {"action": "issue-recovery-certificate", "resource_id": SEEDED})).status_code == 409
    rid = rc["recovery_case_id"]
    attach = {"kind": "MOVABLE", "description": "Two lathes", "value_paise": 1500000}
    step = ro({"action": "attach-property", "resource_id": rid})
    assert client.post(f"{REC}/{rid}/attachments", json=attach, headers=step).status_code == 409                # notice first
    notice = client.post(f"{REC}/{rid}/demand-notices", headers=ro()).json()["data"]
    assert notice["state"] == "NOTICE_SERVED" and notice["pay_by"]
    assert client.post(f"{REC}/{rid}/attachments", json=attach, headers=step).status_code == 409                # 15 days not run
    att = client.post(f"{REC}/{rid}/attachments", json={**attach, "urgent_reason": "Machinery being moved out at night"}, headers=step)
    assert att.status_code == 201, att.json()
    att_id = next(a for a in att.json()["data"]["actions"] if a["kind"] == "ATTACHMENT")["detail"]["attachment_id"]
    sale = {"attachment_id": att_id, "reserve_price_paise": 1200000, "sale_price_paise": 1000000, "buyer": "Synthetic Traders"}
    sale_step = lambda amount: ro({"action": "sell-property", "resource_id": rid, "amount_paise": amount})  # noqa: E731
    assert client.post(f"{REC}/{rid}/sales", json=sale, headers=sale_step(1000000)).status_code == 422          # below the reserve
    sold = client.post(f"{REC}/{rid}/sales", json={**sale, "sale_price_paise": 1300000}, headers=sale_step(1300000)).json()["data"]
    assert sold["realised_paise"] == 1300000 and sold["surplus_to_defaulter_paise"] == 0
    g = client.post(f"{BASE}/cases/{SEEDED}/recovery-8f", json={"garnishee": "BANK", "name": "Demo Bank", "reference": "AC-0002-CURRENT",
                    "amount_paise": 500000}, headers=as_(APFC, {"action": "garnishee-8f", "resource_id": SEEDED, "amount_paise": 500000}))
    assert g.status_code == 200 and g.json()["data"]["realised_paise"] == 1800000, g.json()
    inst = {"count": 73, "first_due": "2026-11-01", "note": "Hardship", "bank_guarantee_paise": 200000, "bank_guarantee_ref": "BG-0002-1"}
    assert client.post(f"{REC}/{rid}/instalments", json=inst, headers=as_(OIC)).status_code == 422             # at most 72
    assert client.post(f"{REC}/{rid}/instalments", json={**inst, "count": 40}, headers=as_(OIC)).json()["type"] == "/problems/beyond-powers"
    assert client.post(f"{REC}/{rid}/instalments", json={**inst, "count": 6, "bank_guarantee_paise": 100000},
                       headers=as_(OIC)).json()["type"] == "/problems/guarantee"                                    # one instalment is ₹2,000
    assert client.post(f"{REC}/{rid}/instalments", json={**inst, "count": 6}, headers=as_(OIC)).json()["data"]["state"] == "INSTALMENTS"
    assert client.post(f"{REC}/{rid}/attachments", json={**attach, "urgent_reason": "x"}, headers=step).status_code == 409   # instalments run
    paid = client.post(f"{REC}/{rid}/payments", json={"amount_paise": 1200000, "reference": "TRRN-RC-1", "mode": "INSTALMENT"}, headers=ro()).json()["data"]
    assert paid["state"] == "CLOSED" and paid["outstanding_paise"] == 0
    assert [(e["mode"], e["amount_paise"]) for e in realisations(q)] == [("SALE", 1300000), ("GARNISHEE_8F", 500000), ("INSTALMENT", 1200000)]
    assert all(e["demand_ids"] == ["D7A-CMP-SEED-0002"] for e in realisations(q))


def test_arrest_needs_a_show_cause_and_a_stay_halts_recovery(ctx):
    client, _, _ = ctx
    rid = certified(client)["recovery_case_id"]
    client.post(f"{REC}/{rid}/demand-notices", headers=ro())
    url, step = f"{REC}/{rid}/arrest-warrants", ro({"action": "arrest-defaulter", "resource_id": rid})
    detention = {"step": "DETENTION_ORDER", "ground": "MEANS_BUT_REFUSES", "reasons": "Pays salaries, not the dues"}
    import app.api.recovery as recovery_module
    from datetime import UTC, datetime, timedelta
    later = datetime.now(UTC) + timedelta(days=20)
    recovery_module.now = lambda: later                                    # the 15 days of the notice have run
    try:
        assert client.post(url, json=detention, headers=step).status_code == 422                                  # show cause first
        assert client.post(url, json={"step": "WARRANT", "ground": "NON_APPEARANCE", "reasons": "x"}, headers=step).status_code == 422
        assert client.post(url, json={"step": "SHOW_CAUSE", "hearing_on": "2026-11-10", "reasons": "EPFCP-25"}, headers=step).status_code == 201
        assert client.post(url, json=detention, headers=step).status_code == 201
        assert client.post(url, json={"step": "RELEASED", "ground": "PAID", "reasons": "Paid the arrears"}, headers=step).status_code == 201
        appeal = client.post(f"{BASE}/cases/{SEEDED}/appeals", json={"case_no": "ATA-9/2026", "filed_on": date.today().isoformat(),
                             "delay_condonation": True}, headers=legal()).json()["data"]
        client.post(f"/api/v1/office/legal/cases/{appeal['legal_case_id']}/orders", json={"order_date": date.today().isoformat(),
                    "outcome": "INTERIM_STAY", "note": "Recovery stayed"}, headers=legal())
        r = client.post(f"{REC}/{rid}/receivers", json={"over": "BUSINESS", "receiver": "Synthetic Receiver", "note": "x"},
                        headers=ro({"action": "appoint-receiver", "resource_id": rid}))
        assert r.status_code == 409 and r.json()["type"] == "/problems/stayed"
    finally:
        recovery_module.now = __import__("app.api.proceedings", fromlist=["now"]).now


def test_employer_view_and_the_ho_reports(ctx):
    client, _, _ = ctx
    rid = certified(client)["recovery_case_id"]
    client.post(f"{REC}/{rid}/payments", json={"amount_paise": 1000000, "reference": "TRRN-RC-2"}, headers=ro())
    mine = client.get("/api/v1/employers/me/recovery-cases", headers=hdr(S["emp-owner"], "employer.owner", establishment=ENG)).json()["data"]
    assert mine[0]["outstanding_paise"] == 2000000 and "recovery_officer" not in mine[0]
    assert client.get(f"{REC}/cases", headers=hdr(S["emp-owner"], "employer.owner", establishment=ENG)).status_code == 403
    rec = client.get("/api/v1/ho/reports/recovery", headers=hdr(S["ho-recovery"], "ho.recovery")).json()["data"]
    assert rec["certificates"] == 1 and rec["realised_paise"] == 1000000 and rec["realised_by_mode_paise"] == {"DIRECT": 1000000}
    proc = client.get("/api/v1/ho/reports/proceedings", headers=hdr(S["ho-compliance"], "ho.compliance")).json()["data"]
    assert proc["inquiries"] >= 1 and proc["by_section"]["7A"]["ORDERED"] >= 1


def test_instalments_by_powers_head_office_beyond_36_and_withdrawn_on_default(ctx, monkeypatch):
    """Circulars of 7.4.2006, 11.4.2012 and 11.02.2014 (Recovery Manual 8.1.2), with the powers scaled down to the
    seeded ₹30,000: the region up to ₹25,000 here, the zone up to ₹50,000; beyond 36 instalments only Head Office."""
    import app.api.recovery as recovery_module
    real = recovery_module.rules

    async def scaled(session):
        document, limits = await real(session)
        return document, {**limits, "instalment_powers_paise": {"RPFC-II": 1000000, "RPFC-I": 2500000, "zo.acc": 5000000, "ho.cpfc": None}}
    monkeypatch.setattr(recovery_module, "rules", scaled)
    client, _, _ = ctx
    rid = certified(client)["recovery_case_id"]
    url = f"{REC}/{rid}/instalments"
    body = {"count": 12, "first_due": "2026-11-01", "note": "Hardship", "bank_guarantee_paise": 250000, "bank_guarantee_ref": "BG-1"}
    refused = client.post(url, json=body, headers=as_(OIC)).json()
    assert refused["type"] == "/problems/beyond-powers" and "RPFC-I" in refused["detail"]               # ₹30,000 > the region's ₹25,000
    zone = hdr(S["zo-acc"], "zo.acc")
    assert client.post(url, json={**body, "count": 40}, headers=zone).json()["type"] == "/problems/beyond-powers"   # > 36: Head Office
    granted = client.post(url, json=body, headers=zone).json()["data"]
    assert granted["state"] == "INSTALMENTS"
    client.post(f"{REC}/{rid}/instalment-defaults", json={"missed": "The second instalment, due 1 Dec 2026"}, headers=ro())
    assert client.get(f"{REC}/cases", headers=ro()).json()["data"][0]["state"] in ("CERTIFIED", "NOTICE_SERVED")
    ho = hdr(S["ho-analyst"], "ho.cpfc")                                                   # the CPFC persona
    beyond = {**body, "count": 60, "bank_guarantee_paise": 300000}                                        # six instalments of ₹500
    again = client.post(url, json=beyond, headers=ho).json()
    assert again["type"] == "/problems/defaulted-before"                                                   # no second facility
