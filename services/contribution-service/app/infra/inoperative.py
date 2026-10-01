"""Shared eligibility calculation for the office and public inoperative-account flows."""
from datetime import UTC, date, datetime

from sqlalchemy import text

from epfo_persistence.policy import rules_on, section


async def months_rule(session) -> int:
    rules = await rules_on(session, date.today())
    return int(section(rules, "inoperative_accounts").get("months_without_credit", 36))


def cutoff_for(months: int) -> date:
    today = datetime.now(UTC).date()
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    return date(year, month + 1, 1)


async def accounts(session, months: int) -> list[dict]:
    """Positive EPF balance and no EPF credit since the rule's month cutoff. Interest is not a transaction: an account
    that only earns interest stays inoperative (SOP on transaction-less and inoperative accounts)."""
    rows = (await session.execute(text(
        "SELECT m.account_link_id, m.uan, m.name, m.date_of_birth, m.establishment_id, e.legal_name AS establishment_name, "
        "m.date_of_exit, v.account_link_id AS verified_id, r.account_link_id AS reactivated_id, "
        "SUM(CASE WHEN jl.side='credit' THEN jl.amount_paise ELSE -jl.amount_paise END) AS balance, "
        "MAX(CASE WHEN jl.side='credit' AND j.kind NOT IN ('INTEREST', 'INTEREST_REVISION') THEN j.occurred_at END) AS last_credit "
        "FROM establishment_members m JOIN establishments e ON e.id=m.establishment_id "
        "JOIN journal_lines jl ON jl.account_link_id=m.account_link_id AND jl.account_code='AC01_EPF' "
        "JOIN journals j ON j.id=jl.journal_id "
        "LEFT JOIN inoperative_verifications v ON v.account_link_id=m.account_link_id "
        "LEFT JOIN account_reactivations r ON r.account_link_id=m.account_link_id "
        "GROUP BY m.account_link_id, m.uan, m.name, m.date_of_birth, m.establishment_id, e.legal_name, "
        "m.date_of_exit, v.account_link_id, r.account_link_id"))).mappings().all()
    cutoff = cutoff_for(months)
    out = []
    for row in rows:
        item = dict(row)
        last = item["last_credit"]
        last_day = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10]) if last else None
        if int(item["balance"] or 0) > 0 and (last_day is None or last_day < cutoff):
            item["balance"] = int(item["balance"])
            item["last_credit_day"] = last_day
            item["verified"] = item["verified_id"] is not None
            item["reactivated"] = item["reactivated_id"] is not None
            out.append(item)
    return out
