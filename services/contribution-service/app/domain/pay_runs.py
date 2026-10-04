"""Pay run validation and ECR drafting from payroll provider runs (P2.22)."""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from app.domain.ecr import capped_wages, section, split

DEFAULT_RULES = {
    "contribution": {
        "epf_employee_rate_bp": 1200,
        "eps_rate_bp": 833,
        "eps_wage_ceiling_paise": 1500000,
        "edli_wage_ceiling_paise": 1500000,
        "eps_age_limit_years": 58,
        "edli_rate_bp": 50,
        "admin_charges_rate_bp": 50,
        "admin_charges_min_paise": 50000,
        "edli_admin_rate_bp": 0,
    },
    "international_workers": {
        "no_wage_ceiling": True,
    },
}


def check_rows(
    rows: list[dict[str, Any]],
    wage_month: str,
    members: list[dict[str, Any]],
    rules: dict[str, Any] | None = None,
    regular_posted: bool = False,
) -> list[dict[str, Any]]:
    """Check pay run rows against establishment members and EPFO rules.

    Returns issues in the contract format: [{row, uan, code, severity, message, fix}].
    """
    if rules is None:
        rules = DEFAULT_RULES
    c = rules.get("contribution", DEFAULT_RULES["contribution"])

    issues: list[dict[str, Any]] = []

    if regular_posted:
        issues.append({
            "row": 0,
            "uan": None,
            "code": "E-REGULAR-ALREADY-POSTED",
            "severity": "error",
            "message": f"Wage month {wage_month} is already covered by a posted regular return.",
            "fix": "Pay runs cannot be submitted for a wage month with a posted return.",
        })

    if not rows:
        issues.append({
            "row": 0,
            "uan": None,
            "code": "E-EMPTY-PAY-RUN",
            "severity": "error",
            "message": "The pay run must contain between 1 and 1000 rows.",
            "fix": "Add at least one employee row.",
        })
        return issues

    by_uan: dict[str, Any] = {}
    for m in members:
        current = by_uan.get(str(m["uan"]))
        if current is None or (current.get("date_of_exit") and not m.get("date_of_exit")):
            by_uan[str(m["uan"])] = m

    seen: set[str] = set()
    day_count = calendar.monthrange(int(wage_month[:4]), int(wage_month[5:7]))[1]
    split_month = bool(c.get("ceiling_periods"))

    for i, row in enumerate(rows, 1):
        uan = str(row.get("uan", ""))
        if uan in seen:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-DUPLICATE-UAN",
                "severity": "error",
                "message": "This UAN appears more than once in the pay run.",
                "fix": "Keep only one row for this UAN per pay run.",
            })
        seen.add(uan)

        member = by_uan.get(uan)
        if not member:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-UAN-UNKNOWN",
                "severity": "error",
                "message": "This UAN is not an employee of this establishment.",
                "fix": "Check the UAN or establishment employment record.",
            })
        else:
            exited = member.get("date_of_exit")
            exited_date = date.fromisoformat(str(exited)) if exited else None
            if exited_date and exited_date.strftime("%Y-%m") < wage_month:
                issues.append({
                    "row": i,
                    "uan": uan,
                    "code": "E-AFTER-EXIT",
                    "severity": "error",
                    "message": f"This member left on {exited_date.isoformat()}, before this wage month.",
                    "fix": "If a court or authority ordered back wages, correct the date of exit (Members › Exit correction) and file a supplementary return.",
                })
            elif re.sub(r"\s+", " ", str(row.get("name", ""))).casefold() != re.sub(r"\s+", " ", str(member.get("name", ""))).strip().casefold():
                masked = " ".join((p[:1] + "***") if p else "" for p in str(member.get("name", "")).split())
                issues.append({
                    "row": i,
                    "uan": uan,
                    "code": "E-NAME-MISMATCH",
                    "severity": "error",
                    "message": f"The name differs from the establishment record ({masked}).",
                    "fix": "correct the file or raise a Joint Declaration",
                })

        gross = row.get("gross_wages_paise", 0)
        epf = row.get("epf_wages_paise", 0)
        eps = row.get("eps_wages_paise", 0)
        edli = row.get("edli_wages_paise", 0)
        ncp = row.get("ncp_days", 0)

        if any(w < 0 for w in (gross, epf, eps, edli)):
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-FORMAT-NUMBER",
                "severity": "error",
                "message": "Enter non-negative wages.",
                "fix": "Enter non-negative wages.",
            })
        elif epf > gross or eps > epf or edli > epf:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-WAGE-ORDER",
                "severity": "error",
                "message": "Wages must satisfy EPF ≤ gross and EPS/EDLI ≤ EPF.",
                "fix": "Correct the wage amounts using payroll records.",
            })

        eps_bound = capped_wages(epf, c, "eps_wage_ceiling_paise") if split_month else c.get("eps_wage_ceiling_paise", 1500000)
        edli_bound = capped_wages(epf, c, "edli_wage_ceiling_paise") if split_month else c.get("edli_wage_ceiling_paise", 1500000)
        above = eps > eps_bound or edli > edli_bound

        iw_rules = section(rules, "international_workers") if "international_workers" in rules else DEFAULT_RULES["international_workers"]
        if above and member and member.get("international_worker") and iw_rules.get("no_wage_ceiling"):
            issues.append({
                "row": i,
                "uan": uan,
                "code": "W-IW-FULL-WAGES",
                "severity": "warning",
                "message": "An international worker contributes on the full wages; the wage ceiling does not apply (illustrative).",
                "fix": "No action needed.",
            })
        elif above:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-EPS-CEILING",
                "severity": "error",
                "message": "EPS and EDLI wages cannot exceed the wage ceiling" + (" weighed by the days of each ceiling this month." if c.get("ceiling_periods") else "."),
                "fix": "Use the wages up to the ceiling (in September 2026: up to ₹15,000 for 1–16 September and ₹25,000 from 17 September, by days).",
            })

        born = date.fromisoformat(str(member["date_of_birth"])) if member and member.get("date_of_birth") else None
        age = int(wage_month[:4]) - born.year - ((int(wage_month[5:7]), day_count) < (born.month, born.day)) if born else 0

        if member and member.get("eps_pensioner") and eps > 0:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-EPS-PENSIONER",
                "severity": "error",
                "message": f"This member already draws an EPS pension (PPO {member.get('pensioner_ppo') or 'on record'}): no pension contribution on re-employment.",
                "fix": "EPS wages 0; the whole employer share (12%) goes to EPF",
            })
        elif member and member.get("eps_not_eligible") and eps > 0:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-EPS-NOT-ELIGIBLE",
                "severity": "error",
                "message": f"This member ID is not eligible for EPS (rectification {member['eps_not_eligible']}): no pension contribution.",
                "fix": "EPS wages 0; the whole employer share (12%) goes to EPF",
            })
        elif born and age >= c.get("eps_age_limit_years", 58) and eps > 0:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-AGE-EPS",
                "severity": "error",
                "message": "This member is at or above the illustrative EPS age limit for the wage month.",
                "fix": "EPS = 0 and the whole employer share goes to EPF",
            })

        if ncp < 0 or ncp > day_count:
            issues.append({
                "row": i,
                "uan": uan,
                "code": "E-NCP-DAYS",
                "severity": "error",
                "message": f"NCP days cannot exceed {day_count} days in this wage month.",
                "fix": f"NCP days must be between 0 and {day_count}.",
            })

    issues.sort(key=lambda x: (x["severity"] != "error", x["row"]))
    return issues


