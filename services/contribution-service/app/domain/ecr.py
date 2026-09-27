"""Pure ECR parsing, illustrative contribution math, and actionable validation."""
from __future__ import annotations

import calendar
import csv
import io
import re
from datetime import date
from typing import Any

FIELDS = ["UAN", "Member Name", "Gross Wages", "EPF Wages", "EPS Wages", "EDLI Wages",
          "EPF Contribution (EE share)", "EPS Contribution", "EPF-EPS Difference (ER share)", "NCP Days", "Refund of Advances"]
AMOUNTS = FIELDS[2:9] + [FIELDS[10]]
ARITHMETIC = FIELDS[6:9]
ACCOUNTS = ("AC01_EPF_EE", "AC01_EPF_ER", "AC10_EPS", "AC21_EDLI", "AC02_ADMIN", "AC22_EDLI_ADMIN", "TOTAL")


# The contribution split is shared with platform-service's policy preview, so both use the same arithmetic.
from epfo_persistence.policy import round_rupee_half_up, split  # noqa: E402,F401


def _masked_uan(uan: str) -> str:
    return "X" * max(0, len(uan) - 4) + uan[-4:]


def parse(content: str, fmt: str) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
    """Parse ECR TXT (11 #~# separated fields) or CSV with a header."""
    warnings = []
    normalized = content
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
        warnings.append({"row": 0, "uan_masked": None, "field": "file", "code": "W-FORMAT-NORMALISED", "severity": "warning", "message": "A byte order mark was removed.", "expected": None, "actual": "BOM", "fix": "No action needed; the file was normalised.", "auto_fixable": True})
    if "\r" in normalized:
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        warnings.append({"row": 0, "uan_masked": None, "field": "file", "code": "W-FORMAT-NORMALISED", "severity": "warning", "message": "Line endings were normalised.", "expected": "LF", "actual": "CRLF", "fix": "No action needed; the file was normalised.", "auto_fixable": True})
    lines = normalized.splitlines()
    rows: list[dict[str, str]] = []
    if fmt == "CSV":
        try:
            parsed = list(csv.reader(io.StringIO("\n".join(lines))))
            if parsed and [x.strip().casefold() for x in parsed[0]] == [x.casefold() for x in FIELDS]:
                parsed = parsed[1:]
            for fields in parsed:
                item = dict(zip(FIELDS, fields))
                if len(fields) != len(FIELDS):
                    item["__field_count"] = str(len(fields))
                rows.append(item)
        except csv.Error:
            rows = []
    else:
        for line in lines:
            rows.append(dict(zip(FIELDS, line.split("#~#"))))
    # Preserve bad field count as a marker for row-level validation.
    for i, line in enumerate(lines if fmt != "CSV" else []):
        if len(line.split("#~#")) != 11 and i < len(rows):
            rows[i]["__field_count"] = str(len(line.split("#~#")))
    changed = False
    for row in rows:
        for key, value in list(row.items()):
            if key.startswith("__"):
                continue
            fixed = value.strip()
            changed |= fixed != value
            row[key] = fixed
    if changed:
        warnings.append({"row": 0, "uan_masked": None, "field": "file", "code": "W-FORMAT-NORMALISED", "severity": "warning", "message": "Leading or trailing spaces were removed.", "expected": "trimmed values", "actual": "spaces", "fix": "No action needed; the file was normalised.", "auto_fixable": True})
    return rows, warnings, normalized


