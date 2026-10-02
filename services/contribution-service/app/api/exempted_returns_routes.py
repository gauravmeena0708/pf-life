"""Illustrative exempt PF trust returns and office priority matrix."""
import json
import re
import secrets
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.db import sessions
from app.infra.trust_passbook import trust_section
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
TRUST = require_stakeholder("exempted.trust")
OFFICER = require_stakeholder("fo.exemption")
RANKING = require_stakeholder("fo.exemption", "ho.exemption")
CONSEQUENCES = {"A": "Show-cause notice for cancellation",
                "B": "Direct the establishment to rectify; cancellation if not rectified on 2 consecutive occasions",
                "C": "Advise; cancellation after 3 consecutive occasions"}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Transfer(BaseModel):
    date: date
    amount_paise: int = Field(ge=0)


class ReturnInput(BaseModel):
    wage_month: str
    employees_opening: int = Field(ge=0)
    joined: int = Field(ge=0)
    left: int = Field(ge=0)
    excluded: int = Field(ge=0)
    contract_trust: int = Field(ge=0)
    contract_elsewhere: int = Field(ge=0)
    direct_exempted: int = Field(ge=0)
    direct_unexempted: int = Field(ge=0)
    international_workers: int = Field(ge=0)
    disabled_workers: int = Field(ge=0)
    pf_wages_paise: int = Field(ge=0)
    employee_share_paise: int = Field(ge=0)
    employer_share_paise: int = Field(ge=0)
    due_paise: int = Field(ge=0)
    transfers: list[Transfer]
    interest_paid_paise: int = Field(ge=0)
    claims_opening: int = Field(ge=0)
    claims_received: int = Field(ge=0)
    claims_within_days: int = Field(ge=0)
    claims_beyond_days: int = Field(ge=0)
    pending_reasons: str | None = None
    grievances_opening: int = Field(ge=0)
    grievances_received: int = Field(ge=0)
    grievances_disposed: int = Field(ge=0)
    interest_rate_declared_bp: int = Field(ge=0)
    investible_corpus_paise: int = Field(ge=0)
    invested_paise: int = Field(ge=0)
    accounts_audited: bool
    member_balances_total_paise: int | None = Field(default=None, ge=0)
    revised: bool = False


class FlagAction(BaseModel):
    action: Literal["DIRECTION_TO_RECTIFY", "ADVICE", "SHOW_CAUSE_NOTICE", "REFERRED_FOR_CANCELLATION", "CLOSED_RECTIFIED"]
    note: str = Field(min_length=1, max_length=2000)


def month_start(month: str) -> date:
    if not MONTH.fullmatch(month):
        raise Problem(422, "/problems/validation", "Write wage_month as YYYY-MM")
    try:
        return date.fromisoformat(month + "-01")
    except ValueError:
        raise Problem(422, "/problems/validation", "Write wage_month as YYYY-MM") from None


def previous_month(month: str) -> str:
    return (month_start(month) - timedelta(days=1)).strftime("%Y-%m")


def validate(body: ReturnInput, effective: date) -> None:
    start = month_start(body.wage_month)
    if start > date.today().replace(day=1) or start < effective:
        raise Problem(422, "/problems/validation", "Wage month is outside the exemption period or in the future")
    headcount = body.employees_opening + body.joined - body.left - body.excluded
    categories = body.contract_trust + body.contract_elsewhere + body.direct_exempted + body.direct_unexempted
    if headcount != categories:
        raise Problem(422, "/problems/validation", "Part C employee totals do not balance",
                      "employees_opening + joined - left - excluded must equal the four employee categories")
    if body.due_paise != body.employee_share_paise + body.employer_share_paise:
        raise Problem(422, "/problems/validation", "Due must equal employee and employer shares")
    if body.claims_within_days + body.claims_beyond_days > body.claims_opening + body.claims_received:
        raise Problem(422, "/problems/validation", "Settled claims exceed claims received and opening")
    if body.claims_opening + body.claims_received > body.claims_within_days + body.claims_beyond_days and not (body.pending_reasons or "").strip():
        raise Problem(422, "/problems/validation", "Pending claims require pending_reasons")
    if body.grievances_disposed > body.grievances_opening + body.grievances_received:
        raise Problem(422, "/problems/validation", "Disposed grievances exceed available grievances")
    if any(t.date < start for t in body.transfers):
        raise Problem(422, "/problems/validation", "Transfer date cannot precede the wage month")


