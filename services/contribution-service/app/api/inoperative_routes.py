"""Illustrative inoperative-account office workflow and two-step public search."""
import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.db import sessions
from app.infra.inoperative import accounts, cutoff_for, months_rule
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
NEXT_STEP = "Visit your EPFO office or a Nidhi Aapke Nikat camp with your ID; the account is reactivated after verification."


class Reactivation(BaseModel):
    decision: Literal["REACTIVATE"]
    note: str = Field(min_length=1, max_length=2000)


class Search(BaseModel):
    name: str | None = None
    date_of_birth: date | None = None
    establishment_query: str | None = None
    search_ref: str | None = None
    otp: str | None = None


def _masked(account_id: str) -> str:
    return "*" * max(4, len(account_id) - 4) + account_id[-4:]


def _otp(ref: str) -> str:
    return f"{int(hashlib.sha256(ref.encode()).hexdigest(), 16) % 1000000:06d}"


@router.get("/api/v1/office/accounts/inoperative")
async def inoperative(months: int | None = Query(default=None, ge=12, le=120),
                      include_reactivated: bool = False,
                      actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.oic", "fo.ao", "fo.apfc"))):
    async with sessions()() as session:
        months = months if months is not None else await months_rule(session)
        rows = await accounts(session, months)
    out = [{"account_link_id": r["account_link_id"], "uan_masked": _masked(r["uan"]), "name": r["name"],
            "establishment_id": r["establishment_id"], "balance_paise": r["balance"],
            "last_credit": r["last_credit_day"].isoformat() if r["last_credit_day"] else None,
            "exited_on": r["date_of_exit"].isoformat() if hasattr(r["date_of_exit"], "isoformat") else r["date_of_exit"],
            "status": "REACTIVATED" if r["reactivated"] else "INOPERATIVE",
            "verified": r["verified"], "reactivated": r["reactivated"]}
           for r in rows if include_reactivated or not r["reactivated"]]
    return envelope({"no_credit_since": cutoff_for(months).isoformat(), "months": months, "accounts": out})


@router.post("/api/v1/office/accounts/{accountLinkId}/reactivations")
async def reactivate(accountLinkId: str, body: Reactivation,
                     actor: Actor = Depends(require_stakeholder("fo.ao", "fo.apfc"))):
    async with sessions()() as session, session.begin():
        if (await session.execute(text("SELECT 1 FROM account_reactivations WHERE account_link_id=:a"),
                                  {"a": accountLinkId})).first():
            raise Problem(409, "/problems/already-reactivated", "Account is already reactivated")
        rules = await rules_on(session, date.today())
        policy = section(rules, "inoperative_accounts")
        rows = await accounts(session, int(policy.get("months_without_credit", 36)))
        row = next((r for r in rows if r["account_link_id"] == accountLinkId), None)
        if row is None:
            raise Problem(409, "/problems/not-inoperative", "Account is not inoperative")
        if not row["verified"]:
            raise Problem(409, "/problems/not-verified", "Account is not verified",
                          next_step="verification through co-workers")
        co_workers = (await session.execute(text(
            "SELECT co_workers FROM inoperative_verifications WHERE account_link_id=:a AND uan=:u"),
            {"a": accountLinkId, "u": row["uan"]})).scalar_one_or_none()
        if co_workers is None or int(co_workers) < int(policy.get("co_workers_required", 2)):
            raise Problem(409, "/problems/not-verified", "Account is not verified",
                          next_step="verification through co-workers")
        if row["balance"] > int(policy.get("ao_limit_paise", 50000000)) and actor.stakeholder == "fo.ao":
            raise Problem(403, "/problems/above-your-band", "Above your approval band", "Forward to the APFC.")
        require_step_up(actor, "reactivate-account", accountLinkId, None, row["balance"])
        inserted = await session.execute(text(
            "INSERT INTO account_reactivations (account_link_id,uan,balance_paise,approved_by,approved_by_role,note) "
            "VALUES (:a,:u,:b,:by,:role,:note) ON CONFLICT (account_link_id) DO NOTHING"),
            {"a": accountLinkId, "u": row["uan"], "b": row["balance"], "by": actor.subject,
             "role": actor.stakeholder, "note": body.note})
        if inserted.rowcount == 0:
            raise Problem(409, "/problems/already-reactivated", "Account is already reactivated")
        await add_event(session, producer="contribution-service", event_type="AccountReactivated.v1",
                        aggregate_type="account", aggregate_id=accountLinkId,
                        payload={"account_link_id": accountLinkId, "uan": row["uan"],
                                 "balance_paise": row["balance"], "approved_by_role": actor.stakeholder},
                        correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="account.reactivated", target_type="account", target_id=accountLinkId,
                    detail=body.note)
    return envelope({"account_link_id": accountLinkId, "status": "REACTIVATED", "balance_paise": row["balance"]})


@router.post("/api/v1/public/inoperative-accounts/searches")
async def public_search(body: Search, actor: Actor = Depends(require_actor)):
    """The gateway authenticates anonymous callers as stakeholder public.

    The local member projection has name and date_of_birth, but no mobile. Match name and DOB exactly
    (name case-insensitively), and require a case-insensitive establishment-name substring.
    """
    if actor.stakeholder != "public":
        raise Problem(403, "/problems/forbidden", "Not allowed")
    if body.search_ref is not None or body.otp is not None:
        if not body.search_ref or not body.otp or any((body.name, body.date_of_birth, body.establishment_query)):
            raise Problem(422, "/problems/validation", "Give a search_ref and otp")
        async with sessions()() as session, session.begin():
            ref = (await session.execute(text("SELECT account_link_id, expires_at FROM inoperative_search_refs WHERE search_ref=:r"),
                                         {"r": body.search_ref})).mappings().first()
            now = datetime.now(UTC)
            expiry = ref["expires_at"] if ref else None
            if isinstance(expiry, str):                                    # SQLite returns the timestamp as text
                expiry = datetime.fromisoformat(expiry)
            if expiry and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if not ref or expiry <= now:
                raise Problem(404, "/problems/not-found", "Search reference not found or expired")
            if not secrets.compare_digest(body.otp, _otp(body.search_ref)):
                raise Problem(422, "/problems/invalid-otp", "Incorrect OTP")
            rows = await accounts(session, await months_rule(session))
            row = next((r for r in rows if r["account_link_id"] == ref["account_link_id"] and not r["reactivated"]), None)
            if row is None:
                raise Problem(404, "/problems/not-found", "Account is no longer inoperative")
            masked = _masked(row["account_link_id"])
            await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                        action="inoperative_search.otp_verified", target_type="search_ref", target_id=body.search_ref,
                        detail=f"member_id_masked={masked}")
            return envelope({"member_id_masked": masked, "balance_paise": row["balance"], "next_step": NEXT_STEP})
    if not body.name or not body.date_of_birth or not body.establishment_query or not body.establishment_query.strip():
        raise Problem(422, "/problems/validation", "Give name, date_of_birth and establishment_query")
    async with sessions()() as session, session.begin():
        rows = await accounts(session, await months_rule(session))
        matches = [r for r in rows if not r["reactivated"] and r["name"].casefold() == body.name.strip().casefold()
                   and str(r["date_of_birth"])[:10] == body.date_of_birth.isoformat()
                   and body.establishment_query.strip().casefold() in r["establishment_name"].casefold()][:3]
        output = []
        for row in matches:
            ref = secrets.token_urlsafe(24)
            await session.execute(text("INSERT INTO inoperative_search_refs (search_ref,account_link_id,expires_at) VALUES (:r,:a,:e)"),
                                  {"r": ref, "a": row["account_link_id"], "e": datetime.now(UTC) + timedelta(minutes=15)})
            output.append({"search_ref": ref, "member_id_masked": _masked(row["account_link_id"]),
                           "establishment_name": row["establishment_name"],
                           "last_credit_year": row["last_credit_day"].year if row["last_credit_day"] else None})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="inoperative_search.created", target_type="search_ref", target_id="-",
                    detail=f"matches={len(output)}")
    return envelope({"matches": output, "otp_sent_to": "the mobile on record",
                     "demo": {"otp": _otp(output[0]["search_ref"]) if output else None,
                              "otp_by_search_ref": {item["search_ref"]: _otp(item["search_ref"]) for item in output},
                              "note": "demo only"}})
