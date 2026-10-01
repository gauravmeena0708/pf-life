"""Illustrative fund custody feed and aggregate finance and governance reads."""
import hashlib
import hmac
import json
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.config import settings
from app.infra.tables import claim_facts, contribution_facts, fund_holdings, fund_positions, grievance_facts
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
FEED = require_stakeholder("ext.fund_manager")
FINANCE = require_stakeholder("ho.investment", "gov.fiac", "ho.fa_cao")
BOARD = require_stakeholder("gov.cbt", "gov.ec", "gov.fiac", "ho.cpfc")
ASSET_CLASSES = ("GOVT_SECURITIES", "DEBT", "SHORT_TERM_DEBT", "EQUITY", "ASSET_BACKED")


class Holding(BaseModel):
    isin: str = Field(pattern=r"^[A-Z0-9]{12}$")
    asset_class: Literal["GOVT_SECURITIES", "DEBT", "SHORT_TERM_DEBT", "EQUITY", "ASSET_BACKED"]
    book_value_paise: int = Field(ge=0)
    market_value_paise: int = Field(ge=0)


class PositionFeed(BaseModel):
    fund_manager: str = Field(min_length=1, max_length=120)
    fund: Literal["EPF", "EPS", "EDLI"]
    as_of: date
    holdings: list[Holding] = Field(min_length=1)
    signature: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("fund_manager")
    @classmethod
    def non_blank_manager(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("fund_manager must not be blank")
        return value.strip()


def feed_signature(body: PositionFeed | dict, secret: str | None = None) -> str:
    """HMAC-SHA256 over manager|fund|date|canonical JSON holdings, excluding signature."""
    values = body.model_dump(mode="json") if isinstance(body, PositionFeed) else body
    holdings = json.dumps(values["holdings"], sort_keys=True, separators=(",", ":"))
    message = f"{values['fund_manager']}|{values['fund']}|{values['as_of']}|{holdings}"
    return hmac.new((secret or settings.fund_manager_feed_secret).encode(), message.encode(), hashlib.sha256).hexdigest()


async def store_positions(session: AsyncSession, fund_manager: str, fund: str, as_of: date,
                          holdings: list[dict]) -> bool:
    """Replace one manager/fund/day snapshot. Return whether it existed."""
    position_id = (await session.execute(select(fund_positions.c.id).where(
        fund_positions.c.fund_manager == fund_manager, fund_positions.c.fund == fund,
        fund_positions.c.as_of == as_of))).scalar_one_or_none()
    existed = position_id is not None
    if existed:
        await session.execute(delete(fund_holdings).where(fund_holdings.c.position_id == position_id))
    else:
        position_id = (await session.execute(insert(fund_positions).values(
            fund_manager=fund_manager, fund=fund, as_of=as_of).returning(fund_positions.c.id))).scalar_one()
    await session.execute(insert(fund_holdings), [dict(position_id=position_id, **holding) for holding in holdings])
    return existed


@router.post("/api/v1/integrations/fund-managers/positions", status_code=201)
async def receive_positions(body: PositionFeed, response: Response, actor: Actor = Depends(FEED),
                            session: AsyncSession = Depends(db)) -> dict:
    if not hmac.compare_digest(feed_signature(body), body.signature.lower()):
        raise Problem(401, "/problems/bad-signature", "The feed signature does not match")
    holdings = [holding.model_dump() for holding in body.holdings]
    async with session.begin():
        existed = await store_positions(session, body.fund_manager, body.fund, body.as_of, holdings)
        await add_event(session, producer="reporting-service", event_type="FundPositionsReceived.v1",
                        aggregate_type="fund_positions", aggregate_id=f"{body.fund_manager}|{body.fund}|{body.as_of}",
                        payload={"fund_manager": body.fund_manager, "fund": body.fund,
                                 "as_of": body.as_of.isoformat(), "holdings": len(holdings),
                                 "market_value_paise": sum(h["market_value_paise"] for h in holdings)})
    response.status_code = 200 if existed else 201
    return envelope({"fund_manager": body.fund_manager, "fund": body.fund,
                     "as_of": body.as_of.isoformat(), "holdings": len(holdings), "replaced": existed})


async def investment_summary(session: AsyncSession, as_of: date) -> dict:
    latest = select(fund_positions.c.fund_manager, fund_positions.c.fund,
                    func.max(fund_positions.c.as_of).label("as_of")).where(
                        fund_positions.c.as_of <= as_of).group_by(
                            fund_positions.c.fund_manager, fund_positions.c.fund).subquery()
    rows = (await session.execute(select(fund_positions.c.fund_manager, fund_positions.c.fund,
                                         fund_positions.c.as_of, fund_holdings.c.asset_class,
                                         fund_holdings.c.book_value_paise, fund_holdings.c.market_value_paise)
                                  .join(latest, (fund_positions.c.fund_manager == latest.c.fund_manager) &
                                        (fund_positions.c.fund == latest.c.fund) &
                                        (fund_positions.c.as_of == latest.c.as_of))
                                  .join(fund_holdings, fund_holdings.c.position_id == fund_positions.c.id))).mappings().all()
    bands = section(await rules_on(session, as_of), "investment_pattern")
    grouped: dict[str, dict[str, dict[str, int]]] = {}
    managers: set[str] = set()
    for row in rows:
        managers.add(row["fund_manager"])
        item = grouped.setdefault(row["fund"], {}).setdefault(row["asset_class"],
                                                               {"book_value_paise": 0, "market_value_paise": 0})
        item["book_value_paise"] += int(row["book_value_paise"])
        item["market_value_paise"] += int(row["market_value_paise"])
    funds = []
    total_book = total_market = 0
    for fund, values in sorted(grouped.items()):
        book = sum(v["book_value_paise"] for v in values.values())
        market = sum(v["market_value_paise"] for v in values.values())
        total_book += book
        total_market += market
        classes = []
        for name in ASSET_CLASSES:
            amounts = values.get(name, {"book_value_paise": 0, "market_value_paise": 0})
            share = round(100 * amounts["market_value_paise"] / market, 1) if market else 0.0
            band = bands[name]
            flag = "BELOW" if share < band["min_pct"] else "ABOVE" if share > band["max_pct"] else "WITHIN"
            classes.append({"asset_class": name, **amounts,
                            "unrealised_gain_paise": amounts["market_value_paise"] - amounts["book_value_paise"],
                            "share_pct": share, "pattern_band": band, "flag": flag})
        funds.append({"fund": fund, "asset_classes": classes,
                      "totals": {"book_value_paise": book, "market_value_paise": market,
                                 "unrealised_gain_paise": market - book}})
    return {"as_of": as_of.isoformat(), "funds": funds,
            "totals": {"book_value_paise": total_book, "market_value_paise": total_market,
                       "unrealised_gain_paise": total_market - total_book},
            "fund_managers": sorted(managers),
            "note": "Illustrative synthetic custody snapshots; latest available per fund manager and fund on or before as_of. "
                    "Shares use market value within each fund. Missing asset classes count as zero."}


@router.get("/api/v1/ho/finance/investments")
async def investments(as_of: date | None = None, actor: Actor = Depends(FINANCE),
                      session: AsyncSession = Depends(db)) -> dict:
    return envelope(await investment_summary(session, as_of or datetime.now(UTC).date()))


def _days(later: datetime | str, earlier: datetime | str) -> float:
    def parse(value: datetime | str) -> datetime:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    return (parse(later) - parse(earlier)).total_seconds() / 86400


@router.get("/api/v1/governance/board-packs")
async def board_pack(meeting: Literal["CBT", "EC", "FIAC"], actor: Actor = Depends(BOARD),
                     session: AsyncSession = Depends(db)) -> dict:
    now = datetime.now(UTC)
    month = now.year * 12 + now.month
    contributions = (await session.execute(select(contribution_facts))).mappings().all()
    claims = (await session.execute(select(claim_facts))).mappings().all()
    grievances = (await session.execute(select(grievance_facts))).mappings().all()
    recent = [r for r in contributions if r["wage_month"] and
              0 <= month - (int(r["wage_month"][:4]) * 12 + int(r["wage_month"][5:7])) < 12 and
              r["submitted_at"] is not None]
    settled = [r for r in claims if r["settled_at"] is not None]
    resolved = [r for r in grievances if r["resolved_at"] is not None]
    investment = await investment_summary(session, now.date())
    summary = {"as_of": investment["as_of"], "funds": [
        {"fund": item["fund"], "totals": item["totals"]} for item in investment["funds"]],
        "totals": investment["totals"]}
    if meeting == "FIAC":
        summary["pattern_flags"] = [
            {"fund": item["fund"], "asset_class": cls["asset_class"], "share_pct": cls["share_pct"],
             "pattern_band": cls["pattern_band"], "flag": cls["flag"]}
            for item in investment["funds"] for cls in item["asset_classes"]]
    sections = {
        "contributions": {"wage_months": 12, "returns_filed": len(recent),
                          "returns_paid": sum(r["paid_at"] is not None for r in recent),
                          "amount_paise": sum(int(r["total_paise"] or 0) for r in recent if r["paid_at"] is not None)},
        "claims": {"received": len(claims), "settled": len(settled),
                   "rejected": sum(r["decision"] == "REJECTED" for r in claims),
                   "average_days_to_settle": round(sum(_days(r["settled_at"], r["submitted_at"])
                                                       for r in settled) / len(settled), 1) if settled else None,
                   "share_settled_within_20_days_pct": round(100 * sum(
                       _days(r["settled_at"], r["submitted_at"]) <= 20 for r in settled) / len(settled), 1)
                   if settled else None},
        "grievances": {"received": len(grievances), "resolved": len(resolved),
                       "pending": len(grievances) - len(resolved),
                       "average_days_to_resolve": round(sum(_days(r["resolved_at"], r["registered_at"])
                                                            for r in resolved) / len(resolved), 1) if resolved else None},
        "investments": summary,
    }
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                action="governance.board_pack_generated", target_type="meeting", target_id=meeting)
    await session.commit()
    return envelope({"generated_at": now.isoformat(), "meeting": meeting, "sections": sections,
                     "note": "Illustrative aggregate facts from this reporting service only."})
