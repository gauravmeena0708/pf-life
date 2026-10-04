"""P2.23: the PF half of the retirement view — the corpus at the normal pension age, with and without VPF."""
from datetime import date

import pytest

from app.domain.retirement import forecast, project
from epfo_persistence.policy import baseline
from tests.test_ecr_api import SEED, ctx, hdr  # noqa: F401
from tests.test_returns import regular_posted

RULES = baseline()
TODAY = date(2026, 10, 4)


def test_one_year_to_go_by_hand():
    """Born 15 Nov 1969: 58 on 15 Nov 2027 — a year to go, short enough to check by hand."""
    p = project(balance_paise=100_000_00, wages_paise=15_000_00, date_of_birth=date(1969, 11, 15), today=TODAY, rules=RULES)
    # November 2026 to October 2027: 12 months of 12% (₹1,800) and the employer's ₹550 (12% less ₹1,250 to EPS) — the
    # employer pays no EPS from 58, which falls after the last month here; wages rise 5% in April 2027
    assert p["months"] == 12 and p["employee_paise"] == 5 * 1800_00 + 7 * 1890_00
    assert p["employer_paise"] == 5 * 550_00 + 7 * 640_00
    assert p["interest_paise"] > 0 and p["corpus_paise"] == 100_000_00 + p["employee_paise"] + p["employer_paise"] + p["interest_paise"]
    assert p["monthly_income_paise"] == round(p["corpus_paise"] * 600 / 10_000 / 12 / 100) * 100


def test_vpf_adds_only_the_members_money_and_its_interest():
    f = forecast(balance_paise=500_000_00, wages_paise=40_000_00, date_of_birth=date(1990, 1, 1), today=TODAY, rules=RULES,
                 vpf_bp=1000, in_service=True)
    without, with_vpf = f["scenarios"]
    assert with_vpf["employer_paise"] == without["employer_paise"] and with_vpf["vpf_paise"] > 0      # the employer does not match
    assert with_vpf["corpus_paise"] - without["corpus_paise"] > with_vpf["vpf_paise"]                 # VPF earns interest too
    assert with_vpf["vpf_now_monthly_paise"] == 4000_00 and f["retire_on"] == "2048-01-01" and f["months_to_go"] > 250
    # ₹40,000 a month: 12% + 10% VPF is ₹1,05,600 a year, below ₹2,50,000 at first; wages rising 5% cross it later
    assert not without["taxable_interest_years"] and with_vpf["taxable_interest_years"]
    assert with_vpf["taxable_interest_years"][0]["above_threshold_paise"] > 0


def test_out_of_service_or_past_the_age():
    left = forecast(balance_paise=300_000_00, wages_paise=0, date_of_birth=date(1980, 6, 1), today=TODAY, rules=RULES, vpf_bp=1000, in_service=False)
    [only] = left["scenarios"]                                  # no VPF what-if without wages
    assert only["employee_paise"] == only["employer_paise"] == 0 and only["corpus_paise"] > 300_000_00
    old = forecast(balance_paise=300_000_00, wages_paise=20_000_00, date_of_birth=date(1960, 1, 1), today=TODAY, rules=RULES, vpf_bp=0, in_service=True)
    assert old["months_to_go"] == 0 and old["scenarios"][0]["corpus_paise"] == 300_000_00
    with pytest.raises(ValueError):
        forecast(balance_paise=0, wages_paise=1, date_of_birth=date(1990, 1, 1), today=TODAY, rules=RULES, vpf_bp=9000, in_service=True)


def test_member_forecast_from_the_ledger(ctx):
    client, _ = ctx
    member = hdr(SEED["keycloak_subjects"]["member-a"], "member", [], establishment=None)
    regular_posted(client)                                      # September 2026: ₹15,000 wages for member A
    r = client.get("/api/v1/members/me/retirement-forecast?vpf_pct=5", headers=member)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["in_service"] and d["wages_now_paise"] == 15_000_00 and d["balance_now_paise"] >= 600000000
    assert len(d["scenarios"]) == 2 and d["scenarios"][1]["vpf_now_monthly_paise"] == 750_00
    assert d["assumptions"]["interest_rate_bp"] == 825 and d["assumptions"]["drawdown_rate_bp"] == 600
    assert client.get("/api/v1/members/me/retirement-forecast?vpf_pct=95", headers=member).status_code == 422
    assert client.get("/api/v1/members/me/retirement-forecast", headers=hdr("x", "employer.owner", [], establishment=None)).status_code == 403
