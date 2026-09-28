"""Annual interest crediting (policy-driven).

The rate for a financial year is part of the published rule set (interest.rates_bp); the run uses the version in
force on the day it runs, so a revised rate published later is picked up by the next run. Interest is worked out
on each month's closing balance of the employee and employer shares (monthly running balance) and credited as a
balanced journal dated the last day of the year. A second run for the same year credits (or recovers) only the
difference from what is already credited, as a separate journal; nothing is ever edited."""
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from epfo_persistence import add_event
from epfo_persistence.policy import financial_year_bounds, interest_on, month_ends

PRODUCER = "contribution-service"
SHARES = ("employee", "employer")


def _end_of(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=UTC)


def _as_utc(at: datetime | str) -> datetime:
    at = datetime.fromisoformat(at) if isinstance(at, str) else at   # SQLite (unit tests) returns text, often naive
    return at if at.tzinfo else at.replace(tzinfo=UTC)


async def interest_due(session: AsyncSession, fy: str, rate_bp: int) -> list[dict[str, Any]]:
    """Per account: interest due at the rate, already credited for the year, and the difference to post now."""
    ends = [_end_of(d) for d in month_ends(fy)]
    accounts = (await session.execute(text(
        "SELECT DISTINCT account_link_id, member_subject FROM establishment_members ORDER BY account_link_id"))).mappings().all()
    out = []
    for a in accounts:
        rows = (await session.execute(text(
            "SELECT j.occurred_at, jl.share, jl.side, jl.amount_paise, ip.financial_year AS interest_year "
            "FROM journal_lines jl JOIN journals j ON j.id = jl.journal_id "
            "LEFT JOIN interest_postings ip ON ip.journal_id = j.id "
            "WHERE jl.account_code = 'AC01_EPF' AND jl.account_link_id = :a AND j.occurred_at <= :last"),
            {"a": a["account_link_id"], "last": ends[-1]})).mappings().all()
        shares = {}
        for share in SHARES:
            own = [r for r in rows if r["share"] == share]
            signed = [(_as_utc(r["occurred_at"]), r["amount_paise"] if r["side"] == "credit" else -r["amount_paise"], r["interest_year"])
                      for r in own]
            # This year's own interest is not part of the balance it is worked out on.
            closing = [sum(v for at, v, year in signed if at <= end and year != fy) for end in ends]
            due = interest_on(closing, rate_bp)
            credited = sum(v for _, v, year in signed if year == fy)
            shares[share] = {"due_paise": due, "credited_paise": credited, "now_paise": due - credited}
        out.append({"account_link_id": a["account_link_id"], "member_subject": a["member_subject"], **shares,
                    "to_credit_paise": sum(shares[s]["now_paise"] for s in SHARES)})
    return out


async def post_interest(session: AsyncSession, fy: str, rate_bp: int, rule_version: str, actor_subject: str,
                        correlation_id: str | None) -> list[dict[str, Any]]:
    """Credit the difference for every account, once per rule version. Returns the postings made."""
    _, last_day = financial_year_bounds(fy)
    posted = []
    for a in await interest_due(session, fy, rate_bp):
        if not a["to_credit_paise"]:
            continue
        key = f"INTEREST-{fy}-{a['account_link_id']}-{rule_version}"
        if (await session.execute(text("SELECT 1 FROM journals WHERE business_key = :k"), {"k": key})).first():
            continue
        earlier = (await session.execute(text("SELECT COUNT(*) FROM interest_postings WHERE financial_year = :y AND account_link_id = :a"),
                                         {"y": fy, "a": a["account_link_id"]})).scalar_one()
        lines = []
        for share in SHARES:
            n = a[share]["now_paise"]
            if n:
                lines.append({"account_code": "AC01_EPF", "side": "credit" if n > 0 else "debit", "amount_paise": abs(n),
                              "account_link_id": a["account_link_id"], "share": share})
        net = a["to_credit_paise"]
        lines.append({"account_code": "INTEREST_EXPENSE", "side": "debit" if net > 0 else "credit", "amount_paise": abs(net)})
        if sum(x["amount_paise"] for x in lines if x["side"] == "debit") != sum(x["amount_paise"] for x in lines if x["side"] == "credit"):
            raise ValueError(f"unbalanced interest journal for {a['account_link_id']}")      # shares moved in opposite directions
        journal_id = str(uuid.uuid4())
        await session.execute(text("INSERT INTO journals (id, business_key, kind, occurred_at, filing_id, claim_id) "
                                   "VALUES (:id, :k, :kind, :at, NULL, NULL)"),
                              {"id": journal_id, "k": key, "kind": "INTEREST_REVISION" if earlier else "INTEREST", "at": _end_of(last_day)})
        for line in lines:
            await session.execute(text("INSERT INTO journal_lines (journal_id, account_code, side, amount_paise, account_link_id, share) "
                                       "VALUES (:j, :a, :s, :n, :l, :h)"),
                                  {"j": journal_id, "a": line["account_code"], "s": line["side"], "n": line["amount_paise"],
                                   "l": line.get("account_link_id"), "h": line.get("share")})
        await session.execute(text(
            "INSERT INTO interest_postings (journal_id, financial_year, account_link_id, rule_version, rate_bp, employee_paise, "
            "employer_paise, revision, posted_by, posted_at) VALUES (:j, :y, :a, :v, :r, :ee, :er, :n, :by, :at)"),
            {"j": journal_id, "y": fy, "a": a["account_link_id"], "v": rule_version, "r": rate_bp, "ee": a["employee"]["now_paise"],
             "er": a["employer"]["now_paise"], "n": earlier, "by": actor_subject, "at": datetime.now(UTC)})
        posted.append({"account_link_id": a["account_link_id"], "journal_id": journal_id, "employee_paise": a["employee"]["now_paise"],
                       "employer_paise": a["employer"]["now_paise"], "revision": earlier})
        if a["member_subject"]:
            await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                            aggregate_id=journal_id, correlation_id=correlation_id, payload={
                                "recipient_subject": a["member_subject"], "template": "INTEREST_REVISED" if earlier else "INTEREST_CREDITED",
                                "reference_id": a["account_link_id"],
                                "params": {"amount_paise": net, "financial_year": fy, "rate": f"{rate_bp / 100:g}%"}})
    if posted:
        await add_event(session, producer=PRODUCER, event_type="InterestCredited.v1", aggregate_type="interest_run",
                        aggregate_id=f"{fy}-{rule_version}", correlation_id=correlation_id, payload={
                            "financial_year": fy, "rate_bp": rate_bp, "rule_version": rule_version,
                            "postings": [{k: p[k] for k in ("account_link_id", "journal_id", "employee_paise", "employer_paise")} for p in posted]})
    return posted
