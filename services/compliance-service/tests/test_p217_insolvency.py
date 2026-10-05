"""Phase 2, slice 17 (P2.17): Insolvency.
- Watchlist from EPFO signals: stopped ECR filing (3+ months), open demands in default, synthetic MCA status.
- Insolvency case per establishment: IBBI announcement, claim deadline (+14 days configurable), 3-day warning.
- Dues frozen: moratorium (IBC s.14) stops coercive recovery (attachment, sale, receiver, arrest);
  claim filed with PF principal kept apart from s.14B damages and s.7Q interest.
- Resolution plan checked: NON-COMPLIANT unless PF principal paid in full (IBC s.36(4)(a)(iii));
  in liquidation, PF claim recorded as outside the liquidation estate (outside s.53 waterfall).
- Recovery measured: dues claimed, recovered, recovery %, and office summary.
"""
from datetime import UTC, date, datetime, timedelta
import json

from tests.test_compliance import EST, S, ctx, hdr  # noqa: F401
from tests.test_proceedings import APFC, BASE, OIC, as_
from tests.test_recovery import REC, RO, ro, SEEDED, ENG, certified

DA = S["ro-da-compliance"]
INS_BASE = "/api/v1/office/compliance/insolvency"
CASES_BASE = "/api/v1/office/compliance/insolvency-cases"


def da(step_up=None):
    return hdr(DA, "fo.da_compliance", step_up)


def apfc(step_up=None):
    return hdr(APFC, "fo.apfc", step_up)


def test_watchlist_signals_scoring_and_reasons(ctx):
    """P2.17a: Watchlist scores establishments from stopped ECR (3+ months), open defaults, or CIRP/liquidation MCA status."""
    client, q, deliver = ctx

    # Seed an open demand in default for EST-DEMO-0002 (ENG) if not already present
    deliver("DemandStateChanged.v1", {
        "demand_id": "DEMAND-ENG-001",
        "establishment_id": ENG,
        "kind": "DUES_7A",
        "trrn": "TRRN-ENG-1",
        "wage_month": "2026-01",
        "amount_paise": 2500000,
        "days_late": 95,
        "state": "OPEN",
        "working": "Assessed dues"
    })

    # Record ECR filing for ENG that stopped >3 months ago (e.g. filed 2026-01, 2026-02, then stopped)
    deliver("ECRValidated.v1", {
        "filing_id": "ECR-ENG-2026-01",
        "establishment_id": ENG,
        "wage_month": "2026-01",
        "member_count": 25
    })
    deliver("ECRValidated.v1", {
        "filing_id": "ECR-ENG-2026-02",
        "establishment_id": ENG,
        "wage_month": "2026-02",
        "member_count": 25
    })

    # Set synthetic MCA status on EST-DEMO-0003 as "UNDER_CIRP"
    client.post(f"{BASE}/establishments/EST-DEMO-0003/mca-statuses",
                json={"mca_status": "UNDER_CIRP"}, headers=apfc())

    r = client.get(f"{INS_BASE}/watchlist", headers=apfc())
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "watchlist" in data
    items = data["watchlist"]
    assert len(items) >= 2

    # Check that ENG is flagged for ECR stopped and open demands
    eng_item = next((item for item in items if item["establishment_id"] == ENG), None)
    assert eng_item is not None
    assert eng_item["score"] > 0
    assert any("ECR" in reason for reason in eng_item["reasons"])
    assert any("demand" in reason.lower() for reason in eng_item["reasons"])

    # Check EST-DEMO-0003 is flagged for MCA CIRP status
    est3_item = next((item for item in items if item["establishment_id"] == "EST-DEMO-0003"), None)
    assert est3_item is not None
    assert est3_item["score"] >= 50
    assert any("CIRP" in reason for reason in est3_item["reasons"])


