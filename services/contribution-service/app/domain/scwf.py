"""Calendar boundaries for the illustrative Senior Citizens' Welfare Fund workflow."""
from datetime import date


def plus_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def inoperative_on(last_credit: date, months: int) -> date:
    """The existing month-cutoff rule first includes the account on this month's first day."""
    month_index = last_credit.year * 12 + last_credit.month + months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, 1)


def scwf_eligible(last_credit: date, months: int, identification_year: int) -> bool:
    # SCWF seven-year wait begins when the account first becomes inoperative.
    return plus_years(inoperative_on(last_credit, months), 7) <= date(identification_year, 9, 30)


def reclaim_open(transferred_on: date, claimed_on: date) -> bool:
    # SCWF reclaim remains open through the transfer's 25th anniversary.
    return transferred_on <= claimed_on <= plus_years(transferred_on, 25)
