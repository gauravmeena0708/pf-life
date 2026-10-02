"""P2.9a: an international worker is a member whose claims follow the international-worker rules (illustrative)."""
from datetime import date

from epfo_persistence.policy import baseline

from app.domain.claims import eligibility

TODAY = date(2026, 9, 30)


def account(**extra):
    return {"employee_paise": 5_000_000, "employer_paise": 1_500_000, "date_of_joining": date(2015, 4, 1),
            "date_of_exit": date(2026, 1, 31), "international_worker": True, "nationality": "Singapore",
            "date_of_birth": date(1980, 6, 15), **extra}


def test_an_international_worker_cannot_take_an_advance():
    result = eligibility(account(date_of_exit=None), "ADVANCE_ILLNESS", baseline(), TODAY)
    assert not result["eligible"] and any("Not available to international workers" in r for r in result["reasons"])


def test_final_settlement_waits_for_58_without_an_agreement():
    result = eligibility(account(), "FINAL_SETTLEMENT", baseline(), TODAY)
    assert not result["eligible"] and any("age of 58" in r for r in result["reasons"])


def test_final_settlement_at_58_or_under_an_agreement():
    assert eligibility(account(date_of_birth=date(1968, 1, 1)), "FINAL_SETTLEMENT", baseline(), TODAY)["eligible"]
    assert eligibility(account(nationality="Germany"), "FINAL_SETTLEMENT", baseline(), TODAY)["eligible"]


def test_a_domestic_member_is_not_affected():
    assert eligibility(account(international_worker=False), "FINAL_SETTLEMENT", baseline(), TODAY)["eligible"]


def test_pension_withdrawal_uses_the_wage_ceiling_in_force_when_the_member_left():
    """P2.26: Table D x wages at exit — ₹15,000 for a member who left before 17 Sep 2026, ₹25,000 after."""
    rules = baseline()
    left = account(international_worker=False, date_of_exit=date(2026, 3, 31), date_of_joining=date(2023, 4, 1))
    before = eligibility(left, "PENSION_WITHDRAWAL", rules, date(2026, 10, 1), None, 1500000)
    after = eligibility(left, "PENSION_WITHDRAWAL", rules, date(2026, 10, 1), None, 2500000)
    assert before["max_amount_paise"] * 25 == after["max_amount_paise"] * 15 > 0