def test_ibbi_announcement_deadline_and_approaching_warning(ctx, monkeypatch):
    """P2.17b: Record IBBI announcement (14 days claim deadline configurable); warning within 3 days if unfiled."""
    client, q, _ = ctx

    today_dt = date(2026, 10, 1)
    body = {
        "establishment_id": ENG,
        "stage": "CIRP",
        "practitioner_type": "IRP",
        "practitioner_name": "Shri V. Sharma, IP",
        "practitioner_email": "v.sharma@insolvency.demo.invalid",
        "announcement_date": today_dt.isoformat(),
        "claim_period_days": 14,
        "nclt_bench": "NCLT New Delhi Bench-II",
        "order_ref": "CP(IB)-102/ND/2026",
        "note": "Public announcement in Form A"
    }

    r = client.post(CASES_BASE, json=body, headers=apfc())
    assert r.status_code == 201, r.text
    case = r.json()["data"]
    cid = case["case_id"]
    assert case["stage"] == "CIRP"
    assert case["claim_deadline"] == "2026-10-15"  # 2026-10-01 + 14 days
    assert case["moratorium_active"] is True

    # 1. More than 3 days before deadline (e.g. today is 2026-10-02 -> 13 days left): no warning
    import app.api.insolvency as ins_module
    monkeypatch.setattr(ins_module, "current_date", lambda: date(2026, 10, 2))
    r_early = client.get(f"{CASES_BASE}/{cid}", headers=apfc())
    assert r_early.status_code == 200
    assert r_early.json()["data"]["warning"] is None

    # 2. Within 3 days of deadline (e.g. today is 2026-10-13 -> 2 days left): warning present
    monkeypatch.setattr(ins_module, "current_date", lambda: date(2026, 10, 13))
    r_warn = client.get(f"{CASES_BASE}/{cid}", headers=apfc())
    assert r_warn.status_code == 200
    assert r_warn.json()["data"]["warning_code"] == "CLAIM_DEADLINE_APPROACHING"
    assert "2 day" in r_warn.json()["data"]["warning"]

    # 3. Configurable claim deadline (e.g. 21 days)
    body_config = {**body, "establishment_id": EST, "claim_period_days": 21}
    r_cfg = client.post(CASES_BASE, json=body_config, headers=apfc())
    assert r_cfg.status_code == 201
    assert r_cfg.json()["data"]["claim_deadline"] == "2026-10-22"