def validate(content: str, fmt: str, wage_month: str, members: list[dict[str, Any]], rules: dict[str, Any], last_posted: dict[str, Any] | None = None) -> dict[str, Any]:
    rows, issues, _ = parse(content, fmt)
    by_uan = {str(m["uan"]): m for m in members}
    seen: set[str] = set()
    totals = {a: 0 for a in ACCOUNTS}
    aggregate_epf_wages = 0
    accepted = 0
    corrected: list[str] = []
    day_count = calendar.monthrange(int(wage_month[:4]), int(wage_month[5:7]))[1]

    def issue(i: int, row: dict[str, str], field: str, code: str, severity: str, msg: str, expected: Any = None, actual: Any = None, fix: str = "Correct this row and upload the file again.", auto: bool = False) -> None:
        issues.append({"row": i, "uan_masked": _masked_uan(row.get("UAN", "")), "field": field, "code": code,
                       "severity": severity, "message": msg, "expected": str(expected) if expected is not None else None,
                       "actual": str(actual) if actual is not None else None, "fix": fix, "auto_fixable": auto})

    if not rows:
        issue(1, {}, "row", "E-FORMAT-FIELDS", "error", "The file must contain at least one member row with 11 fields.", 11, 0)

    for i, row in enumerate(rows, 1):
        if "__field_count" in row:
            issue(i, row, "row", "E-FORMAT-FIELDS", "error", "This row must contain exactly 11 fields.", 11, row["__field_count"])
        uan = row.get("UAN", "")
        if uan in seen:
            issue(i, row, "UAN", "E-DUPLICATE-UAN", "error", "This UAN appears more than once in the file.", fix="Keep only one row for this UAN.")
        seen.add(uan)
        member = by_uan.get(uan)
        if not member:
            issue(i, row, "UAN", "E-UAN-UNKNOWN", "error", "This UAN is not an employee of this establishment.", fix="Check the UAN or establishment employment record.")
        elif re.sub(r"\s+", " ", row.get("Member Name", "")).casefold() != re.sub(r"\s+", " ", str(member["name"])).strip().casefold():
            name = str(member["name"])
            masked = " ".join((p[:1] + "***") if p else "" for p in name.split())
            issue(i, row, "Member Name", "E-NAME-MISMATCH", "error", f"The name differs from the establishment record ({masked}).", fix="correct the file or raise a Joint Declaration")
        numeric: dict[str, int] = {}
        for field in AMOUNTS:
            value = row.get(field, "")
            if not re.fullmatch(r"\d+", value):
                issue(i, row, field, "E-FORMAT-NUMBER", "error", "Enter a whole, non-negative number of rupees without decimals or separators.", actual=value)
            else:
                numeric[field] = int(value) * 100
        ncp = row.get("NCP Days", "")
        if not re.fullmatch(r"\d+", ncp):
            issue(i, row, "NCP Days", "E-FORMAT-NUMBER", "error", "Enter whole NCP days without decimals or separators.", actual=ncp)
        elif int(ncp) > day_count:
            issue(i, row, "NCP Days", "E-NCP-DAYS", "error", f"NCP days cannot exceed {day_count} days in this wage month.", day_count, ncp)
        if numeric:
            gross, epf, eps, edli = (numeric.get(x, 0) for x in FIELDS[2:6])
            aggregate_epf_wages += epf
            if epf > gross or eps > epf or edli > epf:
                issue(i, row, "EPF Wages", "E-WAGE-ORDER", "error", "Wages must satisfy EPF ≤ gross and EPS/EDLI ≤ EPF.", fix="Correct the wage amounts using payroll records.")
            c = rules["contribution"]
            if eps > c["eps_wage_ceiling_paise"] or edli > c["edli_wage_ceiling_paise"]:
                issue(i, row, "EPS/EDLI Wages", "E-EPS-CEILING", "error", "EPS and EDLI wages cannot exceed the illustrative wage ceiling.", c["eps_wage_ceiling_paise"] // 100)
            born = date.fromisoformat(str(member["date_of_birth"])) if member and member.get("date_of_birth") else None
            age = int(wage_month[:4]) - born.year - ((int(wage_month[5:7]), day_count) < (born.month, born.day)) if born else 0
            expected = split(epf, eps, age, rules, edli)
            for field, account in zip(ARITHMETIC, ("AC01_EPF_EE", "AC10_EPS", "AC01_EPF_ER")):
                got = numeric.get(field, -1)
                if got != expected[account]:
                    code = {ARITHMETIC[0]: "E-EPF-EE", ARITHMETIC[1]: "E-EPS-SHARE", ARITHMETIC[2]: "E-DIFF-SHARE"}[field]
                    issue(i, row, field, code, "error", f"{field} does not match the illustrative contribution calculation.", expected[account] // 100, got // 100 if got >= 0 else row.get(field), fix="Replace this amount with the expected whole-rupee value.", auto=True)
                    row[field] = str(expected[account] // 100)
            eps_share_input = numeric.get(FIELDS[7], 0)
            if born and age >= rules["contribution"]["eps_age_limit_years"] and (eps > 0 or eps_share_input > 0 or expected["AC10_EPS"] > 0):
                issue(i, row, "EPS Wages", "E-AGE-EPS", "error", "This member is at or above the illustrative EPS age limit for the wage month.", 0, eps // 100, "EPS = 0 and the whole employer share goes to EPF")
                row["EPS Contribution"] = "0"
                row["EPF-EPS Difference (ER share)"] = str(expected["AC01_EPF_EE"] // 100)
            if all(k in numeric for k in FIELDS[2:9]):
                row_total = split(epf, eps, age, rules, edli)
                for account in ("AC01_EPF_EE", "AC01_EPF_ER", "AC10_EPS", "AC21_EDLI"):
                    totals[account] += row_total[account]
            if gross == epf == 0:
                issue(i, row, "Gross Wages", "W-ZERO-WAGES", "warning", "This row has zero wages.", fix="Confirm this is intentional; remove the row if the member had no employment.")
        corrected.append("#~#".join(row.get(f, "") for f in FIELDS))
        if not any(x["row"] == i and x["severity"] == "error" for x in issues):
            accepted += 1
    present = {r.get("UAN") for r in rows}
    for m in members:
        if m.get("status", "ACTIVE") == "ACTIVE" and m["uan"] not in present:
            issue(0, {"UAN": str(m["uan"])}, "UAN", "W-MISSING-MEMBER", "warning", "An active employee is missing from this file.", fix="mark exit if they left")
    c = rules["contribution"]
    totals["AC02_ADMIN"] = max(c["admin_charges_min_paise"], round_rupee_half_up(aggregate_epf_wages * c["admin_charges_rate_bp"])) if rows else 0
    totals["AC22_EDLI_ADMIN"] = round_rupee_half_up(aggregate_epf_wages * c["edli_admin_rate_bp"])
    totals["TOTAL"] = sum(totals[a] for a in ACCOUNTS[:-1])
    comparison = None
    if last_posted:
        now_count = len(rows)
        delta_pct = abs(now_count - last_posted["members_then"]) * 100 / max(1, last_posted["members_then"])
        comparison = {**last_posted, "members_now": now_count, "total_now_paise": totals["TOTAL"]}
        if delta_pct > rules["validation"]["headcount_change_warning_pct"]:
            issue(0, {}, "headcount", "W-HEADCOUNT-CHANGE", "warning", "The member count differs from the last posted month by more than the configured threshold.", fix="Review joiners and leavers before submission.")
    issues.sort(key=lambda x: (x["severity"] != "error", x["row"]))
    errors = sum(x["severity"] == "error" for x in issues)
    can_correct = any(x["code"] in {"E-EPF-EE", "E-EPS-SHARE", "E-DIFF-SHARE"} and x["auto_fixable"] for x in issues) and not any(x["code"] == "E-FORMAT-FIELDS" for x in issues)
    return {"summary": {"rows": len(rows), "accepted_rows": accepted, "rows_with_errors": len({x["row"] for x in issues if x["severity"] == "error"}),
            "warnings": sum(x["severity"] == "warning" for x in issues), "totals_paise": totals,
            "comparison_with_last_posted_month": comparison}, "issues": issues,
            "corrected_content": "\n".join(corrected) if can_correct else None,
            "valid": errors == 0}
