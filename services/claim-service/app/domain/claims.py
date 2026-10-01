"""Claim rules: eligibility, approval chain and the plain-language summary (init.md §7, Journey B3).

Everything here is deterministic and reads only the frozen rule set passed in, so a decision can be
reproduced from the stored evaluation snapshot."""
from datetime import date
from typing import Any

from epfo_persistence.policy import approval_chain as chain_for, auto_settle_limit, section

OPEN_STATES = {"AWAITING_CONFIRMATION", "SUBMITTED", "PENDING_EMPLOYER_ATTESTATION", "PENDING_EDLI_DECISION", "UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL",
               "APPROVED", "AUTO_APPROVED", "PAYMENT_PENDING", "PAYMENT_RETURNED", "CORRECTION_PENDING",
               "REISSUE_APPROVED", "ON_HOLD_FROZEN"}
# Held while the account is frozen: any state before the payment has gone to the bank (init.md §7).
HOLDABLE = {"SUBMITTED", "PENDING_EMPLOYER_ATTESTATION", "PENDING_EDLI_DECISION", "UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL", "APPROVED", "AUTO_APPROVED",
            "PAYMENT_RETURNED", "CORRECTION_PENDING", "REISSUE_APPROVED"}

ROLE_LABELS = {
    "member": "You", "system": "EPFO system (automatic)", "fo.da_accounts": "Dealing assistant (accounts)",
    "fo.ss": "Section supervisor", "fo.ao": "Accounts officer", "fo.apfc": "Assistant PF commissioner",
    "fo.oic": "Officer in charge", "fo.cash": "Cash section", "bank": "Bank (mock)",
    "fo.fa_accounts": "Accounts wing (F&A)", "fo.edli": "EDLI section", "employer.signatory": "Your employer (authorised signatory)", "claimant": "Claimant (nominee)",
}
# Before payment the member may switch the claim to another of their KYC-verified bank accounts (P2.8b).
BANK_SWITCHABLE = {"PENDING_EMPLOYER_ATTESTATION", "SUBMITTED", "UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL",
                   "APPROVED", "AUTO_APPROVED"}
# A member may withdraw a claim only before an approving officer has decided on it.
CANCELLABLE = {"AWAITING_CONFIRMATION", "SUBMITTED", "PENDING_EMPLOYER_ATTESTATION", "UNDER_REVIEW", "RECOMMENDED"}

NEXT_STEP = {
    "AWAITING_CONFIRMATION": "Check the summary and confirm the claim with the one-time code.",
    "SUBMITTED": "Your claim is being checked.",
    "PENDING_EMPLOYER_ATTESTATION": "Your Aadhaar is not verified yet, so your employer must attest the claim before it goes to the office.",
    "PENDING_EDLI_DECISION": "Admitted by the office; the EDLI section verifies the wages and decides the benefit.",
    "REJECTED_BY_EMPLOYER": "Your employer did not attest the claim. The reason is shown above; you can file a new claim.",
    "UNDER_REVIEW": "A dealing assistant in your regional office will review your claim.",
    "RECOMMENDED": "Your claim has been recommended and is waiting for an approving officer.",
    "AWAITING_NEXT_APPROVAL": "One approval is recorded; the next approving officer will now decide.",
    "APPROVED": "Your claim is approved. The cash section will send the payment to your bank.",
    "AUTO_APPROVED": "Your claim was approved automatically. The payment will be sent to your bank.",
    "PAYMENT_PENDING": "The payment has been sent to the bank; it usually shows in a few seconds in this demo.",
    "SETTLED": "Paid. Nothing more to do.",
    "PAYMENT_RETURNED": "The bank returned the payment. Enter your correct bank details below; an APFC approves the re-payment.",
    "CORRECTION_PENDING": "Your new bank details are with an APFC for approval.",
    "REISSUE_APPROVED": "The re-payment is approved; the cash section will send it to your new account.",
    "ON_HOLD_FROZEN": "Your claim is on hold while your account is being verified. You do not need to do anything.",
    "REJECTED_WITH_REASON": "Your claim was rejected. The reason is shown above; you can file a new claim once it is resolved.",
    "CANCELLED": "You withdrew this claim. You can file a new one.",
}


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


def international_worker_reasons(account: dict[str, Any], claim_type: str, rules: dict[str, Any], today: date) -> list[str]:
    """Why an international worker may not make this claim (empty: they may)."""
    iw = section(rules, "international_workers")
    if claim_type not in iw["claim_types"]:
        return ["Not available to international workers: their PF is paid only as a final settlement "
                "(illustrative international-worker rules)."]
    if claim_type != "FINAL_SETTLEMENT":
        return []
    on, born = iw["final_settlement_on"], account.get("date_of_birth")
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day)) if born else 0
    if age >= on["min_age"] or (account.get("nationality") or "") in on["agreement_nationalities"]:
        return []
    return [f"An international worker's final settlement is paid at the age of {on['min_age']}, or earlier only when "
            f"their country has a social-security agreement with India that allows it (illustrative)."]