def evaluate(body: ReturnInput, settings: dict, epfo_rate: int) -> tuple[dict, int, int, int]:
    year, month = map(int, body.wage_month.split("-"))
    due_date = date(year + (month == 12), month % 12 + 1, int(settings["return_due_day"]))
    transferred = sum(t.amount_paise for t in body.transfers)
    on_time = sum(t.amount_paise for t in body.transfers if t.date <= due_date)
    threshold = int(settings["investment_threshold_pct"]) / 100
    corpus_share = body.invested_paise / body.investible_corpus_paise if body.investible_corpus_paise else 0
    claims = body.claims_opening + body.claims_received
    parts = {
        "transfer_before_due_date": round(100 * min(1, on_time / body.due_paise), 1) if body.due_paise else 100.0,
        "investment": round(100 * min(1, corpus_share / threshold), 1),
        "remittance": round(100 * min(1, transferred / body.due_paise), 1) if body.due_paise else 100.0,
        "interest_declared": round(100 * min(1, body.interest_rate_declared_bp / epfo_rate), 1) if epfo_rate else 100.0,
        "claim_settlement": round(100 * body.claims_within_days / claims, 1) if claims else 100.0,
        "audit_of_accounts": 100.0 if body.accounts_audited else 0.0,
    }
    last = max((t.date for t in body.transfers), default=None)
    return parts, body.due_paise - transferred, max(0, (last - due_date).days) if last else 0, claims - body.claims_within_days - body.claims_beyond_days


def rate_for(rules: dict, month: str) -> int:
    year, m = map(int, month.split("-"))
    fy = f"{year if m >= 4 else year - 1}-{(year + 1 if m >= 4 else year) % 100:02d}"
    rates = section(rules, "interest")["rates_bp"]
    return int(rates.get(fy, rates[max(rates)]))


def unpack(value):
    return value if isinstance(value, (dict, list)) else json.loads(value)


async def trust_establishment(session, actor: Actor):
    rows = (await session.execute(text("SELECT * FROM exempted_establishments"))).mappings().all()
    for row in rows:
        if any(user.get("subject") == actor.subject for user in unpack(row["trust_users"])):
            return row
    raise Problem(403, "/problems/forbidden", "No exempted trust is assigned to this user")


async def office_establishment(session, est_id: str, actor: Actor):
    row = (await session.execute(text("SELECT e.*, x.effective_from FROM establishments e JOIN exempted_establishments x ON x.establishment_id=e.id WHERE e.id=:id"), {"id": est_id})).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Exempted establishment not found")
    if actor.stakeholder == "fo.exemption" and (await officer_office(session, actor) or "") != row["office_id"]:
        raise Problem(403, "/problems/forbidden", "Establishment is outside your office")
    return row


async def flags_for(session, est_id: str, month: str):
    rows = (await session.execute(text("SELECT * FROM trust_flags WHERE establishment_id=:e AND wage_month=:m ORDER BY code"), {"e": est_id, "m": month})).mappings().all()
    return [dict(row) for row in rows]


def present(row, flags):
    result = {**unpack(row["content"]), "return_id": row["return_id"], "establishment_id": row["establishment_id"],
              "version": row["version"], "state": row["state"], "score": row["score"], "parts": unpack(row["parts"]),
              "balance_due_paise": row["balance_due_paise"], "late_transfer_days": row["late_transfer_days"],
              "claims_pending": row["claims_pending"], "flags": flags}
    return result


async def current_returns(session, est_id: str):
    return (await session.execute(text("SELECT * FROM trust_returns WHERE establishment_id=:e AND state IN ('FILED','SUPERSEDED') ORDER BY wage_month DESC, version DESC"), {"e": est_id})).mappings().all()


async def officer_office(session, actor) -> str | None:
    """The officer's office from the postings copy (seed + StaffPostingChanged.v1); a claim in the token for tests."""
    row = (await session.execute(text("SELECT office_id FROM office_staff WHERE subject=:s"), {"s": actor.subject})).first()
    return row[0] if row else actor.claims.get("office_id")