def ecr_lines(
    runs: list[Any],
    members: list[dict[str, Any]] | None = None,
    rules: dict[str, Any] | None = None,
) -> str:
    """Build ECR_TXT content from a month's accepted pay runs.

    Sums wages and NCP days per member over the runs, computing contributions
    with the same arithmetic ecr.validate uses so the draft ECR validates cleanly.
    """
    if rules is None:
        rules = DEFAULT_RULES
    c = rules.get("contribution", DEFAULT_RULES["contribution"])

    by_uan: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    wage_month = "2026-08"

    for run in runs:
        run_wm = getattr(run, "wage_month", None) or (run.get("wage_month") if isinstance(run, dict) else None)
        if run_wm:
            wage_month = run_wm
        run_rows = getattr(run, "rows", None)
        if run_rows is None and isinstance(run, dict):
            run_rows = run.get("rows", [])
        if not run_rows:
            continue
        for r in run_rows:
            uan = str(r["uan"])
            if uan not in by_uan:
                order.append(uan)
                by_uan[uan] = {
                    "uan": uan,
                    "name": r.get("name", ""),
                    "gross_wages_paise": 0,
                    "epf_wages_paise": 0,
                    "eps_wages_paise": 0,
                    "edli_wages_paise": 0,
                    "ncp_days": 0,
                }
            agg = by_uan[uan]
            agg["gross_wages_paise"] += r.get("gross_wages_paise", 0)
            agg["epf_wages_paise"] += r.get("epf_wages_paise", 0)
            agg["eps_wages_paise"] += r.get("eps_wages_paise", 0)
            agg["edli_wages_paise"] += r.get("edli_wages_paise", 0)
            agg["ncp_days"] += r.get("ncp_days", 0)

    members_by_uan: dict[str, Any] = {}
    if members:
        for m in members:
            current = members_by_uan.get(str(m["uan"]))
            if current is None or (current.get("date_of_exit") and not m.get("date_of_exit")):
                members_by_uan[str(m["uan"])] = m

    day_count = calendar.monthrange(int(wage_month[:4]), int(wage_month[5:7]))[1]
    split_month = bool(c.get("ceiling_periods"))

    lines: list[str] = []
    for uan in order:
        agg = by_uan[uan]
        member = members_by_uan.get(uan)
        name = str(agg["name"])

        gross_paise = agg["gross_wages_paise"]
        epf_paise = agg["epf_wages_paise"]
        eps_paise = agg["eps_wages_paise"]
        edli_paise = agg["edli_wages_paise"]
        ncp_days = min(agg["ncp_days"], day_count)

        is_pensioner = bool(member and member.get("eps_pensioner"))
        not_eligible = bool(member and member.get("eps_not_eligible"))
        if is_pensioner or not_eligible:
            eps_paise = 0

        born = date.fromisoformat(str(member["date_of_birth"])) if member and member.get("date_of_birth") else None
        age = int(wage_month[:4]) - born.year - ((int(wage_month[5:7]), day_count) < (born.month, born.day)) if born else 0

        # Cap EPS/EDLI at ceiling if not international worker
        is_iw = bool(member and member.get("international_worker"))
        if not is_iw:
            eps_bound = capped_wages(epf_paise, c, "eps_wage_ceiling_paise") if split_month else c.get("eps_wage_ceiling_paise", 1500000)
            edli_bound = capped_wages(epf_paise, c, "edli_wage_ceiling_paise") if split_month else c.get("edli_wage_ceiling_paise", 1500000)
            eps_paise = min(eps_paise, eps_bound)
            edli_paise = min(edli_paise, edli_bound)

        gross_rupees = gross_paise // 100
        epf_rupees = epf_paise // 100
        eps_rupees = eps_paise // 100
        edli_rupees = edli_paise // 100

        # Exact split as in ecr.validate
        expected = split(epf_rupees * 100, 0 if (is_pensioner or not_eligible) else (eps_rupees * 100), age, rules, edli_rupees * 100)
        ee_rupees = expected["AC01_EPF_EE"] // 100
        eps_share_rupees = expected["AC10_EPS"] // 100
        er_rupees = expected["AC01_EPF_ER"] // 100

        line_fields = [
            uan,
            name,
            str(gross_rupees),
            str(epf_rupees),
            str(eps_rupees),
            str(edli_rupees),
            str(ee_rupees),
            str(eps_share_rupees),
            str(er_rupees),
            str(ncp_days),
            "0",  # Refund of Advances
        ]
        lines.append("#~#".join(line_fields))

    return "\n".join(lines)