def eligibility(account: dict[str, Any], claim_type: str, rules: dict[str, Any], today: date,
                previous_claims: list[date] | None = None) -> dict[str, Any]:
    """Whether this account may claim this type today, the maximum amount, and why — using only the
    conditions the rule set declares for the type (see config/demo-rules.yaml)."""
    spec = rules["claims"]["types"][claim_type]
    employee, employer = int(account["employee_paise"]), int(account["employer_paise"])
    reasons: list[str] = []
    exited = account.get("date_of_exit")
    joined = account.get("date_of_joining")
    if spec.get("retired"):
        reasons.append("This claim type is no longer offered.")
    if spec.get("requires_active_employment") and exited:
        reasons.append("This advance is only for members who are still employed.")
    if spec.get("requires_exit_months") is not None:
        if not exited:
            reasons.append("This claim is available only after you leave employment.")
        elif months_between(exited, today) < spec["requires_exit_months"]:
            reasons.append(f"This claim is available {spec['requires_exit_months']} months after leaving employment.")
    if spec.get("min_service_months") and joined and months_between(joined, exited or today) < spec["min_service_months"]:
        reasons.append(f"You need at least {spec['min_service_months'] // 12} years "
                       f"{'and ' + str(spec['min_service_months'] % 12) + ' months ' if spec['min_service_months'] % 12 else ''}of service.")
    if spec.get("once_every_months") and any(months_between(d, today) < spec["once_every_months"] for d in previous_claims or []):
        reasons.append(f"This claim can be made once every {spec['once_every_months']} months.")
    if account.get("international_worker"):                    # P2.9a: the international-worker rules (illustrative)
        reasons += international_worker_reasons(account, claim_type, rules, today)
    exemption = account.get("exemption") or {}
    trust_rules = section(rules, "exempted_establishments")
    effective = exemption.get("effective_from")
    if (exemption.get("pf_exempt") and exemption.get("status") == "ACTIVE"
            and claim_type in trust_rules["trust_claim_types"] and effective
            and joined and joined <= today and (exited is None or exited >= effective) and effective <= today):
        reasons.append(f"Your PF for this member ID is with {exemption['trust_name']}; the trust settles it within "
                       f"{trust_rules['trust_claim_days']} days (Condition 12).")
    served = months_between(joined, exited or today) if joined else 0
    if spec.get("max_service_months") is not None and served > spec["max_service_months"]:
        reasons.append("With this much service a monthly pension or a scheme certificate applies instead (Form 10D / 10C).")
    if spec["max_from"] == "eps_table_d":             # pension withdrawal benefit: Table D factor x wages (illustrative)
        years = served // 12 + (1 if served % 12 >= 6 else 0)
        table = spec["table_d_factor_x100"]
        if years < 1:
            reasons.append("At least six months of pension (EPS) service are needed.")
        wages = rules["contribution"]["eps_wage_ceiling_paise"]
        base = wages * table[min(years, len(table)) - 1] // 100 if years >= 1 else 0
    else:
        base = employee if spec["max_from"] == "employee_share" else employee + employer
    maximum = base * spec.get("max_pct_bp", 10000) // 10000
    if spec.get("cap_paise"):
        maximum = min(maximum, spec["cap_paise"])
    if maximum <= 0:
        reasons.append("There is no balance available for this claim yet.")
    return {
        "claim_type": claim_type, "form_type": spec["form_type"], "label": spec["label"], "plain_rule": spec["plain_rule"],
        "eligible": not reasons, "max_amount_paise": maximum if not reasons else 0, "reasons": reasons,
        "trace": {"employee_paise": employee, "employer_paise": employer, "max_from": spec["max_from"],
                  "max_pct_bp": spec.get("max_pct_bp", 10000), "cap_paise": spec.get("cap_paise"),
                  "date_of_exit": exited.isoformat() if exited else None, "evaluated_on": today.isoformat(),
                  "rule_version": rules["rule_version"]},
    }


def approval_chain(amount_paise: int, rules: dict[str, Any], claim_type: str) -> list[str]:
    return chain_for(rules, claim_type, amount_paise)


def route(amount_paise: int, rules: dict[str, Any], claim_type: str) -> str:
    limit = auto_settle_limit(rules, claim_type)
    return "AUTO" if limit is not None and amount_paise <= limit else "REVIEW"


def tax_note(claim_type: str, rules: dict[str, Any]) -> str:
    t = section(rules, "tds")
    if claim_type not in t["applies_to_claim_types"]:
        return ""
    return (f" Income tax may be deducted at source (TDS) under the rules in force on the payment date: from {rupees(t['threshold_paise'])}, "
            f"before {t['exempt_after_service_months'] // 12} years of service, unless you have filed Form 15G / 15H for the year.")


def summary(evaluation: dict[str, Any], amount_paise: int, rules: dict[str, Any]) -> str:
    claim_type = evaluation["claim_type"]
    chain = approval_chain(amount_paise, rules, claim_type)
    limit = auto_settle_limit(rules, claim_type)
    if route(amount_paise, rules, claim_type) == "AUTO":
        path = "It is within the automatic settlement limit, so it can be approved without an officer."
    else:
        why = (f"It is above the automatic settlement limit of {rupees(limit)}" if limit is not None
               else "This type of claim is always decided by officers")
        path = f"{why}, so it will be reviewed by: " + " → ".join(ROLE_LABELS[r] for r in chain) + "."
    return (f"You are claiming {rupees(amount_paise)} as '{evaluation['label']}' (Form {evaluation['form_type']}). "
            f"Rule: {evaluation['plain_rule']} Your maximum today is {rupees(evaluation['max_amount_paise'])}. "
            f"{path} The money will be paid to the bank account linked to your UAN.{tax_note(claim_type, rules)} "
            f"Illustrative rules {rules['rule_version']} (not official EPFO limits).")