async def missing_streak(session, est_id: str, month: str, effective: date, count: int) -> bool:
    """`count` months running without a return, counted from the trust's first online return (the Returns Manual lets the
    establishment start its online returns from a chosen month), never before the exemption."""
    first = (await session.execute(text("SELECT MIN(wage_month) FROM trust_returns WHERE establishment_id=:e AND state IN ('FILED','SUPERSEDED')"),
                                   {"e": est_id})).scalar_one_or_none()
    if first is None:
        return False                                    # no online return yet: nothing to count from
    start = max(effective.replace(day=1), month_start(first))
    cursor = month
    for _ in range(count):
        if month_start(cursor) < start:
            return False
        if (await session.execute(text("SELECT 1 FROM trust_returns WHERE establishment_id=:e AND wage_month=:m AND state='FILED'"), {"e": est_id, "m": cursor})).first():
            return False
        cursor = previous_month(cursor)
    return True


async def file_return(session, est_id: str, effective: date, exemption: dict, body: ReturnInput,
                      actor_subject: str, correlation_id: str, *, seeded: bool = False):
    if isinstance(effective, str):
        effective = date.fromisoformat(effective)
    ended = exemption.get("ended_on")
    if isinstance(ended, str):
        ended = date.fromisoformat(ended)
    if ended and month_start(body.wage_month) >= ended:
        raise Problem(409, "/problems/exemption-ended", "The exemption ended on " + ended.isoformat() + "; returns stop (link removed)")
    validate(body, effective)
    prior = (await session.execute(text("SELECT * FROM trust_returns WHERE establishment_id=:e AND wage_month=:m AND state='FILED'"), {"e": est_id, "m": body.wage_month})).mappings().first()
    if prior and (not body.revised or seeded):
        if seeded:
            return present(prior, await flags_for(session, est_id, body.wage_month))
        raise Problem(409, "/problems/duplicate-return", "A return for this month already exists; set revised to true")
    if body.revised and not prior:
        raise Problem(409, "/problems/no-return-to-revise", "There is no return for this month to revise")
    rules = await rules_on(session, month_start(body.wage_month))
    config = section(rules, "exempted_establishments")
    epfo_rate = rate_for(rules, body.wage_month)
    parts, balance, late, pending = evaluate(body, config, epfo_rate)
    score = round(sum(parts.values()), 1)
    if prior:
        await session.execute(text("UPDATE trust_returns SET state='SUPERSEDED' WHERE return_id=:id"), {"id": prior["return_id"]})
        # a revision re-raises the month's flags, but one the office has acted on stays (a revision cannot erase a show-cause)
        await session.execute(text("DELETE FROM trust_flags WHERE establishment_id=:e AND wage_month=:m AND action IS NULL"), {"e": est_id, "m": body.wage_month})
    return_id = f"TR-{secrets.token_hex(8).upper()}"
    content = body.model_dump(mode="json", exclude={"revised"})
    await session.execute(text("""INSERT INTO trust_returns (return_id,establishment_id,wage_month,version,state,content,score,parts,balance_due_paise,late_transfer_days,claims_pending,filed_by)
        VALUES (:id,:e,:m,:v,'FILED',:content,:score,:parts,:balance,:late,:pending,:by)"""),
        {"id": return_id, "e": est_id, "m": body.wage_month, "v": int(prior["version"]) + 1 if prior else 1,
         "content": json.dumps(content), "score": score, "parts": json.dumps(parts), "balance": balance, "late": late,
         "pending": pending, "by": actor_subject})
    findings = []
    count = int(config["consecutive_months"])
    if await missing_streak(session, est_id, previous_month(body.wage_month), effective, count):
        findings.append(("A", "NO_RETURNS", f"No return for {count} consecutive months before {body.wage_month}"))
    months = [body.wage_month]
    for _ in range(count - 1):
        months.append(previous_month(months[-1]))
    if all(month_start(m) >= effective.replace(day=1) for m in months):
        rows = (await session.execute(text("SELECT wage_month,score FROM trust_returns WHERE establishment_id=:e AND state='FILED' AND wage_month IN (" + ",".join(f":m{i}" for i in range(count)) + ")"),
                                      {"e": est_id, **{f"m{i}": m for i, m in enumerate(months)}})).mappings().all()
        if len(rows) == count and all(float(r["score"]) < int(config["min_score"]) for r in rows):
            findings.append(("A", "LOW_SCORE", f"Evaluator score below {config['min_score']} for {count} consecutive months"))
    if balance > 0:
        findings.append(("A", "PF_DUES_DEFAULT", f"PF dues outstanding: {balance} paise"))
    if body.claims_beyond_days:
        findings.append(("A", "CLAIMS_LATE", f"{body.claims_beyond_days} claims settled beyond {config['evaluator_claim_days']} days"))
    if body.interest_rate_declared_bp < epfo_rate:
        findings.append(("A", "INTEREST_BELOW_EPFO", f"Declared {body.interest_rate_declared_bp} bp below EPFO {epfo_rate} bp; employer must make good the shortfall"))
    if body.member_balances_total_paise is not None:
        accounts = (await session.execute(text("SELECT account_link_id FROM establishment_members WHERE establishment_id=:e"), {"e": est_id})).scalars().all()
        reported = 0
        available = True
        for account in accounts:
            trust = await trust_section(session, account, exemption, commit=False)
            if trust.get("unavailable"):
                available = False
                break
            reported += int(trust["balance"]["employee_paise"]) + int(trust["balance"]["employer_paise"])
        if available and reported != body.member_balances_total_paise:
            findings.append(("B", "RECONCILIATION", f"Trust API reports {reported} paise; return reports {body.member_balances_total_paise} paise"))
    actioned = set((await session.execute(text("SELECT code FROM trust_flags WHERE establishment_id=:e AND wage_month=:m"),
                                          {"e": est_id, "m": body.wage_month})).scalars().all())
    for category, code, detail in findings:
        if code in actioned:
            continue                                    # already raised and acted on
        await session.execute(text("""INSERT INTO trust_flags (flag_id,establishment_id,wage_month,category,code,text)
            VALUES (:id,:e,:m,:c,:code,:txt)"""), {"id": f"TF-{secrets.token_hex(8).upper()}", "e": est_id,
                                                   "m": body.wage_month, "c": category, "code": code,
                                                   "txt": f"{detail}. {CONSEQUENCES[category]}"})
    if not seeded:                                      # a seeded history publishes nothing, like the other seeds
        await add_event(session, producer="contribution-service", event_type="TrustReturnFiled.v1", aggregate_type="trust_return",
                        aggregate_id=return_id, correlation_id=correlation_id,
                        payload={"return_id": return_id, "establishment_id": est_id, "wage_month": body.wage_month,
                                 "score": score, "flags": [code for _, code, _ in findings]})
    await audit(session, actor_subject=actor_subject, actor_stakeholder="exempted.trust" if not seeded else "seed",
                action="trust.return_filed", target_type="trust_return", target_id=return_id,
                detail=f"{body.wage_month} version {int(prior['version']) + 1 if prior else 1}")
    row = (await session.execute(text("SELECT * FROM trust_returns WHERE return_id=:id"), {"id": return_id})).mappings().one()
    return present(row, await flags_for(session, est_id, body.wage_month))


