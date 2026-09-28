"""What a draft changes, and what that means in practice (worked examples), so an approver can see the
effect of a policy change before publishing it. Uses the same arithmetic as the services
(epfo_persistence.policy), never a copy."""
from typing import Any

from epfo_persistence.policy import approval_chain, auto_settle_limit, interest_on, pension_on, section, split, tds_on

ROLE = {"fo.da_accounts": "DA", "fo.ss": "SS", "fo.ao": "AO", "fo.apfc": "APFC", "fo.oic": "OIC"}
SAMPLE_WAGES = [1500000, 2000000, 2500000, 3000000]                 # ₹15,000 … ₹30,000 a month
SAMPLE_CLAIMS = [2000000, 5000000, 10000000, 60000000, 300000000]  # ₹20,000 … ₹30,00,000
SAMPLE_BALANCE = 10000000                                          # ₹1,00,000 held all year
SAMPLE_WITHDRAWALS = [4000000, 6000000, 30000000]                  # ₹40,000 … ₹3,00,000, after 3 years of service
SAMPLE_PENSIONS = [(650000, 12, 58), (1500000, 15, 58), (1500000, 25, 58), (1500000, 20, 55)]   # salary, years, age


def rupees(paise: int | None) -> str:
    if paise is None:
        return "—"
    whole = str(paise // 100)
    if len(whole) > 3:
        head, groups = whole[:-3], [whole[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups)
    return f"₹{whole}"


def diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Every changed leaf, as {path, before, after}; added / removed keys show None on the other side."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(set(before) | set(after), key=str):
            out.extend(diff(before.get(key), after.get(key), f"{path}.{key}" if path else str(key)))
        return out
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def contribution_examples(rules: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for wages in SAMPLE_WAGES:
        s = split(wages, wages, 30, rules)
        out.append({"monthly_wages": rupees(wages), "employee_epf": rupees(s["AC01_EPF_EE"]), "employer_eps": rupees(s["AC10_EPS"]),
                    "employer_epf": rupees(s["AC01_EPF_ER"]), "edli": rupees(s["AC21_EDLI"]), "total_challan": rupees(s["TOTAL"])})
    return out


def claim_examples(rules: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for code, spec in rules["claims"]["types"].items():
        limit = auto_settle_limit(rules, code)
        for amount in SAMPLE_CLAIMS:
            automatic = limit is not None and amount <= limit
            out.append({"claim_type": code, "label": spec["label"], "retired": bool(spec.get("retired")),
                        "amount": rupees(amount),
                        "decided_by": "automatic" if automatic else " → ".join(ROLE[r] for r in approval_chain(rules, code, amount))})
    return out


def interest_examples(rules: dict[str, Any]) -> dict[str, str]:
    return {fy: f"{rate / 100:g}% · {rupees(interest_on([SAMPLE_BALANCE] * 12, rate))}"
            for fy, rate in sorted(section(rules, "interest")["rates_bp"].items())}


def tds_examples(rules: dict[str, Any]) -> dict[tuple, str]:
    out = {}
    for claim_type in sorted(set(section(rules, "tds")["applies_to_claim_types"]) | {"FINAL_SETTLEMENT"}):
        for amount in SAMPLE_WITHDRAWALS:
            for pan in (True, False):
                t = tds_on(amount, claim_type, 36, pan, False, rules)
                out[(claim_type, rupees(amount), "verified" if pan else "not verified")] = rupees(t["tds_paise"]) if t["tds_paise"] else "no TDS"
    return out


def pension_examples(rules: dict[str, Any]) -> dict[tuple, str]:
    return {(rupees(salary), years, age): (lambda r: rupees(r["monthly_paise"]) if r["eligible"] else "not eligible")(
                pension_on(salary, years * 12, age, rules)) for salary, years, age in SAMPLE_PENSIONS}


def pensions_in_payment(rules: dict[str, Any]) -> str:
    p = section(rules, "pension")
    if not p["applies_to_pensions_in_payment"]:
        return "unchanged; the formula applies to new pensions only"
    since = f"from {p['revise_in_payment_from']}" if p.get("revise_in_payment_from") else "from the effective date"
    return f"revised {since} (never reduced); an APFC (Pension) approves each revision and its arrears"


def preview(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Worked examples under the current and the proposed rules, side by side, with only the rows that differ."""
    cb, ca = contribution_examples(before), contribution_examples(after)
    ib, ia = interest_examples(before), interest_examples(after)
    tb, ta = tds_examples(before), tds_examples(after)
    pb, pa = pension_examples(before), pension_examples(after)
    kb = {(r["claim_type"], r["amount"]): r for r in claim_examples(before)}
    ka = {(r["claim_type"], r["amount"]): r for r in claim_examples(after)}
    claims = [{"claim_type": k[0], "amount": k[1], "before": kb[k]["decided_by"] if k in kb else "not offered",
               "after": ("retired" if ka[k]["retired"] else ka[k]["decided_by"]) if k in ka else "not offered"}
              for k in sorted(set(kb) | set(ka))]
    return {"contribution": [{"monthly_wages": b["monthly_wages"], "before": b, "after": a} for b, a in zip(cb, ca) if b != a],
            "claims": [c for c in claims if c["before"] != c["after"]],
            "interest": [{"financial_year": fy, "before": ib.get(fy, "not declared"), "after": ia.get(fy, "not declared")}
                         for fy in sorted(set(ib) | set(ia)) if ib.get(fy) != ia.get(fy)],
            "tds": [{"claim_type": k[0], "amount": k[1], "pan": k[2], "before": tb.get(k, "no TDS"), "after": ta.get(k, "no TDS")}
                    for k in sorted(set(tb) | set(ta)) if tb.get(k, "no TDS") != ta.get(k, "no TDS")],
            "pension": [{"salary": k[0], "service_years": k[1], "age": k[2], "before": pb[k], "after": pa[k]} for k in pb if pb[k] != pa[k]],
            "pensions_in_payment": pensions_in_payment(after),
            "note": ("Worked examples: contributions at age 30; claim amounts are samples; interest on ₹1,00,000 held all year; TDS on "
                     "withdrawals after 3 years of service; pensions at the salary, service and age shown. Same arithmetic as the services.")}
