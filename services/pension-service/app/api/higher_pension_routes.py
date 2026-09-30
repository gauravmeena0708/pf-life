"""Phase 2, slice 8c: the joint option for pension on higher wages (illustrative, after the Supreme Court's
judgment of 4 November 2022). The member opts; the present employer validates it and uploads the wages; the dues
are the pension share of the wages above the ceiling for each month, from the `higher_pension` section of the rule
set in force. HigherPensionOptionValidated.v1 records the outcome for the office decision (Phase 3)."""
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import higher_pension_options, member_service
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
MEMBER = require_stakeholder("member")
SIGNATORY = require_stakeholder("employer.signatory")
PRODUCER = "pension-service"
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


async def db():
    async with sessions()() as session:
        yield session


def rupees(paise: int) -> str:
    return f"₹{paise // 100:,}"


def ceiling_for(month: str, rules: dict[str, Any]) -> int:
    ceilings = section(rules, "higher_pension")["wage_ceilings"]
    return next((c["ceiling_paise"] for c in reversed(ceilings) if c["from_month"] <= month), ceilings[0]["ceiling_paise"])


def work_out_dues(lines: list[tuple[str, int]], rules: dict[str, Any]) -> tuple[list[dict[str, Any]], int, str]:
    share = section(rules, "higher_pension")["eps_share_bp"]
    rows, total = [], 0
    for month, wage in sorted(lines):
        ceiling = ceiling_for(month, rules)
        excess = max(0, wage - ceiling)
        dues = excess * share // 10_000
        rows.append({"month": month, "wage_paise": wage, "ceiling_paise": ceiling, "excess_paise": excess, "dues_paise": dues})
        total += dues
    above = sum(1 for r in rows if r["excess_paise"])
    working = (f"{share / 100:g}% of the wages above the ceiling, month by month: {above} of {len(rows)} months above the ceiling, "
               f"dues {rupees(total)} (illustrative; interest on the dues is not worked out here).")
    return rows, total, working


def parse_wages(text: str, joined: date, higher_from: str) -> tuple[list[tuple[str, int]], list[str]]:
    lines, problems, seen = [], [], set()
    this_month = datetime.now(UTC).date().strftime("%Y-%m")
    for n, raw in enumerate([x.strip() for x in text.strip().splitlines() if x.strip()], start=1):
        if raw.lower().startswith("month"):
            continue
        parts = [x.strip() for x in raw.split(",")]
        if len(parts) != 2 or not MONTH.match(parts[0]) or not parts[1].isdigit() or int(parts[1]) <= 0:
            problems.append(f"line {n}: write YYYY-MM,wage in rupees")
            continue
        month = parts[0]
        if month in seen:
            problems.append(f"line {n}: {month} is given twice")
        elif month < joined.strftime("%Y-%m") or month > this_month:
            problems.append(f"line {n}: {month} is outside the member's service")
        elif month < higher_from:
            problems.append(f"line {n}: {month} is before the month the member declared ({higher_from})")
        else:
            seen.add(month)
            lines.append((month, int(parts[1]) * 100))
    if not lines and not problems:
        problems.append("give the wages month by month")
    return lines, problems


def _view(r: dict[str, Any]) -> dict[str, Any]:
    return {"option_id": r["option_id"], "uan": r["uan"], "account_link_id": r["account_link_id"], "state": r["state"],
            "higher_wages_from": r["higher_wages_from"], "dues_paise": r["dues_paise"], "working": r["working"],
            "wages": r["wages"] or [], "rule_version": r["rule_version"], "employer_note": r["employer_note"],
            "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
            "validated_at": r["validated_at"].isoformat() if r["validated_at"] else None,
            "next_step": {"SUBMITTED": "Your employer validates the option and uploads your wages.",
                          "VALIDATED": "Validated by your employer. The office decides and works out the dues with interest (Phase 3).",
                          "REJECTED_BY_EMPLOYER": "Your employer did not validate the option; the reason is shown."}.get(r["state"], "")}


