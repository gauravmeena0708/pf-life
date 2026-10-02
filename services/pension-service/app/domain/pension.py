"""Pension amounts over time and revisions under a changed formula (policy-driven, illustrative).

* The monthly amount for a month is the original amount, or the latest approved revision effective by then.
* A published rule set that changes the formula, with `applies_to_pensions_in_payment`, proposes a revision
  for each pension it would increase, effective from the rule set's date (or the pension's start, if later).
  Pensions in payment are never reduced.
* When an APFC (Pension) approves, the arrears are the difference for every month already paid from the
  effective month, paid as one credit; later months are paid at the new amount."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import pension_payments, pension_revisions, pensioners
from epfo_persistence.policy import pension_on, section


def today() -> date:
    return datetime.now(UTC).date()


def month_of(day: date) -> str:
    return day.strftime("%Y-%m")


def last_day(month: str) -> date:
    y, m = int(month[:4]), int(month[5:])
    return date.fromordinal(date(y + (m == 12), m % 12 + 1, 1).toordinal() - 1)


def months(first: str, before: str) -> list[str]:
    """Months from `first` up to, not including, `before` (YYYY-MM)."""
    out, y, m = [], int(first[:4]), int(first[5:])
    while f"{y:04d}-{m:02d}" < before:
        out.append(f"{y:04d}-{m:02d}")
        y, m = y + (m == 12), m % 12 + 1
    return out


def age_on(born: date, day: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


async def approved(session: AsyncSession, ppo_id: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(pension_revisions).where(pension_revisions.c.ppo_id == ppo_id,
                                                                  pension_revisions.c.state == "APPROVED")
                                  .order_by(pension_revisions.c.effective_from, pension_revisions.c.decided_at))).mappings().all()
    return [dict(r) for r in rows]


def amount_for(pensioner: dict[str, Any], revisions: list[dict[str, Any]], month: str) -> dict[str, Any]:
    """The monthly amount (and the rules behind it) in force for a month."""
    current = {"monthly_paise": pensioner["original_monthly_paise"], "rule_version": pensioner["original_rule_version"],
               "working": pensioner["original_working"]}
    for r in revisions:
        if month_of(r["effective_from"]) <= month:
            current = {"monthly_paise": r["new_monthly_paise"], "rule_version": r["to_rule_version"], "working": r["working"]}
    return current


async def catch_up_payments(session: AsyncSession, pensioner: dict[str, Any], on: date | None = None,
                            released_on: date | None = None) -> None:
    """Mock CPPS: credit every month up to the last completed one at the amount in force for it (idempotent).
    Nothing is credited while the pension is suspended or stopped; months held back are credited when it is
    resumed (`released_on`: the date they are paid)."""
    if pensioner.get("status", "IN_PAYMENT") != "IN_PAYMENT":
        return
    revisions = await approved(session, pensioner["ppo_id"])
    paid = set((await session.execute(select(pension_payments.c.month).where(
        pension_payments.c.ppo_id == pensioner["ppo_id"], pension_payments.c.kind == "MONTHLY"))).scalars())
    last = month_of(on or today())
    if pensioner.get("pension_kind") == "CHILD":           # P2.19: to 25 (Pension Manual 2.10.5); a disabled child is paid for life
        born = pensioner["date_of_birth"]
        y, m = born.year + 25 + (born.month == 12), born.month % 12 + 1
        ends = f"{y:04d}-{m:02d}"                          # paid up to the month in which 25 is reached (the range excludes its end)
        if ends < last:
            last = ends
            await session.execute(update(pensioners).where(pensioners.c.ppo_id == pensioner["ppo_id"]).values(
                status="CEASED", status_reason=f"Children's pension ends at 25 ({born.year + 25}-{born.month:02d}; Pension Manual 2.10.5)"))
    for month in months(month_of(pensioner["pension_start"]), last):
        if month not in paid:
            await session.execute(insert(pension_payments).values(
                ppo_id=pensioner["ppo_id"], month=month, kind="MONTHLY", revision_id="",
                amount_paise=amount_for(pensioner, revisions, month)["monthly_paise"],
                paid_on=max(last_day(month), released_on) if released_on else last_day(month)))


async def arrears(session: AsyncSession, revision: dict[str, Any]) -> int:
    """The difference for every month already paid from the revision's effective month, against what each month
    has received so far: the monthly credit plus arrears of revisions approved earlier (never paid twice)."""
    pensioner = dict((await session.execute(select(pensioners).where(pensioners.c.ppo_id == revision["ppo_id"]))).mappings().one())
    earlier = await approved(session, revision["ppo_id"])
    paid = (await session.execute(select(pension_payments.c.month).where(
        pension_payments.c.ppo_id == revision["ppo_id"], pension_payments.c.kind == "MONTHLY",
        pension_payments.c.month >= month_of(revision["effective_from"])))).scalars().all()
    return sum(max(0, revision["new_monthly_paise"] - amount_for(pensioner, earlier, month)["monthly_paise"]) for month in paid)


async def propose_revisions(session: AsyncSession, rules: dict[str, Any], effective_from: date) -> list[str]:
    """After a rule set is published: propose a revision for every pension the new formula would increase."""
    p_rules = section(rules, "pension")
    if not p_rules["applies_to_pensions_in_payment"]:
        return []
    if p_rules.get("revise_in_payment_from"):                     # retrospective effect for pensions in payment
        effective_from = min(effective_from, date.fromisoformat(str(p_rules["revise_in_payment_from"])))
    proposed = []
    for row in (await session.execute(select(pensioners).where(pensioners.c.status == "IN_PAYMENT"))).mappings().all():
        p = dict(row)
        result = pension_on(p["pensionable_salary_paise"], p["service_months"], p["age_at_start"], rules,
                            disablement=p.get("pension_kind") == "DISABLED")
        effective = max(effective_from, p["pension_start"])
        current = amount_for(p, await approved(session, p["ppo_id"]), month_of(effective))
        if not result["eligible"] or result["monthly_paise"] <= current["monthly_paise"]:
            continue                                              # unchanged, or lower: pensions in payment are never reduced
        revision_id = f"REV-{p['ppo_id']}-{rules['rule_version']}"
        covered = (await session.execute(select(pension_revisions.c.revision_id).where(
            pension_revisions.c.ppo_id == p["ppo_id"], pension_revisions.c.state.in_(("PROPOSED", "APPROVED")),
            pension_revisions.c.new_monthly_paise == result["monthly_paise"], pension_revisions.c.effective_from <= effective))).first()
        if covered:                                   # the same change carried into another version (e.g. a scheduled one)
            continue
        await session.execute(update(pension_revisions).where(pension_revisions.c.ppo_id == p["ppo_id"],
                                                              pension_revisions.c.state == "PROPOSED").values(state="SUPERSEDED"))
        await session.execute(insert(pension_revisions).values(
            revision_id=revision_id, ppo_id=p["ppo_id"], from_rule_version=current["rule_version"],
            to_rule_version=rules["rule_version"], effective_from=effective, old_monthly_paise=current["monthly_paise"],
            new_monthly_paise=result["monthly_paise"], working=result["working"], state="PROPOSED"))
        proposed.append(revision_id)
    return proposed
