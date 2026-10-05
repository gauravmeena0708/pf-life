"""Phase 2, slice 6b: family pension (Form 10D by the widow / widower or a child of a member who died in service).
It then runs through the same desks as a member's Form 10D — IDS (DA Accounts) → AO → worksheet (DA Pension) →
APFC (Pension) → PPO → initial arrear → e-sign → dispatch — with the family-pension formula in the worksheet."""
import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settlement_routes import _office, _view, db, months_between
from app.domain.pension import age_on, today
from app.infra.tables import family_members, member_service, pension_claims, pensioners
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import family_pension_on, rules_on, section

router = APIRouter()
FAMILY = require_stakeholder("claimant", "family_pensioner")


class FamilyBeneficiary(BaseModel):
    deceased_uan: str = Field(pattern=r"^[0-9]{12}$")
    subject: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=3, max_length=120)
    relation: str = Field(pattern="^(FATHER|MOTHER|NOMINEE)$")
    date_of_birth: date
    dependent: bool = False
    nomination_valid: bool = False
    evidence_ref: str = Field(min_length=5, max_length=120)


@router.post("/api/v1/office/pensions/family-beneficiaries", status_code=201)
async def record_beneficiary(body: FamilyBeneficiary, actor: Actor = Depends(require_stakeholder("fo.da_pension")),
                             session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        member = (await session.execute(select(member_service).where(member_service.c.uan == body.deceased_uan,
                         member_service.c.office_id == office))).mappings().first()
        if not member or not member["date_of_exit"]:
            raise Problem(404, "/problems/not-found", "Deceased member not found in your office")
        require_step_up(actor, "record-family-beneficiary", body.deceased_uan)
        if body.date_of_birth >= member["date_of_exit"] or (body.relation in ("FATHER", "MOTHER") and not body.dependent) or (
                body.relation == "NOMINEE" and not body.nomination_valid):
            raise Problem(422, "/problems/validation", "Record the documented dependency or valid EPS nomination")
        existing = (await session.execute(select(family_members.c.id).where(family_members.c.uan == body.deceased_uan,
                    family_members.c.subject == body.subject))).first()
        if existing:
            raise Problem(409, "/problems/already-recorded", "This beneficiary is already on record")
        # EPS para 16(5)(a),(aa): the office verifies the EPS nomination or parental dependency.
        record = {"id": f"FAM-{secrets.token_hex(6).upper()}", "uan": body.deceased_uan, "subject": body.subject,
                  "name": body.name.strip().upper(), "relation": body.relation, "date_of_birth": body.date_of_birth,
                  "dependent": body.dependent, "nomination_valid": body.nomination_valid, "evidence_ref": body.evidence_ref}
        await session.execute(insert(family_members).values(**record))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.family_beneficiary_recorded",
                    target_type="family_beneficiary", target_id=record["id"], detail=body.evidence_ref)
    return envelope({"beneficiary_id": record["id"], "relation": body.relation, "deceased_uan": body.deceased_uan})


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
        until = section(rules, "pension").get("family", {}).get("child_until_age", 25)
        relatives = (await session.execute(select(family_members).where(family_members.c.uan == body.deceased_uan))).mappings().all()
        living = [r for r in relatives if not r["date_of_death"] or r["date_of_death"] > m["date_of_exit"]]
        eligible_children = [r for r in living if r["relation"] == "CHILD" and
                             (r["disabled"] or age_on(r["date_of_birth"], m["date_of_exit"]) < until)]
        family_exists = any(r["relation"] == "SPOUSE" for r in living) or bool(eligible_children)
        nominee = next((r for r in living if r["relation"] == "NOMINEE" and r["nomination_valid"]), None)
        if me["date_of_death"] and me["date_of_death"] <= today():
            raise Problem(422, "/problems/not-eligible", "The claimant is recorded as deceased")
        if me["relation"] == "NOMINEE" and (family_exists or not me["nomination_valid"] or nominee["id"] != me["id"]):
            raise Problem(422, "/problems/not-eligible", "A valid EPS nominee takes the pension only when no family survives")
        if me["relation"] in ("FATHER", "MOTHER"):
            father = next((r for r in relatives if r["relation"] == "FATHER" and r["dependent"]), None)
            father_alive = father and (not father["date_of_death"] or father["date_of_death"] > today())
            # EPS 1995 para 16(5)(aa): nominee before parents; father before mother, each for life.
            if family_exists or nominee or not me["dependent"] or (me["relation"] == "MOTHER" and father_alive):
                raise Problem(422, "/problems/not-eligible", "Dependent parent pension is not yet payable")
        if me["relation"] not in ("SPOUSE", "CHILD", "NOMINEE", "FATHER", "MOTHER"):
            raise Problem(422, "/problems/not-eligible", "No family pension entitlement for this relation")
        if me["relation"] == "CHILD" and not me.get("disabled") and age_on(me["date_of_birth"], m["date_of_exit"]) >= until:
            raise Problem(422, "/problems/not-eligible", "Not eligible for a children's pension",
                          f"A child must be under {until} on the member's death (Pension Manual 2.10.1.1), unless disabled — then for life (2.13.10).")
        if me["relation"] == "CHILD":
            eligible_now = [r for r in eligible_children if r["disabled"] or age_on(r["date_of_birth"], today()) < until]
            ordered = sorted(eligible_now, key=lambda r: (r["date_of_birth"], r["id"]))
            max_children = section(rules, "pension").get("family", {}).get("max_children", 2)
            # Pension Manual 2.13.10: disabled children beyond the first two draw in addition.
            if me["id"] not in {r["id"] for r in ordered[:max_children]} and not me["disabled"]:
                raise Problem(422, "/problems/not-eligible", "The first two eligible children have priority")
        service = months_between(m["date_of_joining"], m["date_of_exit"])
        estimate = family_pension_on(m["eps_wages_paise"], service,
                                     "SPOUSE" if me["relation"] in ("NOMINEE", "FATHER", "MOTHER") else me["relation"], rules)
        start = m["date_of_exit"] + timedelta(days=1)
        if me["relation"] == "MOTHER" and father and father["date_of_death"]:
            start = max(start, father["date_of_death"] + timedelta(days=1))
            await session.execute(update(pensioners).where(pensioners.c.subject == father["subject"],
                    pensioners.c.uan == body.deceased_uan, pensioners.c.status == "IN_PAYMENT").values(
                    status="STOPPED", status_reason="Dependent father died; dependent mother succeeds (EPS para 16(5)(aa))"))
        family = {"deceased_name": m["name"], "deceased_uan": body.deceased_uan, "died_on": m["date_of_exit"].isoformat(),
                  "relation": me["relation"], "claimant_name": me["name"], "disabled_child": bool(me.get("disabled"))}
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