@router.post("/api/v1/exempted/me/returns", status_code=201)
async def post_return(body: ReturnInput, actor: Actor = Depends(TRUST)):
    async with sessions()() as session, session.begin():
        ex = await trust_establishment(session, actor)
        data = await file_return(session, ex["establishment_id"], ex["effective_from"], dict(ex), body, actor.subject, actor.correlation_id)
    return envelope(data)


@router.get("/api/v1/exempted/me/returns")
async def own_returns(actor: Actor = Depends(TRUST)):
    async with sessions()() as session:
        ex = await trust_establishment(session, actor)
        rows = await current_returns(session, ex["establishment_id"])
        items = [present(row, await flags_for(session, ex["establishment_id"], row["wage_month"]) if row["state"] == "FILED" else []) for row in rows]
    return envelope({"returns": items})


@router.get("/api/v1/office/exempted/{estId}/returns")
async def office_returns(estId: str, actor: Actor = Depends(OFFICER)):
    async with sessions()() as session:
        await office_establishment(session, estId, actor)
        rows = await current_returns(session, estId)
        items = [present(row, await flags_for(session, estId, row["wage_month"]) if row["state"] == "FILED" else []) for row in rows]
    return envelope({"returns": items})


@router.get("/api/v1/office/exempted/rankings")
async def rankings(month: str, actor: Actor = Depends(RANKING)):
    start = month_start(month)
    if start > date.today().replace(day=1):
        raise Problem(422, "/problems/validation", "Month cannot be in the future")
    async with sessions()() as session:
        office = await officer_office(session, actor) if actor.stakeholder == "fo.exemption" else None
        if actor.stakeholder == "fo.exemption" and not office:
            raise Problem(403, "/problems/forbidden", "Your office is not assigned")
        rows = (await session.execute(text("""SELECT e.id,e.legal_name,e.office_id,x.effective_from,x.ended_on,x.status,r.score
            FROM exempted_establishments x JOIN establishments e ON e.id=x.establishment_id
            LEFT JOIN trust_returns r ON r.establishment_id=e.id AND r.wage_month=:m AND r.state='FILED'
            WHERE (:all_offices=1 OR e.office_id=:office) ORDER BY e.id"""),
            {"m": month, "all_offices": int(actor.stakeholder == "ho.exemption"), "office": office or ""})).mappings().all()
        items = []
        for row in rows:
            effective = row["effective_from"] if isinstance(row["effective_from"], date) else date.fromisoformat(row["effective_from"])
            if start < effective.replace(day=1):
                continue
            ended = row["ended_on"]
            if isinstance(ended, str):
                ended = date.fromisoformat(ended)
            if row["status"] != "ACTIVE" and (ended is None or start >= ended):
                continue
            flags = [f["code"] for f in await flags_for(session, row["id"], month)]
            if row["score"] is None:
                flags.append("NO_RETURN")
                config = section(await rules_on(session, start), "exempted_establishments")
                if await missing_streak(session, row["id"], month, effective, int(config["consecutive_months"])):
                    flags.append("NO_RETURNS")
            items.append({"establishment_id": row["id"], "legal_name": row["legal_name"], "office_id": row["office_id"],
                          "wage_month": month, "score": float(row["score"]) if row["score"] is not None else 0.0, "flags": flags})
    items.sort(key=lambda item: (-item["score"], item["establishment_id"]))
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
    return envelope({"rankings": items})