def test_moratorium_stops_coercive_recovery_and_freezes_dues(ctx):
    """P2.17c: IBC s.14 moratorium stops coercive recovery actions (attachment, sale, receiver, arrest).
    Dues frozen: PF principal kept apart from s.14B damages and s.7Q interest."""
    client, q, deliver = ctx

    # Seed an order and recovery certificate on ENG (EST-DEMO-0002)
    rc = certified(client)
    rid = rc["recovery_case_id"]

    # Serve demand notice
    client.post(f"{REC}/{rid}/demand-notices", headers=ro())

    # Admission to CIRP with moratorium on ENG
    announcement = {
        "establishment_id": ENG,
        "stage": "CIRP",
        "practitioner_type": "IRP",
        "practitioner_name": "Resolution Professional A",
        "announcement_date": "2026-10-01",
        "claim_period_days": 14,
    }
    r_case = client.post(CASES_BASE, json=announcement, headers=apfc())
    assert r_case.status_code == 201, r_case.text
    case_id = r_case.json()["data"]["case_id"]

    # Coercive recovery MUST be refused under IBC s.14 moratorium
    # 1. Attachment
    attach_body = {"kind": "MOVABLE", "description": "Machinery", "value_paise": 1000000, "urgent_reason": "Risk"}
    step_att = ro({"action": "attach-property", "resource_id": rid})
    r_att = client.post(f"{REC}/{rid}/attachments", json=attach_body, headers=step_att)
    assert r_att.status_code == 409, r_att.text
    assert r_att.json()["type"] == "/problems/moratorium-active"

    # 2. Receiver
    step_rec = ro({"action": "appoint-receiver", "resource_id": rid})
    r_rec = client.post(f"{REC}/{rid}/receivers", json={"over": "BUSINESS", "receiver": "Rec", "note": "x"}, headers=step_rec)
    assert r_rec.status_code == 409
    assert r_rec.json()["type"] == "/problems/moratorium-active"

    # 3. Arrest
    step_arr = ro({"action": "arrest-defaulter", "resource_id": rid})
    r_arr = client.post(f"{REC}/{rid}/arrest-warrants", json={"step": "SHOW_CAUSE", "hearing_on": "2026-11-01", "reasons": "SCN"}, headers=step_arr)
    assert r_arr.status_code == 409
    assert r_arr.json()["type"] == "/problems/moratorium-active"

    # Check dues summary: principal kept apart from s.14B damages and s.7Q interest
    deliver("DemandStateChanged.v1", {"demand_id": "D-ENG-14B", "establishment_id": ENG, "kind": "DAMAGES_14B", "trrn": "T1",
                                      "wage_month": "2026-01", "amount_paise": 300000, "days_late": 30, "state": "OPEN", "working": "w"})
    deliver("DemandStateChanged.v1", {"demand_id": "D-ENG-7Q", "establishment_id": ENG, "kind": "INTEREST_7Q", "trrn": "T1",
                                      "wage_month": "2026-01", "amount_paise": 150000, "days_late": 30, "state": "OPEN", "working": "w"})

    r_dues = client.get(f"{CASES_BASE}/{case_id}/dues-summary", headers=apfc())
    assert r_dues.status_code == 200, r_dues.text
    dues = r_dues.json()["data"]
    assert dues["principal_paise"] == 3000000  # DUES_7A
    assert dues["damages_paise"] == 300000     # DAMAGES_14B
    assert dues["interest_paise"] == 150000    # INTEREST_7Q
    assert dues["total_dues_paise"] == 3450000

    # File claim
    claim_body = {
        "claim_reference": "CLAIM/ENG/01",
        "form_type": "FORM_B",
        "principal_paise": 3000000,
        "damages_paise": 300000,
        "interest_paise": 150000,
        "note": "Claim submitted to IRP under IBC"
    }
    r_claim = client.post(f"{CASES_BASE}/{case_id}/claims", json=claim_body, headers=apfc())
    assert r_claim.status_code == 200, r_claim.text
    case_updated = r_claim.json()["data"]
    assert case_updated["claim_filed"] is True
    assert case_updated["total_claimed_paise"] == 3450000
    assert case_updated["claimed_principal_paise"] == 3000000


def test_resolution_plan_compliance_check_and_liquidation_estate(ctx):
    """P2.17d: Resolution plan flagged NON-COMPLIANT unless PF principal paid in full (IBC s.36(4)(a)(iii)).
    In liquidation, PF dues recorded outside liquidation estate (outside s.53 waterfall)."""
    client, q, _ = ctx

    # Create CIRP case and file claim
    r_case = client.post(CASES_BASE, json={
        "establishment_id": ENG,
        "stage": "CIRP",
        "practitioner_type": "RP",
        "practitioner_name": "RP Patel",
        "announcement_date": "2026-09-01",
    }, headers=apfc())
    cid = r_case.json()["data"]["case_id"]

    client.post(f"{CASES_BASE}/{cid}/claims", json={
        "claim_reference": "FORM-B-ENG-2",
        "principal_paise": 5000000,
        "damages_paise": 1000000,
        "interest_paise": 500000,
    }, headers=apfc())

    # 1. Non-compliant plan: cuts PF principal (e.g. offers 40,00,000 paise vs 50,00,000 claimed)
    non_compliant_plan = {
        "plan_reference": "PLAN-RESOLUTION-01",
        "resolution_applicant": "ABC Holdings",
        "plan_principal_paise": 4000000,  # 80% haircut on principal -> ILLEGAL
        "plan_damages_paise": 500000,
        "plan_interest_paise": 250000,
        "note": "Proposed resolution plan"
    }
    r_nc = client.post(f"{CASES_BASE}/{cid}/resolution-plans", json=non_compliant_plan, headers=apfc())
    assert r_nc.status_code == 200, r_nc.text
    nc_result = r_nc.json()["data"]
    assert nc_result["plan_status"] == "NON_COMPLIANT"
    assert nc_result["resolution_plan"]["is_compliant"] is False
    assert "s.36(4)(a)(iii)" in nc_result["resolution_plan"]["compliance_reason"]

    # 2. Compliant plan: pays 100% PF principal, compromises damages and interest
    compliant_plan = {
        "plan_reference": "PLAN-RESOLUTION-02",
        "resolution_applicant": "Reliable Infra Ltd",
        "plan_principal_paise": 5000000,  # 100% of principal paid
        "plan_damages_paise": 200000,     # damages compromised
        "plan_interest_paise": 100000,    # interest compromised
        "note": "Revised resolution plan with full PF principal"
    }
    r_c = client.post(f"{CASES_BASE}/{cid}/resolution-plans", json=compliant_plan, headers=apfc())
    assert r_c.status_code == 200, r_c.text
    c_result = r_c.json()["data"]
    assert c_result["plan_status"] == "COMPLIANT"
    assert c_result["resolution_plan"]["is_compliant"] is True

    # 3. Liquidation case: PF claim recorded as outside the liquidation estate (outside s.53 waterfall)
    r_liq = client.post(CASES_BASE, json={
        "establishment_id": EST,
        "stage": "LIQUIDATION",
        "practitioner_type": "LIQUIDATOR",
        "practitioner_name": "Liquidator Sen",
        "announcement_date": "2026-10-01",
    }, headers=apfc())
    assert r_liq.status_code == 201
    liq_case = r_liq.json()["data"]
    assert liq_case["outside_liquidation_estate"] is True
    assert liq_case["waterfall_status"] == "OUTSIDE_S53_WATERFALL"
    assert "s.36(4)(a)(iii)" in liq_case["statutory_basis"]


