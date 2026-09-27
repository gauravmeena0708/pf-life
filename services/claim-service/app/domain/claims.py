"""Claim rules: eligibility, approval chain and the plain-language summary (init.md §7, Journey B3).

Everything here is deterministic and reads only the frozen rule set passed in, so a decision can be
reproduced from the stored evaluation snapshot."""
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(os.getenv("RULES_FILE", "/srv/demo-rules.yaml"))

OPEN_STATES = {"AWAITING_CONFIRMATION", "SUBMITTED", "UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL",
               "APPROVED", "AUTO_APPROVED", "PAYMENT_PENDING", "PAYMENT_RETURNED"}

ROLE_LABELS = {
    "member": "You", "system": "EPFO system (automatic)", "fo.da_accounts": "Dealing assistant (accounts)",
    "fo.ss": "Section supervisor", "fo.ao": "Accounts officer", "fo.apfc": "Assistant PF commissioner",
    "fo.oic": "Officer in charge", "fo.cash": "Cash section", "bank": "Bank (mock)",
}

NEXT_STEP = {
    "AWAITING_CONFIRMATION": "Check the summary and confirm the claim with the one-time code.",
    "SUBMITTED": "Your claim is being checked.",
    "UNDER_REVIEW": "A dealing assistant in your regional office will review your claim.",
    "RECOMMENDED": "Your claim has been recommended and is waiting for an approving officer.",
    "AWAITING_NEXT_APPROVAL": "One approval is recorded; the next approving officer will now decide.",
    "APPROVED": "Your claim is approved. The cash section will send the payment to your bank.",
    "AUTO_APPROVED": "Your claim was approved automatically. The payment will be sent to your bank.",
    "PAYMENT_PENDING": "The payment has been sent to the bank; it usually shows in a few seconds in this demo.",
    "SETTLED": "Paid. Nothing more to do.",
    "PAYMENT_RETURNED": "The bank returned the payment. The cash section will re-issue it; check your bank details.",
    "REJECTED_WITH_REASON": "Your claim was rejected. The reason is shown above; you can file a new claim once it is resolved.",
}


@lru_cache(maxsize=1)
def ruleset() -> dict[str, Any]:
    path = RULES_PATH if RULES_PATH.exists() else Path(__file__).resolve().parents[4] / "config" / "demo-rules.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def rupees(paise: int) -> str:
    """₹ with Indian digit grouping, e.g. 60000000 → ₹6,00,000."""
    whole, frac = divmod(paise, 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups + [tail])
    return f"₹{s}" + (f".{frac:02d}" if frac else "")


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)


def eligibility(account: dict[str, Any], claim_type: str, rules: dict[str, Any], today: date) -> dict[str, Any]:
    """Whether this account may claim this type today, the maximum amount, and why."""
    spec = rules["claims"]["types"][claim_type]
    employee, employer = int(account["employee_paise"]), int(account["employer_paise"])
    reasons: list[str] = []
    exited = account.get("date_of_exit")
    if spec.get("requires_active_employment") and exited:
        reasons.append("This advance is only for members who are still employed.")
    if "requires_exit_months" in spec:
        if not exited:
            reasons.append("Final settlement is available only after you leave employment.")
        elif months_between(exited, today) < spec["requires_exit_months"]:
            reasons.append(f"Final settlement is available {spec['requires_exit_months']} months after leaving employment.")
    base = employee if spec["max_from"] == "employee_share" else employee + employer
    maximum = min(base, spec["cap_paise"]) if spec.get("cap_paise") else base
    if maximum <= 0:
        reasons.append("There is no balance available for this claim yet.")
    return {
        "claim_type": claim_type, "form_type": spec["form_type"], "label": spec["label"], "plain_rule": spec["plain_rule"],
        "eligible": not reasons, "max_amount_paise": maximum if not reasons else 0, "reasons": reasons,
        "trace": {"employee_paise": employee, "employer_paise": employer, "max_from": spec["max_from"],
                  "cap_paise": spec.get("cap_paise"), "date_of_exit": exited.isoformat() if exited else None,
                  "evaluated_on": today.isoformat(), "rule_version": rules["rule_version"]},
    }


def approval_chain(amount_paise: int, rules: dict[str, Any]) -> list[str]:
    for band in rules["claims"]["approval_bands"]:
        if band["upto_paise"] is None or amount_paise <= band["upto_paise"]:
            return list(band["chain"])
    raise ValueError("no approval band")


def route(amount_paise: int, rules: dict[str, Any]) -> str:
    return "AUTO" if amount_paise <= rules["claims"]["auto_settlement_limit_paise"] else "REVIEW"


def summary(evaluation: dict[str, Any], amount_paise: int, rules: dict[str, Any]) -> str:
    chain = approval_chain(amount_paise, rules)
    if route(amount_paise, rules) == "AUTO":
        path = "It is within the automatic settlement limit, so it can be approved without an officer."
    else:
        path = ("It is above the automatic settlement limit of "
                f"{rupees(rules['claims']['auto_settlement_limit_paise'])}, so it will be reviewed by: "
                + " → ".join(ROLE_LABELS[r] for r in chain) + ".")
    return (f"You are claiming {rupees(amount_paise)} as '{evaluation['label']}' (Form {evaluation['form_type']}). "
            f"Rule: {evaluation['plain_rule']} Your maximum today is {rupees(evaluation['max_amount_paise'])}. "
            f"{path} The money will be paid to the bank account linked to your UAN. "
            f"Illustrative rules {rules['rule_version']} (not official EPFO limits).")
