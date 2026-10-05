"""P2.24: Interest-sustainability model for HO Finance."""
import json
from datetime import date

from app.infra.messaging import on_fund_positions_received
from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401

URL = "/api/v1/ho/finance/interest-sustainability"
YIELD_URL = "/api/v1/ho/finance/yield-assumptions"
HO_FINANCE = SEED["keycloak_subjects"]["ho-finance"]


def fa_cao():
    return hdr(HO_FINANCE, "ho.fa_cao", [], establishment=None)


def cpfc():
    return hdr("cpfc-subject", "ho.cpfc", [], establishment=None)


def member_user():
    return hdr("member-subject", "member", [], establishment=None)


def deliver_positions(manager="SBI MF", fund="EPF", as_of="2026-09-30", by_asset_class=None):
    classes = by_asset_class if by_asset_class is not None else [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 100_000_000},
        {"asset_class": "DEBT", "book_value_paise": 50_000_000},
    ]
    payload = {
        "fund_manager": manager,
        "fund": fund,
        "as_of": as_of,
        "holdings": len(classes),
        "market_value_paise": sum(c["book_value_paise"] for c in classes),
        "by_asset_class": classes,
    }
    return _deliver(on_fund_positions_received, payload, "FundPositionsReceived.v1")


def test_copy_keeps_newest_as_of_and_ignores_non_epf(ctx):
    client, q = ctx
    # 1. Deliver initial EPF position for Manager A as of 2026-09-30
    deliver_positions("Manager A", "EPF", "2026-09-30", [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 10_000_000},
    ])
    rows = q("SELECT fund_manager, fund, asset_class, book_value_paise, as_of FROM fund_asset_classes WHERE fund_manager='Manager A'")
    assert len(rows) == 1
    assert rows[0][0] == "Manager A" and rows[0][1] == "EPF" and rows[0][2] == "GOVT_SECURITIES" and rows[0][3] == 10_000_000
    assert str(rows[0][4])[:10] == "2026-09-30"

    # 2. Deliver older position for Manager A as of 2026-09-15 -> must be ignored (order-safe)
    deliver_positions("Manager A", "EPF", "2026-09-15", [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 99_999_999},
    ])
    rows_after_older = q("SELECT book_value_paise, as_of FROM fund_asset_classes WHERE fund_manager='Manager A'")
    assert len(rows_after_older) == 1
    assert rows_after_older[0][0] == 10_000_000
    assert str(rows_after_older[0][1])[:10] == "2026-09-30"

    # 3. Deliver newer position for Manager A as of 2026-10-15 -> replaces previous snapshot
    deliver_positions("Manager A", "EPF", "2026-10-15", [
        {"asset_class": "DEBT", "book_value_paise": 20_000_000},
    ])
    rows_newer = q("SELECT asset_class, book_value_paise, as_of FROM fund_asset_classes WHERE fund_manager='Manager A'")
    assert len(rows_newer) == 1
    assert rows_newer[0][0] == "DEBT" and rows_newer[0][1] == 20_000_000
    assert str(rows_newer[0][2])[:10] == "2026-10-15"

    # 4. Deliver non-EPF (EPS) -> ignored
    deliver_positions("Manager A", "EPS", "2026-11-01", [
        {"asset_class": "EQUITY", "book_value_paise": 50_000_000},
    ])
    assert q("SELECT COUNT(*) FROM fund_asset_classes WHERE fund='EPS'")[0][0] == 0

    # 5. Deliver Manager B -> keeps latest per fund manager
    deliver_positions("Manager B", "EPF", "2026-10-01", [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 15_000_000},
    ])
    assert q("SELECT COUNT(*) FROM fund_asset_classes WHERE fund='EPF'")[0][0] == 2

    # A newer empty report still advances the manager watermark.
    deliver_positions("Manager B", "EPF", "2026-11-01", [])
    assert q("SELECT COUNT(*) FROM fund_asset_classes WHERE fund_manager='Manager B'")[0][0] == 0
    deliver_positions("Manager B", "EPF", "2026-10-15", [
        {"asset_class": "DEBT", "book_value_paise": 90_000_000},
    ])
    assert q("SELECT COUNT(*) FROM fund_asset_classes WHERE fund_manager='Manager B'")[0][0] == 0


def test_no_positions_returns_422(ctx):
    client, _ = ctx
    response = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao())
    assert response.status_code == 422
    assert "No fund positions are known" in response.text


