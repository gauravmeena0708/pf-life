"""P2.24: compare proposed contribution rules against synthetic account data without posting them."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.domain.ecr import parse, split
from app.infra.db import sessions
from app.infra.interest import interest_due
from epfo_auth import Actor, require_stakeholder
from epfo_observability import envelope
from epfo_persistence import audit
from epfo_persistence.policy import interest_rate_bp, rules_on

router = APIRouter()
OFFICE = require_stakeholder("ho.fa_cao")


class SimulationInput(BaseModel):
    financial_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    interest_rate_bp: int | None = Field(default=None, ge=0, le=2000)
    wage_ceiling_paise: int | None = Field(default=None, ge=0, le=100_000_000)
    employee_rate_bp: int | None = Field(default=None, ge=0, le=3000)
    employer_rate_bp: int | None = Field(default=None, ge=0, le=3000)

    @model_validator(mode="after")
    def has_scenario(self):
        if not any(getattr(self, k) is not None for k in ("interest_rate_bp", "wage_ceiling_paise", "employee_rate_bp", "employer_rate_bp")):
            raise ValueError("Provide at least one proposed rule value")
        return self


@router.post("/api/v1/office/accounts/rule-change-simulations")
async def simulate_rules(body: SimulationInput, actor: Actor = Depends(OFFICE)):
    async with sessions()() as session, session.begin():
        rules = await rules_on(session, __import__("datetime").date(int(body.financial_year[:4]), 4, 1))
        current_rate = interest_rate_bp(rules, body.financial_year) or 0
        new_rate = body.interest_rate_bp if body.interest_rate_bp is not None else current_rate
        # EPF Scheme para 60: reuse the production monthly-closing-balance calculation; only the rate is substituted.
        old_interest = await interest_due(session, body.financial_year, current_rate)
        new_interest = await interest_due(session, body.financial_year, new_rate)
        balances = {r["account_link_id"]: r for r in new_interest}
        old_by_account = {r["account_link_id"]: r for r in old_interest}
        members = (await session.execute(text("SELECT account_link_id, uan, name, date_of_birth, international_worker FROM establishment_members ORDER BY account_link_id"))).mappings().all()
        proposed = json.loads(json.dumps(rules))
        c = proposed["contribution"]
        if body.wage_ceiling_paise is not None:
            c["eps_wage_ceiling_paise"] = c["edli_wage_ceiling_paise"] = body.wage_ceiling_paise
        if body.employee_rate_bp is not None:
            c["epf_employee_rate_bp"] = body.employee_rate_bp
        if body.employer_rate_bp is not None and body.employer_rate_bp < c["eps_rate_bp"]:
            from epfo_observability import Problem
            raise Problem(422, "/problems/invalid-employer-rate", "The employer rate cannot be below the pension allocation rate.")
        # A member's latest posted synthetic ECR row is the comparison basis for the proposed wage rules.
        postings = (await session.execute(text("SELECT content, format FROM ecr_filings WHERE state IN ('POSTED','SUBMITTED') ORDER BY wage_month DESC, created_at DESC"))).mappings().all()
        by_uan = {}
        for filing in postings:
            for row in parse(filing["content"], filing["format"])[0]:
                by_uan.setdefault(row.get("UAN"), row)
        changes: list[tuple[str, int, int]] = []
        for member in members:
            account = member["account_link_id"]
            old = old_by_account.get(account, {})
            new = balances.get(account, {})
            interest_delta = sum(new.get(part, {}).get("due_paise", 0) - old.get(part, {}).get("due_paise", 0) for part in ("employee", "employer"))
            contribution_delta = 0
            row = by_uan.get(member["uan"])
            if row:
                wages = [int(row.get(k) or 0) * 100 for k in ("EPF Wages", "EPS Wages", "EDLI Wages")]
                age = 0
                if member["date_of_birth"]:
                    from datetime import date
                    born = member["date_of_birth"]
                    born = date.fromisoformat(str(born)[:10]) if not isinstance(born, date) else born
                    age = date.today().year - born.year - ((date.today().month, date.today().day) < (born.month, born.day))
                # The member's own PF credit for the month (employee share + the employer's EPF share): the pension,
                # EDLI and admin parts are not the member's balance.
                credit = lambda r: r["AC01_EPF_EE"] + r["AC01_EPF_ER"]
                old_total = credit(split(*wages[:2], age, rules, wages[2]))
                new_employer_rate = body.employer_rate_bp if body.employer_rate_bp is not None else rules["contribution"]["epf_employee_rate_bp"]
                new_total = credit(split(*wages[:2], age, proposed, wages[2], employer_rate_bp=new_employer_rate))
                contribution_delta = new_total - old_total
            balance = (await session.execute(text("SELECT COALESCE(SUM(CASE WHEN jl.side='credit' THEN jl.amount_paise ELSE -jl.amount_paise END),0) FROM journal_lines jl WHERE jl.account_code='AC01_EPF' AND jl.account_link_id=:a"), {"a": account})).scalar_one()
            changes.append((account, interest_delta + contribution_delta, int(balance)))
        def summary(name: str, entries: list[tuple[str, int, int]]) -> dict[str, int | str]:
            amounts = sorted(n for _, n, _ in entries)
            middle = len(amounts) // 2
            med = amounts[middle] if len(amounts) % 2 else ((amounts[middle - 1] + amounts[middle]) // 2 if amounts else 0)
            return {"band": name, "member_count": len(amounts), "min_change_paise": min(amounts, default=0), "median_change_paise": med,
                    "max_change_paise": max(amounts, default=0), "gain_count": sum(n > 0 for n in amounts), "lose_count": sum(n < 0 for n in amounts)}
        ranked = sorted(changes, key=lambda entry: entry[2])
        chunks = [ranked[i * len(ranked) // 3:(i + 1) * len(ranked) // 3] for i in range(3)] if ranked else [[], [], []]
        values = [n for _, n, _ in changes]
        data = {"sample_size": len(values), "total_change_paise": sum(values),
                "bands": [summary(name, group) for name, group in zip(("lower balance", "middle balance", "upper balance"), chunks)],
                "illustrative_members": [{"synthetic_id": f"SIM-{i+1:03d}", "change_paise": n} for i, (_, n, _) in enumerate(sorted(changes, key=lambda x: x[0])[:3])],
                "sample_basis": "every member of the (synthetic) establishments: the year's interest on their ledger balances, and one month's PF credit from their latest posted return"}
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="rule_change.simulated",
                    target_type="rule_simulation", target_id=str(uuid.uuid4()), detail=json.dumps(body.model_dump(exclude_none=True), sort_keys=True))
        return envelope(data)
