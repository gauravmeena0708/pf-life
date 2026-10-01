"""pension-service: pensions in payment, revisions under a changed formula, the member's pension estimate and
the public calculator. Every amount comes from the formula in the published rule set (illustrative)."""
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import age_on, amount_for, approved, arrears, catch_up_payments, month_of, today
from app.infra.db import sessions
from app.infra.tables import eps_accounts, member_service, office_staff, pension_payments, pension_revisions, pensioners
from epfo_auth import Actor, require_actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import pension_on, rules_on, section

router = APIRouter()
PENSIONER = require_stakeholder("pensioner", "family_pensioner")
PENSION_OFFICE = require_stakeholder("fo.apfc_pension", "fo.da_pension")
APFC_PENSION = require_stakeholder("fo.apfc_pension")
MEMBER = require_stakeholder("member")


async def db():
    async with sessions()() as session:
        yield session


def _revision(r: Any, arrears_now: int | None = None) -> dict[str, Any]:
    return {"revision_id": r["revision_id"], "ppo_id": r["ppo_id"], "state": r["state"],
            "effective_from": r["effective_from"].isoformat(), "from_rule_version": r["from_rule_version"],
            "to_rule_version": r["to_rule_version"], "old_monthly_paise": r["old_monthly_paise"],
            "new_monthly_paise": r["new_monthly_paise"], "working": r["working"],
            "arrears_paise": r["arrears_paise"] if r["arrears_paise"] is not None else arrears_now,
            "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None, "note": r["note"]}


async def _own(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(pensioners).where(pensioners.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "No pension found for this login")
    return dict(row)


@router.get("/api/v1/pensioners/me")
async def me(actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _own(session, actor)
        await catch_up_payments(session, p)
        now = amount_for(p, await approved(session, p["ppo_id"]), month_of(today()))
        revisions = (await session.execute(select(pension_revisions).where(pension_revisions.c.ppo_id == p["ppo_id"],
                                                                           pension_revisions.c.state != "SUPERSEDED")
                                           .order_by(pension_revisions.c.proposed_at.desc()))).mappings().all()
    return envelope({"ppo_id": p["ppo_id"], "name": p["name"], "pension_type": "Superannuation" if p["age_at_start"] >= 58 else "Early",
                     "pension_start": p["pension_start"].isoformat(), "service_months": p["service_months"],
                     "pensionable_salary_paise": p["pensionable_salary_paise"], "age_at_start": p["age_at_start"],
                     "monthly_paise": now["monthly_paise"], "rule_version": now["rule_version"], "working": now["working"],
                     "bank_account_last4": p["bank_account_last4"],
                     "revisions": [_revision(r) for r in revisions]})


@router.get("/api/v1/pensioners/me/payments")
async def my_payments(actor: Actor = Depends(PENSIONER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        p = await _own(session, actor)
        await catch_up_payments(session, p)
        rows = (await session.execute(select(pension_payments).where(pension_payments.c.ppo_id == p["ppo_id"])
                                      .order_by(pension_payments.c.paid_on.desc(), pension_payments.c.id.desc()))).mappings().all()
    return envelope([{"month": r["month"], "kind": r["kind"], "amount_paise": r["amount_paise"], "paid_on": r["paid_on"].isoformat(),
                      "revision_id": r["revision_id"] or None} for r in rows])


async def _office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/forbidden", "Not posted to an office")
    return office


@router.get("/api/v1/office/pensions/revisions")
async def revision_queue(state: str = Query(default="PROPOSED", pattern="^(PROPOSED|APPROVED|REJECTED)$"),
                         actor: Actor = Depends(PENSION_OFFICE), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        rows = (await session.execute(select(pension_revisions, pensioners.c.name, pensioners.c.uan).join(
            pensioners, pensioners.c.ppo_id == pension_revisions.c.ppo_id).where(
            pension_revisions.c.state == state, pensioners.c.office_id == office).order_by(pension_revisions.c.proposed_at))).mappings().all()
        items = []
        for r in rows:
            await catch_up_payments(session, dict((await session.execute(select(pensioners).where(
                pensioners.c.ppo_id == r["ppo_id"]))).mappings().one()))
            items.append({**_revision(r, await arrears(session, dict(r))), "name": r["name"], "uan_masked": "********" + r["uan"][-4:]})
    return envelope({"items": items})


class RevisionDecision(BaseModel):
    revision_id: str = Field(min_length=1, max_length=80)
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/office/pensions/{ppo_id}/revisions")
async def decide_revision(ppo_id: str, body: RevisionDecision, actor: Actor = Depends(APFC_PENSION),
                          session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        p = (await session.execute(select(pensioners).where(pensioners.c.ppo_id == ppo_id))).mappings().first()
        if not p or p["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Pension not found in your office")
        r = (await session.execute(select(pension_revisions).where(pension_revisions.c.revision_id == body.revision_id,
                                                                   pension_revisions.c.ppo_id == ppo_id)
                                   .with_for_update())).mappings().first()
        if not r:
            raise Problem(404, "/problems/not-found", "Revision not found")
        if r["state"] != "PROPOSED":
            raise Problem(409, "/problems/invalid-state", "This revision is already decided", f"Status: {r['state']}.")
        await catch_up_payments(session, dict(p))
        due = await arrears(session, dict(r))
        require_step_up(actor, "approve-pension-revision", body.revision_id, None, due)
        now = datetime.now(UTC)
        await session.execute(update(pension_revisions).where(pension_revisions.c.revision_id == body.revision_id).values(
            state="APPROVED" if body.decision == "APPROVE" else "REJECTED", arrears_paise=due if body.decision == "APPROVE" else 0,
            decided_by=actor.subject, decided_at=now, note=body.note))
        if body.decision == "APPROVE" and due:
            await session.execute(insert(pension_payments).values(ppo_id=ppo_id, month=month_of(today()), kind="ARREARS",
                                                                  amount_paise=due, revision_id=body.revision_id, paid_on=today()))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"pension.revision.{body.decision.lower()}",
                    target_type="pension", target_id=ppo_id, detail=f"{body.revision_id}: {r['old_monthly_paise']} -> {r['new_monthly_paise']}, arrears {due}")
        r = (await session.execute(select(pension_revisions).where(pension_revisions.c.revision_id == body.revision_id))).mappings().one()
    return envelope(_revision(r))


def eps_service(spells: list[dict[str, Any]], day: date) -> tuple[int, list[dict[str, Any]]]:
    """Pensionable service across a member's IDs (P2.9b): the union of the spells — overlapping jobs count once — less the
    breaks without contributions (EPS para 9), in completed months; and each member ID's own months."""
    def months(a: date, b: date) -> int:
        return max(0, (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day))
    by_id, merged = [], []
    for sp in sorted(spells, key=lambda x: x["date_of_joining"]):
        start, end = sp["date_of_joining"], min(sp["date_of_exit"] or day, day)
        by_id.append({"account_link_id": sp["account_link_id"], "establishment_id": sp.get("establishment_id"), "from": start.isoformat(),
                      "to": sp["date_of_exit"].isoformat() if sp["date_of_exit"] else None, "months": months(start, end),
                      "breaks_months": int(sp.get("breaks_months") or 0)})
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total = sum(months(a, b) for a, b in merged) - sum(x["breaks_months"] for x in by_id)
    return max(0, total), by_id


# ── estimates (member, public) under the formula in force today ─────────────────────────────────

@router.get("/api/v1/members/me/pension-eligibility-preview")
async def my_estimate(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        m = (await session.execute(select(member_service).where(member_service.c.subject == actor.subject))).mappings().first()
        if not m:
            raise Problem(404, "/problems/not-found", "No service record found")
        key = (await session.execute(select(eps_accounts.c.person_key).where(eps_accounts.c.uan == m["uan"]).limit(1))).scalar_one_or_none()
        spells = [dict(r) for r in (await session.execute(select(eps_accounts).where(eps_accounts.c.person_key == key)
                                                          .order_by(eps_accounts.c.date_of_joining))).mappings().all()] if key else []
        rules = await rules_on(session, today())
    p = section(rules, "pension")
    day = today()
    normal = date(m["date_of_birth"].year + p["normal_age_years"], m["date_of_birth"].month, min(m["date_of_birth"].day, 28))
    if not spells:                                                  # no EPS accounts known: the one service record
        spells = [{"account_link_id": m["account_link_id"], "establishment_id": m["establishment_id"], "date_of_joining": m["date_of_joining"],
                   "date_of_exit": m["date_of_exit"], "breaks_months": 0}]
    served, by_id = eps_service(spells, day)
    in_service = any(sp["date_of_exit"] is None for sp in spells)
    to_normal = served + max(0, (normal - day).days * 12 // 365) if in_service else served
    scenarios = [
        {"label": f"If you leave now and draw your pension at {p['normal_age_years']}", "service_months": served,
         **pension_on(m["eps_wages_paise"], served, p["normal_age_years"], rules)},
        {"label": f"If you stay in service until {p['normal_age_years']} ({normal.year})", "service_months": to_normal,
         **pension_on(m["eps_wages_paise"], to_normal, p["normal_age_years"], rules)}]
    return envelope({"rule_version": rules["rule_version"], "age_years": age_on(m["date_of_birth"], day),
                     "service_months_so_far": served, "service_by_member_id": by_id,
                     "pensionable_salary_paise": min(m["eps_wages_paise"], p["pensionable_salary_cap_paise"]),
                     "min_service_years": p["min_service_years"], "scenarios": scenarios,
                     "note": "An estimate under the rules in force today (illustrative). The pension is fixed when it is settled."})


class Calculation(BaseModel):
    monthly_salary_paise: int = Field(ge=0, le=100_000_000)
    service_years: int = Field(ge=0, le=50)
    age_years: int = Field(ge=18, le=100)


@router.post("/api/v1/public/demo-calculations/pension")
async def calculator(body: Calculation, actor: Actor = Depends(require_actor),   # anonymous callers still pass the gateway
                     session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        rules = await rules_on(session, today())
    return envelope({**pension_on(body.monthly_salary_paise, body.service_years * 12, body.age_years, rules),
                     "rule_version": rules["rule_version"], "illustrative": True})
