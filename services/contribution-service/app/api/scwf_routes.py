"""Office annual identification, transfer and reclaim of unclaimed EPF balances."""
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.domain.scwf import reclaim_open, scwf_eligible
from app.infra.claims_ledger import _post, member_shares
from app.infra.db import sessions
from app.infra.inoperative import accounts
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
OFFICE = require_stakeholder("fo.da_accounts", "fo.ao", "fo.apfc")


class TransferRun(BaseModel):
    identification_year: int = Field(ge=2000, le=9998)
    transferred_on: date


class Reclaim(BaseModel):
    claimed_on: date


async def _candidates(session, year: int) -> list[dict]:
    as_of = date(year, 9, 30)
    rules = await rules_on(session, as_of)
    months = int(section(rules, "inoperative_accounts").get("months_without_credit", 36))
    rows = await accounts(session, months, as_of)
    existing = {row[0] for row in (await session.execute(text("SELECT account_link_id FROM scwf_transfers"))).all()}
    return [r for r in rows if r["last_credit_day"] and not r["reactivated"]
            and r["account_link_id"] not in existing and scwf_eligible(r["last_credit_day"], months, year)]


@router.get("/api/v1/office/scwf/identifications/{year}")
async def identify(year: int, actor: Actor = Depends(OFFICE)) -> dict:
    if year < 2000 or year > 9998:
        raise Problem(422, "/problems/validation", "Identification year is out of range")
    async with sessions()() as session:
        rows = await _candidates(session, year)
    return envelope({"year": year, "identified_on": date(year, 9, 30).isoformat(), "dry_run": True,
                     "accounts": [{"account_link_id": r["account_link_id"], "uan": r["uan"],
                                   "balance_paise": r["balance"]} for r in rows]})


@router.post("/api/v1/office/scwf/transfers")
async def transfer(body: TransferRun, actor: Actor = Depends(require_stakeholder("fo.ao", "fo.apfc"))) -> dict:
    if not date(body.identification_year, 10, 1) <= body.transferred_on <= date(body.identification_year + 1, 3, 1):
        raise Problem(422, "/problems/validation", "Transfer must follow identification and occur by 1 March")
    posted = []
    async with sessions()() as session, session.begin():
        for row in await _candidates(session, body.identification_year):
            account = row["account_link_id"]
            shares = await member_shares(session, account)
            amount = sum(max(value, 0) for value in shares.values())
            if amount != row["balance"] or amount <= 0:
                continue
            lines = [{"account_code": "AC01_EPF", "side": "debit", "amount_paise": value,
                      "account_link_id": account, "share": share}
                     for share, value in shares.items() if value > 0]
            lines.append({"account_code": "SCWF_PAYABLE", "side": "credit", "amount_paise": amount})
            # SCWF: retain a balanced member-level debit and a separate fund liability.
            journal = await _post(session, f"SCWF-{account}", "SCWF_TRANSFER", None, lines)
            if journal is None:
                continue
            await session.execute(text("UPDATE journals SET occurred_at=:d WHERE id=:j"),
                                  {"d": datetime.combine(body.transferred_on, time.min, tzinfo=UTC), "j": journal})
            await session.execute(text("INSERT INTO scwf_transfers "
                                       "(account_link_id,uan,identification_year,amount_paise,transferred_on,state,journal_id) "
                                       "VALUES (:a,:u,:y,:n,:d,'TRANSFERRED',:j)"),
                                  {"a": account, "u": row["uan"], "y": body.identification_year,
                                   "n": amount, "d": body.transferred_on, "j": journal})
            posted.append({"account_link_id": account, "amount_paise": amount})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="scwf.transfer_run", target_type="identification_year",
                    target_id=str(body.identification_year), detail=f"members={len(posted)}")
    return envelope({"year": body.identification_year, "transferred_on": body.transferred_on.isoformat(),
                     "transfers": posted})


@router.post("/api/v1/office/scwf/transfers/{accountLinkId}/reclaims")
async def reclaim(accountLinkId: str, body: Reclaim,
                  actor: Actor = Depends(require_stakeholder("fo.ao", "fo.apfc"))) -> dict:
    async with sessions()() as session, session.begin():
        lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
        row = (await session.execute(text("SELECT * FROM scwf_transfers WHERE account_link_id=:a" + lock),
                                     {"a": accountLinkId})).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "SCWF transfer not found")
        if row["state"] != "TRANSFERRED":
            return envelope({"account_link_id": accountLinkId, "state": row["state"]})
        transferred = date.fromisoformat(str(row["transferred_on"])[:10])
        if body.claimed_on < transferred:
            raise Problem(422, "/problems/validation", "Reclaim date precedes transfer")
        if not reclaim_open(transferred, body.claimed_on):
            # SCWF: after 25 years record escheat to the Central Government; no money moves here.
            await session.execute(text("UPDATE scwf_transfers SET state='ESCHEATED',escheated_on=:d "
                                       "WHERE account_link_id=:a"), {"d": body.claimed_on, "a": accountLinkId})
            state = "ESCHEATED"
        else:
            amount = int(row["amount_paise"])
            shares = (await session.execute(text("SELECT share,amount_paise FROM journal_lines "
                                                 "WHERE journal_id=:j AND account_code='AC01_EPF' AND side='debit'"),
                                            {"j": row["journal_id"]})).all()
            lines = [{"account_code": "SCWF_PAYABLE", "side": "debit", "amount_paise": amount}]
            lines += [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": int(value),
                       "account_link_id": accountLinkId, "share": share} for share, value in shares]
            journal = await _post(session, f"SCWF-RECLAIM-{accountLinkId}", "SCWF_RECLAIM", None, lines)
            await session.execute(text("UPDATE journals SET occurred_at=:d WHERE id=:j"),
                                  {"d": datetime.combine(body.claimed_on, time.min, tzinfo=UTC), "j": journal})
            await session.execute(text("UPDATE scwf_transfers SET state='RECLAIMED',reclaimed_on=:d "
                                       "WHERE account_link_id=:a"), {"d": body.claimed_on, "a": accountLinkId})
            state = "RECLAIMED"
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action=f"scwf.{state.lower()}", target_type="account", target_id=accountLinkId)
    return envelope({"account_link_id": accountLinkId, "state": state})
