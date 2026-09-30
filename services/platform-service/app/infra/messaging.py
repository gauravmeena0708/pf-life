"""Events platform-service consumes: an approved interest rate recorded by HO F&A becomes a draft rule set (P2.8d)."""
import secrets
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import published, published_order, stamp, today
from app.infra.tables import rule_sets

BINDINGS = ["contribution-service.InterestRateDeclared.v1"]


async def on_interest_rate(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if (await session.execute(select(rule_sets.c.version_id).where(rule_sets.c.change_note.like(f"%{p['declaration_id']}%")))).first():
        return                                                                        # already drafted
    live = await published(session)
    in_force = [r for r in live if r["effective_from"] <= today()] or live
    base = max(in_force, key=published_order)
    document = {k: v for k, v in base["document"].items() if k not in ("rule_version", "effective_from", "ILLUSTRATIVE_ONLY")}
    interest = dict(document.get("interest") or {})
    interest["rates_bp"] = {**(interest.get("rates_bp") or {}), p["financial_year"]: p["rate_bp"]}
    document["interest"] = interest
    name = f"interest-{p['financial_year']}-{secrets.token_hex(2)}"
    await session.execute(insert(rule_sets).values(
        version_id=f"POL-{secrets.token_hex(4).upper()}", rule_version=name, effective_from=today(), status="DRAFT",
        document=stamp(document, name, today()), base_version_id=base["version_id"],
        change_note=(f"Interest rate for {p['financial_year']}: {p['rate_bp'] / 100:.2f}% as recorded by HO F&A "
                     f"({p['declaration_id']}; CBT {p['cbt_recommended_on']}, Ministry concurrence {p['ministry_concurrence_ref']} "
                     f"of {p['ministry_concurrence_on']}). Prepared automatically; check and submit."),
        drafted_by=f"SYSTEM:{p['declaration_id']}", version=1))


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"] == "InterestRateDeclared.v1":
        await on_interest_rate(session, event)
