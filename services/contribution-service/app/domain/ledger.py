"""Pure balanced journal builder for confirmed synthetic challan payments."""
from typing import Any


def build_postings(rows: list[dict[str, Any]], totals: dict[str, int]) -> list[dict[str, Any]]:
    postings = [{"account_code": "BANK_COLLECTION", "side": "debit", "amount_paise": totals["TOTAL"]}]
    for row in rows:
        for account, side, share in (("AC01_EPF", "credit", "employee"), ("AC01_EPF", "credit", "employer")):
            amount = int(row["shares"][share])
            if amount:
                postings.append({"account_code": account, "side": side, "amount_paise": amount,
                                 "account_link_id": row["account_link_id"], "share": share})
        for account in ("AC10_EPS", "AC21_EDLI", "AC02_ADMIN", "AC22_EDLI_ADMIN"):
            amount = int(row.get(account, 0))
            if amount:
                postings.append({"account_code": account, "side": "credit", "amount_paise": amount})
    debits = sum(x["amount_paise"] for x in postings if x["side"] == "debit")
    credits = sum(x["amount_paise"] for x in postings if x["side"] == "credit")
    if debits != credits:
        raise ValueError(f"unbalanced journal: {debits} != {credits}")
    return postings
