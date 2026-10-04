"""P2.19c: rectifying erroneous EPS contributions — EPFO Head Office circular No. WSU/2025/E-961539/Refund of erroneous
contribution/42, 19 Dec 2025.

Scenario I — EPS allowed to a member not eligible for it (e.g. joined on or after 1 Sep 2014 on wages above the ceiling,
G.S.R. 609(E)): the EPS remitted each month, with interest at the declared rate, moves from the pension fund (A/c 10) to
the member's PF (A/c 1) — or, for an establishment whose PF is with a trust, to the trust — and the pension service is
deleted. Scenario II — EPS denied to an eligible member: the EPS due each month (8.33% of the wages up to that month's
ceiling, which went to the PF instead), with interest, moves from A/c 1 to A/c 10 — or the trust remits it, worked out at
the trust's declared rate — and the pension service is credited.

Interest is simple, from the month after the wage month to the month of the rectification, at the rate declared for
each wage month's financial year (the latest declared rate when that year has none). Illustrative."""
from datetime import date
from typing import Any

from epfo_persistence.policy import round_rupee_half_up

SCENARIOS = {"WRONGLY_ALLOWED": "I — EPS allowed to a member not eligible", "WRONGLY_DENIED": "II — EPS denied to an eligible member"}


def months_after(wage_month: str, today: date) -> int:
    """Whole months from the month after the wage month to today's month."""
    y, m = int(wage_month[:4]), int(wage_month[5:7])
    return max(0, (today.year - y) * 12 + today.month - m - 1)


def work_out(months: list[dict[str, Any]], scenario: str, today: date, rate_bp_for) -> dict[str, Any]:
    """months: [{wage_month, epf_wages_paise, eps_wages_paise, eps_paise, ceiling_paise, eps_rate_bp}] from the posted
    returns; rate_bp_for(wage_month) -> the interest rate. Returns the month-by-month working and the totals."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
    lines = []
    for m in sorted(months, key=lambda x: x["wage_month"]):
        if scenario == "WRONGLY_ALLOWED":
            amount = m["eps_paise"]
            basis = "EPS remitted"
        else:
            amount = 0 if m["eps_paise"] else round_rupee_half_up(min(m["epf_wages_paise"], m["ceiling_paise"]) * m["eps_rate_bp"])
            basis = f"{m['eps_rate_bp'] / 100:g}% of ₹{min(m['epf_wages_paise'], m['ceiling_paise']) // 100:,}"
        if amount <= 0:
            continue
        rate, n = rate_bp_for(m["wage_month"]), months_after(m["wage_month"], today)
        interest = round_rupee_half_up(amount * rate * n // 12)
        lines.append({"wage_month": m["wage_month"], "basis": basis, "amount_paise": amount, "rate_bp": rate, "months": n,
                      "interest_paise": interest})
    amount = sum(x["amount_paise"] for x in lines)
    interest = sum(x["interest_paise"] for x in lines)
    return {"scenario": scenario, "months": lines, "amount_paise": amount, "interest_paise": interest, "total_paise": amount + interest,
            "worked_out_on": today.isoformat()}
