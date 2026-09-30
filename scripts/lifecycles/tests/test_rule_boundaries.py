"""Real deterministic POC rules with controlled data; these are not live UI results."""
import copy
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
for package in ("common-persistence", "common-observability", "common-auth-client"):
    sys.path.insert(0, str(ROOT / "packages" / package))
spec = importlib.util.spec_from_file_location("lifecycle_claim_rules", ROOT / "services/claim-service/app/domain/claims.py")
claims = importlib.util.module_from_spec(spec)
spec.loader.exec_module(claims)
from epfo_persistence.policy import tds_on

RULES = yaml.safe_load((ROOT / "config/demo-rules.yaml").read_text())
TODAY = date(2026, 9, 30)


def account(**values):
    return {"employee_paise": 360000000, "employer_paise": 240000000,
            "date_of_joining": date(2022, 6, 1), "date_of_exit": None, **values}


@pytest.mark.parametrize("amount,route", [(9999999, "AUTO"), (10000000, "AUTO"), (10000001, "REVIEW")])
def test_automatic_limit_below_at_above(amount, route):
    assert claims.route(amount, RULES, "ADVANCE_ILLNESS") == route


@pytest.mark.parametrize("amount,last", [(5000000, "fo.ss"), (5000001, "fo.ao"), (50000000, "fo.ao"),
                                          (50000001, "fo.apfc"), (250000000, "fo.apfc"), (250000001, "fo.oic")])
def test_approval_band_inclusive_boundaries(amount, last):
    chain = claims.approval_chain(amount, RULES, "FINAL_SETTLEMENT")
    assert chain[0] == "fo.da_accounts" and chain[-1] == last


def test_small_eps_claim_always_reviewed():
    assert claims.route(100, RULES, "PENSION_WITHDRAWAL") == "REVIEW"


@pytest.mark.parametrize("exit_date,eligible", [(date(2026, 8, 1), False), (date(2026, 7, 30), True), (date(2026, 7, 29), True)])
def test_complete_exit_month_boundary(exit_date, eligible):
    result = claims.eligibility(account(date_of_exit=exit_date), "FINAL_SETTLEMENT", RULES, TODAY)
    assert result["eligible"] is eligible


def test_zero_balance_and_zero_employee_share_are_distinct():
    for specimen in [account(employee_paise=0, employer_paise=0), account(employee_paise=0, employer_paise=10000)]:
        result = claims.eligibility(specimen, "ADVANCE_ILLNESS", RULES, TODAY)
        assert not result["eligible"] and "no balance" in "; ".join(result["reasons"]).lower()


def test_employee_share_and_claim_cap():
    result = claims.eligibility(account(), "ADVANCE_ILLNESS", RULES, TODAY)
    assert result["max_amount_paise"] == 100000000
    result = claims.eligibility(account(employee_paise=1234500), "ADVANCE_ILLNESS", RULES, TODAY)
    assert result["max_amount_paise"] == 1234500


def test_retired_type_and_repeat_benefit():
    rules = copy.deepcopy(RULES)
    rules["claims"]["types"]["ADVANCE_ILLNESS"]["retired"] = True
    assert not claims.eligibility(account(), "ADVANCE_ILLNESS", rules, TODAY)["eligible"]
    result = claims.eligibility(account(date_of_exit=date(2026, 6, 30)), "PENSION_WITHDRAWAL", RULES, TODAY, [date(2026, 6, 29)])
    assert not result["eligible"] and any("once every" in r for r in result["reasons"])


@pytest.mark.parametrize("joined,eligible", [(date(2026, 1, 31), False), (date(2026, 1, 30), True),
                                           (date(2017, 2, 28), True), (date(2017, 1, 30), False)])
def test_eps_service_minimum_and_maximum(joined, eligible):
    result = claims.eligibility(account(date_of_joining=joined, date_of_exit=date(2026, 7, 30)), "PENSION_WITHDRAWAL", RULES, TODAY)
    assert result["eligible"] is eligible


@pytest.mark.parametrize("amount,service,pan,declaration,tax", [
    (4999900, 59, True, False, 0), (5000000, 59, True, False, 500000),
    (5000000, 59, False, False, 1000000), (5000000, 60, False, False, 0),
    (5000000, 59, False, True, 0),
])
def test_tds_threshold_pan_service_and_waiver(amount, service, pan, declaration, tax):
    result = tds_on(amount, "FINAL_SETTLEMENT", service, pan, declaration, RULES)
    assert result["tds_paise"] == tax
    assert amount == result["tds_paise"] + (amount - result["tds_paise"])


def test_medical_advance_is_not_final_settlement_tax_case():
    assert tds_on(60000000, "ADVANCE_ILLNESS", 1, False, False, RULES)["tds_paise"] == 0
