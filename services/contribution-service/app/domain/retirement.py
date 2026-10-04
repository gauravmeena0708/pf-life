"""P2.23: the member's PF at retirement, with and without VPF — the provident-fund half of the retirement view (the pension
half is pension-service's estimate; the web shows them together). Illustrative, not advice.

Month by month to the normal pension age: the member's 12% and the employer's EPF share (12% less the 8.33% to EPS on
wages up to the ceiling, none at 58 or more) on wages that rise each April; VPF on top, which the employer does not match;
interest at the latest declared rate on each month's closing balance, credited at the end of each financial year (and at
retirement for the part year). Interest on the member's own contributions above the threshold a year is taxable (VPF
counts toward it): the years where that happens are listed."""
from datetime import date
from typing import Any

from epfo_persistence.policy import financial_year, interest_on, round_rupee_half_up, section, split


def _add_months(day: date, n: int) -> date:
    y, m = divmod(day.month - 1 + n, 12)
    return date(day.year + y, m + 1, 1)


def retirement_day(date_of_birth: date, rules: dict[str, Any]) -> date:
    age = section(rules, "pension")["normal_age_years"]
    return date(date_of_birth.year + age, date_of_birth.month, min(date_of_birth.day, 28))


def latest_rate(rules: dict[str, Any]) -> tuple[str | None, int]:
    rates = section(rules, "interest").get("rates_bp") or {}
    if not rates:
        return None, 0
    fy = max(rates)
    return fy, int(rates[fy])


def project(*, balance_paise: int, wages_paise: int, date_of_birth: date, today: date, rules: dict[str, Any],
            vpf_bp: int = 0, in_service: bool = True) -> dict[str, Any]:
    r = section(rules, "retirement")
    _, rate = latest_rate(rules)
    threshold = section(rules, "tds").get("taxable_interest_threshold_paise")
    retire = retirement_day(date_of_birth, rules)
    balance, wages = balance_paise, wages_paise
    totals = {"employee_paise": 0, "employer_paise": 0, "vpf_paise": 0, "interest_paise": 0}
    month = _add_months(today, 1)                               # from next month's wages
    # this year's months so far earn interest too, at the year's end: their closing balances are today's (approximately)
    closings: list[int] = [balance] * ((today.month - 4) % 12 + 1) if _add_months(month, 1) <= retire else []
    own_in_year, taxable_years = 0, []
    months = 0
    while _add_months(month, 1) <= retire:                     # whole months before the 58th birthday
        if month.month == 4 and months:                         # a new year's pay rise
            wages = wages * (10_000 + r["wage_growth_bp"]) // 10_000
        if in_service:
            age = month.year - date_of_birth.year - ((month.month, 1) < (date_of_birth.month, date_of_birth.day))
            parts = split(wages, wages, age, rules)
            vpf = round_rupee_half_up(wages * vpf_bp)
            balance += parts["AC01_EPF_EE"] + parts["AC01_EPF_ER"] + vpf
            totals["employee_paise"] += parts["AC01_EPF_EE"]
            totals["employer_paise"] += parts["AC01_EPF_ER"]
            totals["vpf_paise"] += vpf
            own_in_year += parts["AC01_EPF_EE"] + vpf
        closings.append(balance)
        months += 1
        last = _add_months(month, 2) > retire
        if month.month == 3 or last:                            # the year ends (or the member retires): interest credited
            interest = interest_on(closings, rate)
            balance += interest
            totals["interest_paise"] += interest
            if threshold is not None and own_in_year > threshold:
                taxable_years.append({"financial_year": financial_year(month), "own_contributions_paise": own_in_year,
                                      "above_threshold_paise": own_in_year - threshold})
            closings, own_in_year = [], 0
        month = _add_months(month, 1)
    income = balance * r["drawdown_rate_bp"] // 10_000 // 12
    return {"vpf_bp": vpf_bp, "corpus_paise": balance, **totals, "months": months, "final_wages_paise": wages if in_service else 0,
            "monthly_income_paise": round_rupee_half_up(income * 10_000), "vpf_now_monthly_paise": round_rupee_half_up(wages_paise * vpf_bp) if in_service else 0,
            "taxable_interest_years": taxable_years}


def forecast(*, balance_paise: int, wages_paise: int, date_of_birth: date, today: date, rules: dict[str, Any],
             vpf_bp: int, in_service: bool) -> dict[str, Any]:
    r = section(rules, "retirement")
    if not 0 <= vpf_bp <= r["vpf_max_bp"]:
        raise ValueError(f"VPF can be 0 to {r['vpf_max_bp'] / 100:g}% of wages")
    fy, rate = latest_rate(rules)
    retire = retirement_day(date_of_birth, rules)
    common = dict(balance_paise=balance_paise, wages_paise=wages_paise, date_of_birth=date_of_birth, today=today, rules=rules,
                  in_service=in_service)
    without = project(**common)
    scenarios = [without] if not vpf_bp or not in_service else [without, project(**common, vpf_bp=vpf_bp)]
    threshold = section(rules, "tds").get("taxable_interest_threshold_paise")
    return {"as_of": today.isoformat(), "retire_on": retire.isoformat(), "months_to_go": without["months"],
            "balance_now_paise": balance_paise, "wages_now_paise": wages_paise if in_service else 0, "in_service": in_service,
            "assumptions": {"interest_rate_bp": rate, "interest_declared_for": fy, "wage_growth_bp": r["wage_growth_bp"],
                            "drawdown_rate_bp": r["drawdown_rate_bp"], "vpf_max_bp": r["vpf_max_bp"],
                            "taxable_interest_threshold_paise": threshold, "rule_version": rules["rule_version"]},
            "scenarios": scenarios,
            "note": ("Illustrative, not advice: the latest declared interest rate is assumed to hold and wages to rise each year. "
                     "VPF is your own money — the employer does not match it — and earns the EPF rate.")}
