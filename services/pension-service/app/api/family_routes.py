"""Phase 2, slice 6b: family pension (Form 10D by the widow / widower or a child of a member who died in service).
It then runs through the same desks as a member's Form 10D — IDS (DA Accounts) → AO → worksheet (DA Pension) →
APFC (Pension) → PPO → initial arrear → e-sign → dispatch — with the family-pension formula in the worksheet."""
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settlement_routes import _view, db, months_between
from app.domain.pension import today
from app.infra.tables import family_members, member_service, pension_claims
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence.policy import family_pension_on, rules_on

router = APIRouter()
FAMILY = require_stakeholder("claimant", "family_pensioner")


class FamilyApplication(BaseModel):
    form_type: str = Field(default="FORM_10D", pattern="^FORM_10D$")
    deceased_uan: str = Field(pattern=r"^[0-9]{12}$")


@router.post("/api/v1/claimants/family-pension-applications", status_code=201)
async def apply(body: FamilyApplication, actor: Actor = Depends(FAMILY), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        me = (await session.execute(select(family_members).where(family_members.c.uan == body.deceased_uan,
                                                                 family_members.c.subject == actor.subject))).mappings().first()
        if not me:
            raise Problem(404, "/problems/not-found", "You are not on record as family of that member",
                          "Family on record comes from the member's nomination; otherwise apply at the PRO counter with documents.")
        m = (await session.execute(select(member_service).where(member_service.c.uan == body.deceased_uan))).mappings().first()
        if not m or not m["date_of_exit"]:
            raise Problem(422, "/problems/death-not-recorded", "The member's death is not recorded",
                          "The employer marks the exit with the reason 'death while in service' first.")
        require_step_up(actor, "file-family-pension", body.deceased_uan)
        if (await session.execute(select(pension_claims.c.claim_id).where(pension_claims.c.member_subject == actor.subject,
                                                                          pension_claims.c.state != "REJECTED"))).first():
            raise Problem(409, "/problems/already-applied", "A pension application is already on file")
        rules = await rules_on(session, today())
        service = months_between(m["date_of_joining"], m["date_of_exit"])
        estimate = family_pension_on(m["eps_wages_paise"], service, me["relation"], rules)
        start = m["date_of_exit"] + timedelta(days=1)
        family = {"deceased_name": m["name"], "deceased_uan": body.deceased_uan, "died_on": m["date_of_exit"].isoformat(),
                  "relation": me["relation"], "claimant_name": me["name"]}
        claim = {"claim_id": f"PC-{secrets.token_hex(4).upper()}", "member_subject": actor.subject, "uan": body.deceased_uan, "name": me["name"],
                 "date_of_birth": me["date_of_birth"], "account_link_id": m["account_link_id"], "office_id": m["office_id"] or "RO-DEMO-01",
                 "pension_from": start, "state": "SUBMITTED", "service_months": service, "aggregated": [],
                 "pensionable_salary_paise": m["eps_wages_paise"], "kind": me["relation"], "family": family,
                 "history": [{"state": "SUBMITTED", "role": "claimant", "by": actor.subject,
                              "note": f"Form 10D (family pension) filed by the {me['relation'].lower()} of {m['name']}",
                              "at": datetime.now(UTC).isoformat()}]}
        await session.execute(insert(pension_claims).values(**claim))
    return envelope({**_view(claim), "estimate": {k: estimate[k] for k in ("monthly_paise", "working")}})


@router.get("/api/v1/claimants/family-pension-applications")
async def mine(actor: Actor = Depends(FAMILY), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(pension_claims).where(pension_claims.c.member_subject == actor.subject, pension_claims.c.kind != "MEMBER")
                                  .order_by(pension_claims.c.created_at.desc()))).mappings().all()
    return envelope([_view(dict(r)) for r in rows])