def test_sustainability_model_verdicts_and_break_even_matches(ctx):
    client, _ = ctx
    # In synthetic seed, members have balances and 2025-26 declared rate is 825 bp
    # Set known fund positions:
    # Say 100,000,000 paise (₹10,00,000)
    deliver_positions("Manager A", "EPF", "2026-09-30", [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 200_000_000},
        {"asset_class": "DEBT", "book_value_paise": 100_000_000},
    ])

    response = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao())
    assert response.status_code == 200, response.json()
    data = response.json()["data"]

    assert data["financial_year"] == "2025-26"
    assert data["income_paise"] > 0
    assert data["liability_paise"] > 0
    assert data["surplus_paise"] == data["income_paise"] - data["liability_paise"]
    assert data["break_even_rate_bp"] > 0
    assert data["sensitivity"]["minus_50_bp_income_paise"] < data["income_paise"] < data["sensitivity"]["plus_50_bp_income_paise"]
    assert data["current_declared_rate_bp"] == 825
    assert data["current_income_paise"] == data["income_paise"]

    zero = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 0}, headers=fa_cao())
    assert zero.status_code == 200
    assert zero.json()["data"]["liability_paise"] == 0
    assert zero.json()["data"]["break_even_rate_bp"] is not None

    break_even = data["break_even_rate_bp"]

    # 1. Rate below break-even is SUSTAINABLE
    sustainable_rate = max(1, break_even - 100)
    res_sub = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": sustainable_rate}, headers=fa_cao()).json()["data"]
    assert res_sub["verdict"] == "SUSTAINABLE"
    assert res_sub["surplus_paise"] > 0

    # 2. Rate above break-even is DEFICIT
    deficit_rate = break_even + 100
    res_def = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": deficit_rate}, headers=fa_cao()).json()["data"]
    assert res_def["verdict"] == "DEFICIT"
    assert res_def["surplus_paise"] < 0

    # 3. At break-even rate, liability equals income (within 1 basis point of integer rounding)
    res_be = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": break_even}, headers=fa_cao()).json()["data"]
    bp_cost = res_be["liability_paise"] / break_even
    assert abs(res_be["income_paise"] - res_be["liability_paise"]) <= bp_cost + 100


def test_nothing_but_audit_written(ctx):
    client, q = ctx
    deliver_positions("Manager A", "EPF", "2026-09-30")

    tables = ("journals", "journal_lines", "interest_postings", "outbox", "fund_asset_classes", "fund_position_snapshots", "yield_assumptions", "audit_local")
    before = {t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in tables}

    response = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao())
    assert response.status_code == 200

    after = {t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in tables}
    diff = {t: after[t] - before[t] for t in tables}
    assert diff == {**{t: 0 for t in tables}, "audit_local": 1}

    audit_row = q("SELECT actor_subject, action, target_id FROM audit_local WHERE action='finance.interest_sustainability.modeled'")
    assert len(audit_row) == 1
    assert audit_row[0][0] == HO_FINANCE
    assert audit_row[0][2] == "2025-26"


def test_roles_and_permissions(ctx):
    client, _ = ctx
    deliver_positions("Manager A", "EPF", "2026-09-30")

    # POST interest-sustainability: ho.fa_cao and ho.cpfc allowed; member denied (403)
    assert client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao()).status_code == 200
    assert client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=cpfc()).status_code == 200
    assert client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=member_user()).status_code == 403

    # PUT yield-assumptions: only ho.fa_cao allowed; ho.cpfc and member denied (403)
    assert client.put(f"{YIELD_URL}/GOVT_SECURITIES", json={"yield_bp": 750}, headers=fa_cao()).status_code == 200
    assert client.put(f"{YIELD_URL}/GOVT_SECURITIES", json={"yield_bp": 750}, headers=cpfc()).status_code == 403
    assert client.put(f"{YIELD_URL}/GOVT_SECURITIES", json={"yield_bp": 750}, headers=member_user()).status_code == 403


def test_yield_assumption_update_affects_model_and_is_audited(ctx):
    client, q = ctx
    deliver_positions("Manager A", "EPF", "2026-09-30", [
        {"asset_class": "GOVT_SECURITIES", "book_value_paise": 100_000_000},
    ])

    # Initial run: default yield for GOVT_SECURITIES is 720 bp
    initial = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao()).json()["data"]
    init_income = initial["income_paise"]

    # Update yield assumption to 800 bp
    update_res = client.put(f"{YIELD_URL}/GOVT_SECURITIES", json={"yield_bp": 800}, headers=fa_cao())
    assert update_res.status_code == 200
    assert update_res.json()["data"]["yield_bp"] == 800

    # Audit written
    audit_row = q("SELECT actor_subject, action, target_id FROM audit_local WHERE action='finance.yield_assumption.updated'")
    assert len(audit_row) >= 1
    assert audit_row[-1][0] == HO_FINANCE
    assert audit_row[-1][2] == "GOVT_SECURITIES"

    # Re-run model: income should be higher due to 800 bp yield vs 720 bp
    updated = client.post(URL, json={"financial_year": "2025-26", "proposed_rate_bp": 825}, headers=fa_cao()).json()["data"]
    assert updated["income_paise"] > init_income

    # GET yield assumptions lists all
    get_res = client.get(YIELD_URL, headers=fa_cao())
    assert get_res.status_code == 200
    assumptions = {item["asset_class"]: item["yield_bp"] for item in get_res.json()["data"]}
    assert assumptions["GOVT_SECURITIES"] == 800