def test_recovery_measurement_and_office_summary(ctx):
    """P2.17e: Measure dues claimed, recovered, and recovery %; office summary."""
    client, q, _ = ctx

    # Create case and file claim
    r_case = client.post(CASES_BASE, json={
        "establishment_id": ENG,
        "stage": "CIRP",
        "practitioner_type": "RP",
        "practitioner_name": "RP Mehta",
        "announcement_date": "2026-08-01",
    }, headers=apfc())
    cid = r_case.json()["data"]["case_id"]

    client.post(f"{CASES_BASE}/{cid}/claims", json={
        "claim_reference": "CLAIM-MHT-01",
        "principal_paise": 4000000,
        "damages_paise": 500000,
        "interest_paise": 500000,
    }, headers=apfc())

    # Record first recovery payment (e.g. ₹20,000 / 2,000,000 paise = 40%)
    r_rec1 = client.post(f"{CASES_BASE}/{cid}/realisations", json={
        "amount_paise": 2000000,
        "mode": "RESOLUTION_PLAN",
        "reference": "CHQ-RP-001",
        "realised_on": "2026-09-15",
        "note": "First instalment from Resolution Applicant"
    }, headers=apfc())
    assert r_rec1.status_code == 200, r_rec1.text
    res1 = r_rec1.json()["data"]
    assert res1["realised_paise"] == 2000000
    assert res1["recovery_pct"] == 40.0
    assert res1["state"] == "CLAIM_FILED"

    # Record second recovery payment (e.g. ₹30,000 / 3,000,000 paise = 100% total)
    r_rec2 = client.post(f"{CASES_BASE}/{cid}/realisations", json={
        "amount_paise": 3000000,
        "mode": "RESOLUTION_PLAN",
        "reference": "CHQ-RP-002",
        "realised_on": "2026-10-01",
        "note": "Final settlement"
    }, headers=apfc())
    assert r_rec2.status_code == 200
    res2 = r_rec2.json()["data"]
    assert res2["realised_paise"] == 5000000
    assert res2["recovery_pct"] == 100.0
    assert res2["state"] == "CLOSED"

    # Office summary
    r_sum = client.get(f"{INS_BASE}/summary", headers=apfc())
    assert r_sum.status_code == 200, r_sum.text
    summary = r_sum.json()["data"]
    assert summary["total_cases"] >= 1
    assert summary["total_claimed_paise"] >= 5000000
    assert summary["total_recovered_paise"] >= 5000000
    assert summary["overall_recovery_pct"] > 0
    assert "by_stage" in summary