@router.post("/api/v1/office/exempted/{estId}/flags/{flagId}/actions")
async def action_flag(estId: str, flagId: str, body: FlagAction, actor: Actor = Depends(OFFICER)):
    async with sessions()() as session, session.begin():
        await office_establishment(session, estId, actor)
        flag = (await session.execute(text("SELECT * FROM trust_flags WHERE flag_id=:f AND establishment_id=:e"), {"f": flagId, "e": estId})).mappings().first()
        if not flag:
            raise Problem(404, "/problems/not-found", "Trust flag not found")
        require_step_up(actor, "action-trust-flag", flagId)
        if flag["category"] == "A" and body.action == "ADVICE":
            raise Problem(422, "/problems/validation", "Category A requires a show-cause response, not advice")
        await session.execute(text("""UPDATE trust_flags SET action=:a,action_note=:n,actioned_by=:by,actioned_at=CURRENT_TIMESTAMP
            WHERE flag_id=:f"""), {"a": body.action, "n": body.note, "by": actor.subject, "f": flagId})
        await add_event(session, producer="contribution-service", event_type="TrustFlagActioned.v1", aggregate_type="trust_flag",
                        aggregate_id=flagId, correlation_id=actor.correlation_id,
                        payload={"flag_id": flagId, "establishment_id": estId, "category": flag["category"], "action": body.action})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="trust.flag_actioned",
                    target_type="trust_flag", target_id=flagId, detail=body.note)
        updated = (await session.execute(text("SELECT * FROM trust_flags WHERE flag_id=:f"), {"f": flagId})).mappings().one()
    return envelope(dict(updated))