class OptionInput(BaseModel):
    higher_wages_from: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    declaration: bool
    consent_to_dues_adjustment: bool


@router.post("/api/v1/members/me/higher-pension-options", status_code=201)
async def submit_option(body: OptionInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        m = (await session.execute(select(member_service).where(member_service.c.subject == actor.subject))).mappings().first()
        if not m:
            raise Problem(404, "/problems/not-found", "No service record found")
        rules = await rules_on(session, date.today())
        cut = date.fromisoformat(section(rules, "higher_pension")["in_service_on"])
        problems = []
        if m["date_of_joining"] > cut or (m["date_of_exit"] and m["date_of_exit"] < cut):
            problems.append(f"Only members in service on {cut.strftime('%d %B %Y')} may opt (illustrative rule).")
        if m["date_of_exit"]:
            problems.append("The option is filed while in service; pensioners apply through the office.")
        if body.higher_wages_from < m["date_of_joining"].strftime("%Y-%m"):
            problems.append("The month of higher wages cannot be before you joined.")
        if not (body.declaration and body.consent_to_dues_adjustment):
            problems.append("Confirm the declaration and your consent to move the dues from your PF to the pension fund.")
        if (await session.execute(select(higher_pension_options.c.option_id).where(
                higher_pension_options.c.subject == actor.subject, higher_pension_options.c.state != "REJECTED_BY_EMPLOYER"))).first():
            problems.append("You have already opted; follow that application.")
        if problems:
            raise Problem(422, "/problems/not-eligible", "The option cannot be filed", " ".join(problems), errors=problems)
        require_step_up(actor, "submit-higher-pension-option", m["uan"])
        option_id = f"HPO-{secrets.token_hex(4).upper()}"
        await session.execute(insert(higher_pension_options).values(
            option_id=option_id, subject=actor.subject, uan=m["uan"], account_link_id=m["account_link_id"],
            establishment_id=m["establishment_id"] or "-", office_id=m["office_id"], higher_wages_from=body.higher_wages_from,
            state="SUBMITTED"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.higher_option",
                    target_type="higher_pension_option", target_id=option_id)
        row = (await session.execute(select(higher_pension_options).where(higher_pension_options.c.option_id == option_id))).mappings().one()
    return envelope(_view(dict(row)))


@router.get("/api/v1/members/me/higher-pension-options")
async def my_options(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(higher_pension_options).where(higher_pension_options.c.subject == actor.subject)
                                  .order_by(higher_pension_options.c.submitted_at.desc()))).mappings().all()
    rules = await rules_on(session, date.today())
    return envelope({"options": [_view(dict(r)) for r in rows],
                     "in_service_on": section(rules, "higher_pension")["in_service_on"],
                     "note": "Illustrative: members in service on the date shown, on wages above the ceiling, may opt jointly with "
                             "the employer; the employer's pension share of the higher wages then moves from the PF to the pension fund."})


@router.get("/api/v1/members/me/higher-pension-options/{optionId}")
async def my_option(optionId: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    row = (await session.execute(select(higher_pension_options).where(higher_pension_options.c.option_id == optionId,
                                                                      higher_pension_options.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Option not found")
    return envelope(_view(dict(row)))


@router.get("/api/v1/employers/me/higher-pension-options")
async def employer_options(actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(higher_pension_options, member_service.c.name, member_service.c.date_of_joining).join(
        member_service, member_service.c.subject == higher_pension_options.c.subject).where(
        higher_pension_options.c.establishment_id == (actor.establishment_id or "-"))
        .order_by(higher_pension_options.c.submitted_at))).mappings().all()
    return envelope([{**_view(dict(r)), "name": r["name"], "date_of_joining": r["date_of_joining"].isoformat()} for r in rows])


class Validation(BaseModel):
    decision: str = Field(pattern="^(VALIDATE|REJECT)$")
    wages: str = Field(default="", max_length=40_000)          # CSV: YYYY-MM,wage in rupees
    note: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/employers/me/higher-pension-options/{optionId}/validations")
async def validate_option(optionId: str, body: Validation, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        row = (await session.execute(select(higher_pension_options).where(
            higher_pension_options.c.option_id == optionId,
            higher_pension_options.c.establishment_id == (actor.establishment_id or "-")))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Option not found")
        if row["state"] != "SUBMITTED":
            raise Problem(409, "/problems/invalid-state", "This option is already decided", f"Current status: {row['state']}.")
        rules = await rules_on(session, date.today())
        values: dict[str, Any] = {"employer_note": body.note, "validated_by": actor.subject, "validated_at": datetime.now(UTC),
                                  "rule_version": rules["rule_version"]}
        if body.decision == "VALIDATE":
            joined = (await session.execute(select(member_service.c.date_of_joining).where(
                member_service.c.subject == row["subject"]))).scalar_one()
            lines, problems = parse_wages(body.wages, joined, row["higher_wages_from"])
            if problems:
                raise Problem(422, "/problems/validation", "Please correct the wages", "; ".join(problems[:10]), errors=problems)
            wages, dues, working = work_out_dues(lines, rules)
            if not dues:
                raise Problem(422, "/problems/validation", "No month is above the wage ceiling",
                              "A higher pension needs wages above the ceiling; reject the option instead.")
            values.update(state="VALIDATED", wages=wages, dues_paise=dues, working=working)
        else:
            values.update(state="REJECTED_BY_EMPLOYER")
        require_step_up(actor, "validate-higher-pension", optionId, None, values.get("dues_paise"))
        await session.execute(update(higher_pension_options).where(higher_pension_options.c.option_id == optionId).values(**values))
        await add_event(session, producer=PRODUCER, event_type="HigherPensionOptionValidated.v1", aggregate_type="higher_pension_option",
                        aggregate_id=optionId, correlation_id=actor.correlation_id, payload={
                            "option_id": optionId, "uan": row["uan"], "account_link_id": row["account_link_id"],
                            "establishment_id": row["establishment_id"], "decision": values["state"],
                            "dues_paise": values.get("dues_paise") or 0, "months": len(values.get("wages") or []),
                            "rule_version": rules["rule_version"]})
        await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=optionId, correlation_id=actor.correlation_id, payload={
                            "recipient_subject": row["subject"], "template": "HIGHER_PENSION_" + values["state"], "reference_id": optionId,
                            "params": {"amount_paise": values.get("dues_paise") or 0, "reason": body.note}})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pension.higher_option_validation",
                    target_type="higher_pension_option", target_id=optionId, detail=values["state"])
        row = (await session.execute(select(higher_pension_options).where(higher_pension_options.c.option_id == optionId))).mappings().one()
    return envelope(_view(dict(row)))


@router.post("/api/v1/employers/me/higher-pension-options/{optionId}/dues-previews")
async def preview_dues(optionId: str, body: Validation, actor: Actor = Depends(SIGNATORY), session: AsyncSession = Depends(db)) -> dict:
    """The dues the wages give, before the signatory confirms (the confirmation is bound to this amount)."""
    row = (await session.execute(select(higher_pension_options).where(
        higher_pension_options.c.option_id == optionId,
        higher_pension_options.c.establishment_id == (actor.establishment_id or "-")))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Option not found")
    joined = (await session.execute(select(member_service.c.date_of_joining).where(member_service.c.subject == row["subject"]))).scalar_one()
    lines, problems = parse_wages(body.wages, joined, row["higher_wages_from"])
    if problems:
        raise Problem(422, "/problems/validation", "Please correct the wages", "; ".join(problems[:10]), errors=problems)
    wages, dues, working = work_out_dues(lines, await rules_on(session, date.today()))
    return envelope({"option_id": optionId, "dues_paise": dues, "working": working, "wages": wages})
