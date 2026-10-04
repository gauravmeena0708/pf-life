"""P2.23: the member's PF at retirement, with a VPF what-if (see app/domain/retirement.py). Read-only."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.domain.retirement import forecast
from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence.policy import rules_on

router = APIRouter()
MEMBER = require_stakeholder("member")


@router.get("/api/v1/members/me/retirement-forecast")
async def retirement_forecast(vpf_pct: float = Query(default=0, ge=0, le=100), actor: Actor = Depends(MEMBER)) -> dict:
    """The PF balance today across the member's IDs, the wages of the latest contribution, and the corpus at the normal
    pension age with no VPF and with `vpf_pct` % of wages as VPF."""
    async with sessions()() as session:
        mine = (await session.execute(text("SELECT uan, date_of_birth FROM establishment_members WHERE member_subject=:s LIMIT 1"),
                                      {"s": actor.subject})).mappings().first()
        if not mine:
            raise Problem(404, "/problems/not-found", "No PF account found")
        accounts = (await session.execute(text("SELECT account_link_id, date_of_exit FROM establishment_members WHERE uan=:u"),
                                          {"u": mine["uan"]})).mappings().all()
        links = [a["account_link_id"] for a in accounts]
        open_links = [a["account_link_id"] for a in accounts if a["date_of_exit"] is None]
        balance = 0
        for link in links:
            balance += int((await session.execute(text(
                "SELECT COALESCE(SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END), 0) FROM journal_lines "
                "WHERE account_code='AC01_EPF' AND account_link_id=:a"), {"a": link})).scalar_one())
        rules = await rules_on(session, date.today())
        employee_share = 0
        for link in open_links:                                     # the latest month's 12% gives the wages
            row = (await session.execute(text(
                "SELECT jl.amount_paise FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id WHERE j.kind='CONTRIBUTION' "
                "AND jl.account_link_id=:a AND jl.account_code='AC01_EPF' AND jl.share='employee' AND jl.side='credit' "
                "ORDER BY j.occurred_at DESC LIMIT 1"), {"a": link})).scalar_one_or_none()
            employee_share = max(employee_share, int(row or 0))
    wages = employee_share * 10_000 // rules["contribution"]["epf_employee_rate_bp"]
    born = mine["date_of_birth"] if isinstance(mine["date_of_birth"], date) else date.fromisoformat(str(mine["date_of_birth"]))
    try:
        result = forecast(balance_paise=balance, wages_paise=wages, date_of_birth=born, today=date.today(), rules=rules,
                          vpf_bp=round(vpf_pct * 100), in_service=bool(open_links) and wages > 0)
    except ValueError as exc:
        raise Problem(422, "/problems/validation", "VPF out of range", str(exc)) from exc
    return envelope(result)
