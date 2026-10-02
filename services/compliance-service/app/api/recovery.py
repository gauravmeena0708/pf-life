"""P2.11d — recovery of assessed dues under s.8B-8G (EPFO Recovery Manual, 08/12/2023): the Authorised Officer's recovery
certificate, the Recovery Officer's demand notice (EPFCP-1, 15 days), instalments, the other modes of s.8F (a bank or a debtor
pays EPFO), attachment and sale, a receiver, arrest and detention (records only — no property, warrant or prison in a POC);
and the HO reports on proceedings and recovery. Realisations reach contribution-service as RecoveryRealised.v1."""
import secrets
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.proceedings import BASE, dt, event, inquiry, iso, now, record, rules
from app.api.routes import _office, db
from app.infra.tables import (compliance_officers, demands, establishments, inquiries, legal_cases, office_staff, recovery_actions,
                              recovery_cases)
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope

router = APIRouter()
RECOVERY = "/api/v1/office/recovery"
COERCIVE = {"GARNISHEE_8F", "ATTACHMENT", "SALE", "RECEIVER", "ARREST"}


async def act(session: AsyncSession, case_id: str, kind: str, subject: str, detail: dict) -> None:
    await session.execute(insert(recovery_actions).values(action_id=f"RA-{secrets.token_hex(6)}", recovery_case_id=case_id, kind=kind,
                                                          detail=detail, actor_subject=subject, occurred_at=now()))


async def actions_of(session: AsyncSession, case_id: str) -> list[dict]:
    rows = (await session.execute(select(recovery_actions).where(recovery_actions.c.recovery_case_id == case_id)
                                  .order_by(recovery_actions.c.occurred_at))).mappings().all()
    return [{"kind": r["kind"], "at": iso(r["occurred_at"]), "detail": r["detail"]} for r in rows]


async def view(session: AsyncSession, row: dict) -> dict:
    stayed = bool(row["inquiry_case_id"]) and bool((await session.execute(select(legal_cases.c.legal_case_id).where(
        legal_cases.c.inquiry_case_id == row["inquiry_case_id"], legal_cases.c.stayed.is_(True)))).first())
    return {**row, "issued_at": iso(row["issued_at"]), "pay_by": iso(row["pay_by"]), "closed_at": iso(row["closed_at"]),
            "outstanding_paise": int(row["amount_paise"]) - int(row["realised_paise"]), "stayed": stayed,
            "actions": await actions_of(session, row["recovery_case_id"])}


async def case_of(session: AsyncSession, case_id: str, office: str) -> dict:
    row = (await session.execute(select(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id))).mappings().first()
    if not row or row["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Recovery case not found")
    return dict(row)


async def coercion_allowed(session: AsyncSession, row: dict, kind: str, urgent_reason: str | None = None) -> None:
    """A step that takes the defaulter's money or property: not while a court stays recovery, not while instalments run, and
    not before the 15 days of the demand notice unless the officer records why it cannot wait (para 1.5 i)."""
    current = await view(session, row)
    if current["stayed"]:
        raise Problem(409, "/problems/stayed", "Recovery is stayed by a court or tribunal order")
    if row["state"] == "CLOSED":
        raise Problem(409, "/problems/closed", "The certificate is satisfied")
    if row["state"] == "INSTALMENTS":
        raise Problem(409, "/problems/instalments", "Instalments are running; coercive steps wait unless they are defaulted")
    if kind in COERCIVE - {"GARNISHEE_8F"}:
        if not row["pay_by"] and not urgent_reason:
            raise Problem(409, "/problems/notice-first", "Serve the demand notice (EPFCP-1) first")
        if row["pay_by"] and now() <= dt(row["pay_by"]) and not urgent_reason:
            raise Problem(409, "/problems/notice-period", "The 15 days of the demand notice have not run; record the reason if the "
                          "defaulter is likely to conceal or remove property (para 1.5 i)")


async def realise(session: AsyncSession, actor: Actor, row: dict, amount: int, mode: str, reference: str) -> dict:
    """Money realised: applied to the certificate's demands (contribution-service posts it); the certificate closes when satisfied."""
    applied = min(amount, int(row["amount_paise"]) - int(row["realised_paise"]))
    if applied <= 0:
        return row
    realised = int(row["realised_paise"]) + applied
    values = {"realised_paise": realised}
    if realised >= int(row["amount_paise"]):
        values.update(state="CLOSED", closed_at=now())
    await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == row["recovery_case_id"]).values(**values))
    await act(session, row["recovery_case_id"], "REALISATION", actor.subject, {"amount_paise": applied, "mode": mode, "reference": reference})
    await event(session, actor, "RecoveryRealised.v1", "recovery_case", row["recovery_case_id"],
                {"recovery_case_id": row["recovery_case_id"], "establishment_id": row["establishment_id"], "demand_ids": row["demand_ids"],
                 "amount_paise": applied, "mode": mode, "reference": reference})
    return {**row, **values}


# ── the certificate (s.8B) ─────────────────────────────────────────────────────────────────────────────────────────────
class CertificateInput(BaseModel):
    note: str = Field(min_length=1)


@router.post(BASE + "/cases/{case_id}/recovery-certificates", status_code=201)
async def certify(case_id: str, body: CertificateInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                  session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        row = await inquiry(session, case_id, office)
        require_step_up(actor, "issue-recovery-certificate", case_id)
        if row["state"] not in ("ORDERED", "PART_ORDERED"):
            raise Problem(409, "/problems/invalid-state", "A recovery certificate issues on a passed order")
        _, limits = await rules(session)
        if now() <= dt(row["ordered_at"]) + timedelta(days=limits["pay_after_order_days"]):
            raise Problem(409, "/problems/not-in-arrears", f"The order allows {limits['pay_after_order_days']} days to pay; not yet in arrears")
        open_demands = (await session.execute(select(demands).where(demands.c.demand_id.in_(row["order_demand_ids"] or ["-"]),
                                                                    demands.c.state == "OPEN"))).mappings().all()
        if not open_demands:
            raise Problem(409, "/problems/nothing-due", "The order's dues are paid")
        if (await session.execute(select(recovery_cases.c.recovery_case_id).where(recovery_cases.c.inquiry_case_id == case_id,
                                                                                  recovery_cases.c.state != "CLOSED"))).first():
            raise Problem(409, "/problems/already-certified", "A certificate for this order is already being executed")
        officer = (await session.execute(select(office_staff.c.subject).where(office_staff.c.office_id == office,
                   office_staff.c.stakeholder == "fo.recovery_officer"))).scalar_one_or_none()
        if not officer:
            raise Problem(422, "/problems/no-officer", "No Recovery Officer is posted to the office")
        amount = sum(int(d["amount_paise"]) for d in open_demands)
        rc = dict(recovery_case_id=f"RC-{secrets.token_hex(4).upper()}", office_id=office, establishment_id=row["establishment_id"],
                  inquiry_case_id=case_id, certificate_no=f"RC/{office}/{now().year}/{secrets.randbelow(9000) + 1000}",
                  demand_ids=[d["demand_id"] for d in open_demands], amount_paise=amount, realised_paise=0, state="CERTIFIED",
                  recovery_officer=officer, issued_by=actor.subject, issued_at=now(), pay_by=None, closed_at=None)
        await session.execute(insert(recovery_cases).values(**rc))
        await act(session, rc["recovery_case_id"], "CERTIFICATE", actor.subject, {"note": body.note, "diary_no": row["diary_no"]})
        await event(session, actor, "RecoveryCertificateIssued.v1", "recovery_case", rc["recovery_case_id"],
                    {"recovery_case_id": rc["recovery_case_id"], "establishment_id": rc["establishment_id"], "inquiry_case_id": case_id,
                     "amount_paise": amount})
        await record(session, actor, "recovery.certificate", "recovery_case", rc["recovery_case_id"], rc["certificate_no"])
        result = await view(session, rc)
    return envelope(result)


@router.get(RECOVERY + "/cases")
async def recovery_cases_list(state: str | None = Query(None), actor: Actor = Depends(require_stakeholder("fo.recovery_officer", "fo.apfc", "fo.oic")),
                              session: AsyncSession = Depends(db)):
    query = select(recovery_cases).where(recovery_cases.c.office_id == await _office(session, actor)).order_by(recovery_cases.c.issued_at.desc())
    if state:
        query = query.where(recovery_cases.c.state == state)
    return envelope([await view(session, dict(r)) for r in (await session.execute(query)).mappings().all()])


async def officer_case(session: AsyncSession, case_id: str, actor: Actor) -> dict:
    row = await case_of(session, case_id, await _office(session, actor))
    if row["recovery_officer"] != actor.subject:
        raise Problem(403, "/problems/recovery-officer", "Only the Recovery Officer executing the certificate")
    return row


@router.post(RECOVERY + "/{case_id}/demand-notices")
async def demand_notice(case_id: str, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")), session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        if row["state"] != "CERTIFIED":
            raise Problem(409, "/problems/invalid-state", "The demand notice is served once, on a new certificate")
        _, limits = await rules(session)
        pay_by = now() + timedelta(days=limits["demand_notice_days"])
        await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id).values(state="NOTICE_SERVED", pay_by=pay_by))
        await act(session, case_id, "DEMAND_NOTICE", actor.subject, {"form": "EPFCP-1", "pay_by": pay_by.isoformat(), "served": "by e-mail and speed post (mock)"})
        await record(session, actor, "recovery.demand_notice", "recovery_case", case_id, pay_by.isoformat())
        result = await view(session, {**row, "state": "NOTICE_SERVED", "pay_by": pay_by})
    return envelope(result)


class InstalmentInput(BaseModel):
    count: int = Field(ge=2)
    first_due: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    bank_guarantee_paise: int = Field(ge=0)
    bank_guarantee_ref: str = Field(min_length=3, max_length=60)
    note: str = Field(min_length=1)


async def _power(session: AsyncSession, actor: Actor, powers: dict) -> tuple[str, int | None]:
    """Who the actor is for instalments, and the most arrears they may grant them on (None: no limit)."""
    if actor.stakeholder in powers:
        return actor.stakeholder, powers[actor.stakeholder]
    rank = (await session.execute(select(compliance_officers.c.rank).where(compliance_officers.c.subject == actor.subject))).scalar_one_or_none()
    rank = rank if rank in powers else "RPFC-II"                # an officer in charge without a recorded rank: the lowest power
    return rank, powers[rank]


@router.post(RECOVERY + "/{case_id}/instalments")
async def instalments(case_id: str, body: InstalmentInput, actor: Actor = Depends(require_stakeholder("fo.oic", "zo.acc", "ho.cpfc")),
                      session: AsyncSession = Depends(db)):
    """Instalments on a certificate (Recovery Manual, circulars of 7.4.2006, 11.4.2012 and 11.02.2014): up to 36 by the
    officer whose power covers the arrears; more than 36 (at most 72) only by Head Office, with a guarantee of six
    instalments and never for an establishment that defaulted on a facility before. Each instalment is paid with that
    month's 7Q interest and the current dues; a default withdraws the facility without notice."""
    async with session.begin():
        if actor.stakeholder == "fo.oic":
            row = await case_of(session, case_id, await _office(session, actor))
        else:                                                   # the zone or Head Office, on a field office's certificate
            row = (await session.execute(select(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id))).mappings().first()
            if not row:
                raise Problem(404, "/problems/not-found", "Recovery case not found")
            row = dict(row)
        _, limits = await rules(session)
        if body.count > limits["max_instalments"]:
            raise Problem(422, "/problems/validation", f"At most {limits['max_instalments']} instalments")
        if row["state"] in ("CLOSED", "INSTALMENTS"):
            raise Problem(409, "/problems/invalid-state", "Not on a satisfied certificate or one already in instalments")
        outstanding = int(row["amount_paise"]) - int(row["realised_paise"])
        who, power = await _power(session, actor, limits["instalment_powers_paise"])
        beyond = body.count > limits["normal_instalments"]
        if beyond and actor.stakeholder != "ho.cpfc" or power is not None and outstanding > power:
            raise Problem(403, "/problems/beyond-powers", "Beyond your powers to grant",
                          f"{who} may grant up to {limits['normal_instalments']} instalments on arrears up to "
                          f"₹{(power or 0) // 100:,}; more than {limits['normal_instalments']} instalments, or more arrears, go to "
                          + ("the zone or " if not beyond else "") + "Head Office.")
        each, extra = divmod(outstanding, body.count)
        need = (each + (1 if extra else 0)) * (limits["guarantee_instalments_beyond_normal"] if beyond else limits["guarantee_instalments"])
        if body.bank_guarantee_paise < need:
            raise Problem(422, "/problems/guarantee", "The bank guarantee is too small",
                          f"A revolving guarantee of {'six instalments' if beyond else 'one instalment'} is needed: ₹{need // 100:,}.")
        if beyond:
            defaulted = (await session.execute(select(recovery_actions.c.action_id).join(
                recovery_cases, recovery_cases.c.recovery_case_id == recovery_actions.c.recovery_case_id).where(
                recovery_cases.c.establishment_id == row["establishment_id"], recovery_actions.c.kind == "INSTALMENT_DEFAULT"))).first()
            if defaulted:
                raise Problem(409, "/problems/defaulted-before", "No second facility after a default",
                              "This establishment defaulted on instalments before (circular 11.02.2014 para 3 b).")
        schedule = [{"number": i + 1, "amount_paise": each + (1 if i < extra else 0)} for i in range(body.count)]
        await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id).values(state="INSTALMENTS"))
        await act(session, case_id, "INSTALMENTS", actor.subject, {
            "count": body.count, "first_due": body.first_due, "schedule": schedule, "note": body.note, "granted_as": who,
            "bank_guarantee_paise": body.bank_guarantee_paise, "bank_guarantee_ref": body.bank_guarantee_ref,
            "with_each": "that month's 7Q interest and the current contributions"})
        await record(session, actor, "recovery.instalments", "recovery_case", case_id, f"{body.count} from {body.first_due} by {who}")
        result = await view(session, {**row, "state": "INSTALMENTS"})
    return envelope(result)


class DefaultInput(BaseModel):
    missed: str = Field(min_length=3, max_length=200)


@router.post(RECOVERY + "/{case_id}/instalment-defaults")
async def instalment_default(case_id: str, body: DefaultInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")),
                             session: AsyncSession = Depends(db)):
    """A missed instalment, or the current dues unpaid: the facility is withdrawn without notice and recovery resumes."""
    async with session.begin():
        row = await case_of(session, case_id, await _office(session, actor))
        if row["state"] != "INSTALMENTS":
            raise Problem(409, "/problems/invalid-state", "No instalments are running")
        back = "NOTICE_SERVED" if row["pay_by"] else "CERTIFIED"
        await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id).values(state=back))
        await act(session, case_id, "INSTALMENT_DEFAULT", actor.subject, {"missed": body.missed, "facility": "withdrawn without notice"})
        await record(session, actor, "recovery.instalment_default", "recovery_case", case_id, body.missed)
        result = await view(session, {**row, "state": back})
    return envelope(result)


class PaymentInput(BaseModel):
    amount_paise: int = Field(gt=0)
    reference: str = Field(min_length=4)
    mode: Literal["DIRECT", "INSTALMENT"] = "DIRECT"


@router.post(RECOVERY + "/{case_id}/payments")
async def payment(case_id: str, body: PaymentInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")), session: AsyncSession = Depends(db)):
    """A payment the defaulter makes to the Recovery Officer (collection register): applied to the certificate's demands."""
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        if any(a["detail"].get("reference") == body.reference for a in await actions_of(session, case_id) if a["kind"] == "REALISATION"):
            return envelope(await view(session, row))
        row = await realise(session, actor, row, body.amount_paise, body.mode, body.reference)
        result = await view(session, row)
    return envelope(result)


# ── other modes (s.8F): a bank or a debtor of the employer pays EPFO ──────────────────────────────────────────────────────
class GarnisheeInput(BaseModel):
    garnishee: Literal["BANK", "DEBTOR"]
    name: str = Field(min_length=2)
    reference: str = Field(min_length=4)              # the account or the debt
    amount_paise: int = Field(gt=0)
    paid_paise: int | None = Field(default=None, ge=0)   # what the bank / debtor paid on the notice (mock: the amount, unless given)


@router.post(BASE + "/cases/{case_id}/recovery-8f")
async def garnishee(case_id: str, body: GarnisheeInput, actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.oic")),
                    session: AsyncSession = Depends(db)):
    async with session.begin():
        office = await _office(session, actor)
        await inquiry(session, case_id, office)
        require_step_up(actor, "garnishee-8f", case_id, None, body.amount_paise)
        row = (await session.execute(select(recovery_cases).where(recovery_cases.c.inquiry_case_id == case_id,
                                                                  recovery_cases.c.state != "CLOSED"))).mappings().first()
        if not row:
            raise Problem(409, "/problems/no-certificate", "Issue the recovery certificate first: the 8F notice recovers its arrears")
        row = dict(row)
        await coercion_allowed(session, row, "GARNISHEE_8F")
        paid = min(body.amount_paise if body.paid_paise is None else body.paid_paise, body.amount_paise)
        await act(session, row["recovery_case_id"], "GARNISHEE_8F", actor.subject, {**body.model_dump(), "paid_paise": paid,
                  "copy_to_employer": True, "section": "8F(3)"})
        if paid:
            row = await realise(session, actor, row, paid, "GARNISHEE_8F", f"8F-{body.reference}")
        await record(session, actor, "recovery.garnishee_8f", "recovery_case", row["recovery_case_id"], f"{body.garnishee} {body.name}")
        result = await view(session, row)
    return envelope(result)


# ── attachment and sale, receiver, arrest (records only) ──────────────────────────────────────────────────────────────
class AttachmentInput(BaseModel):
    kind: Literal["MOVABLE", "IMMOVABLE", "DEBTS_SHARES"]
    description: str = Field(min_length=3)
    value_paise: int = Field(gt=0)
    urgent_reason: str | None = None


@router.post(RECOVERY + "/{case_id}/attachments", status_code=201)
async def attach(case_id: str, body: AttachmentInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")),
                 session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        require_step_up(actor, "attach-property", case_id)
        await coercion_allowed(session, row, "ATTACHMENT", body.urgent_reason)
        attachment_id = f"ATT-{secrets.token_hex(3).upper()}"
        await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id).values(state="IN_EXECUTION"))
        await act(session, case_id, "ATTACHMENT", actor.subject, {"attachment_id": attachment_id, **body.model_dump(), "form": "EPFCP attachment order"})
        await record(session, actor, "recovery.attachment", "recovery_case", case_id, f"{body.kind} {body.description}")
        result = await view(session, {**row, "state": "IN_EXECUTION"})
    return envelope(result)


class SaleInput(BaseModel):
    attachment_id: str
    reserve_price_paise: int = Field(gt=0)
    sale_price_paise: int = Field(gt=0)
    buyer: str = Field(min_length=2)
    mode: Literal["E_AUCTION", "PUBLIC_AUCTION"] = "E_AUCTION"


@router.post(RECOVERY + "/{case_id}/sales", status_code=201)
async def sell(case_id: str, body: SaleInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")), session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        require_step_up(actor, "sell-property", case_id, None, body.sale_price_paise)
        await coercion_allowed(session, row, "SALE", "sale of property already attached")
        past = await actions_of(session, case_id)
        if not any(a["kind"] == "ATTACHMENT" and a["detail"]["attachment_id"] == body.attachment_id for a in past):
            raise Problem(404, "/problems/not-found", "No such attachment on this certificate")
        if any(a["kind"] == "SALE" and a["detail"]["attachment_id"] == body.attachment_id for a in past):
            raise Problem(409, "/problems/sold", "That property is already sold")
        if body.sale_price_paise < body.reserve_price_paise:
            raise Problem(422, "/problems/validation", "Not below the reserve price")
        await act(session, case_id, "SALE", actor.subject, body.model_dump())
        surplus = max(0, body.sale_price_paise - (int(row["amount_paise"]) - int(row["realised_paise"])))
        row = await realise(session, actor, row, body.sale_price_paise, "SALE", f"SALE-{body.attachment_id}")
        await record(session, actor, "recovery.sale", "recovery_case", case_id, f"{body.attachment_id} {body.sale_price_paise}")
        result = {**await view(session, row), "surplus_to_defaulter_paise": surplus}
    return envelope(result)


class ReceiverInput(BaseModel):
    over: Literal["BUSINESS", "IMMOVABLE"]
    receiver: str = Field(min_length=2)
    note: str = Field(min_length=1)


@router.post(RECOVERY + "/{case_id}/receivers", status_code=201)
async def receiver(case_id: str, body: ReceiverInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")),
                   session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        require_step_up(actor, "appoint-receiver", case_id)
        await coercion_allowed(session, row, "RECEIVER")
        await session.execute(update(recovery_cases).where(recovery_cases.c.recovery_case_id == case_id).values(state="IN_EXECUTION"))
        await act(session, case_id, "RECEIVER", actor.subject, body.model_dump())
        await record(session, actor, "recovery.receiver", "recovery_case", case_id, body.receiver)
        result = await view(session, {**row, "state": "IN_EXECUTION"})
    return envelope(result)


class ArrestInput(BaseModel):
    step: Literal["SHOW_CAUSE", "WARRANT", "DETENTION_ORDER", "RELEASED"]
    hearing_on: str | None = None
    ground: Literal["NON_APPEARANCE", "LIKELY_TO_ABSCOND", "DISHONEST_TRANSFER", "MEANS_BUT_REFUSES", "PAID", "SECURITY", "PERIOD_OVER"] | None = None
    reasons: str = Field(min_length=1)

    @model_validator(mode="after")
    def fits(self):
        allowed = {"SHOW_CAUSE": {None}, "WARRANT": {"NON_APPEARANCE", "LIKELY_TO_ABSCOND"},
                   "DETENTION_ORDER": {"DISHONEST_TRANSFER", "MEANS_BUT_REFUSES"}, "RELEASED": {"PAID", "SECURITY", "PERIOD_OVER"}}[self.step]
        if self.ground not in allowed or (self.step == "SHOW_CAUSE" and not self.hearing_on):
            raise ValueError(f"{self.step} takes {sorted(g for g in allowed if g) or 'a hearing date'}")
        return self


@router.post(RECOVERY + "/{case_id}/arrest-warrants", status_code=201)
async def arrest(case_id: str, body: ArrestInput, actor: Actor = Depends(require_stakeholder("fo.recovery_officer")),
                 session: AsyncSession = Depends(db)):
    async with session.begin():
        row = await officer_case(session, case_id, actor)
        require_step_up(actor, "arrest-defaulter", case_id)
        if body.step != "RELEASED":
            await coercion_allowed(session, row, "ARREST")
        steps = [a["detail"]["step"] for a in await actions_of(session, case_id) if a["kind"] == "ARREST"]
        # no detention without a show-cause notice and a hearing; a warrant for not appearing needs the notice (Recovery Manual 6.1-6.3)
        if body.step == "DETENTION_ORDER" and "SHOW_CAUSE" not in steps:
            raise Problem(422, "/problems/show-cause-first", "Notice to show cause (EPFCP-25) and a hearing come before a detention order")
        if body.step == "WARRANT" and body.ground == "NON_APPEARANCE" and "SHOW_CAUSE" not in steps:
            raise Problem(422, "/problems/show-cause-first", "A warrant for not appearing follows a notice to show cause")
        if body.step == "RELEASED" and not ({"WARRANT", "DETENTION_ORDER"} & set(steps)):
            raise Problem(409, "/problems/invalid-state", "Nobody is in custody")
        await act(session, case_id, "ARREST", actor.subject, body.model_dump())
        await record(session, actor, "recovery.arrest_" + body.step.lower(), "recovery_case", case_id, body.reasons)
        await event(session, actor, "RecoveryStepTaken.v1", "recovery_case", case_id,
                    {"recovery_case_id": case_id, "establishment_id": row["establishment_id"], "step": f"ARREST_{body.step}"})
        result = await view(session, row)
    return envelope(result)


@router.get("/api/v1/employers/me/recovery-cases")
async def my_recovery(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory")), session: AsyncSession = Depends(db)):
    rows = (await session.execute(select(recovery_cases).where(recovery_cases.c.establishment_id == (actor.establishment_id or ""))
                                  .order_by(recovery_cases.c.issued_at.desc()))).mappings().all()
    out = []
    for r in rows:
        v = await view(session, dict(r))
        v.pop("recovery_officer", None)
        v.pop("issued_by", None)
        out.append(v)
    return envelope(out)


# ── HO reports ────────────────────────────────────────────────────────────────────────────────────────────────────────
@router.get("/api/v1/ho/reports/proceedings")
async def proceedings_report(actor: Actor = Depends(require_stakeholder("ho.compliance", "zo.acc")), session: AsyncSession = Depends(db)):
    rows = (await session.execute(select(inquiries))).mappings().all()
    names = dict((await session.execute(select(establishments.c.establishment_id, establishments.c.legal_name))).all())
    pending = [r for r in rows if r["state"] not in ("ORDERED", "CLOSED_ON_APPEAL")]
    overdue = [r for r in pending if r["order_due_at"] and now() > dt(r["order_due_at"])]
    month = now().strftime("%Y-%m")
    disposed = [r for r in rows if r["ordered_at"] and dt(r["ordered_at"]).strftime("%Y-%m") == month]
    days = [(dt(r["ordered_at"]) - dt(r["registered_at"])).days for r in rows if r["ordered_at"]]
    by_section = defaultdict(Counter)
    for r in rows:
        by_section[r["section"] or "7A"][r["state"]] += 1
    by_office = Counter(r["office_id"] for r in pending)
    appeals = (await session.execute(select(legal_cases.c.kind, legal_cases.c.state))).all()
    return envelope({"as_of": now().isoformat(), "inquiries": len(rows), "pending": len(pending), "disposed_this_month": len(disposed),
                     "average_days_to_order": round(sum(days) / len(days), 1) if days else None,
                     "by_section": {k: dict(v) for k, v in sorted(by_section.items())}, "pending_by_office": dict(by_office),
                     "orders_overdue": [{"case_id": r["case_id"], "diary_no": r["diary_no"], "establishment": names.get(r["establishment_id"], r["establishment_id"]),
                                         "officer_rank": r["officer_rank"], "order_due_at": iso(r["order_due_at"])} for r in overdue],
                     "legal_cases": dict(Counter(f"{k} {s}" for k, s in appeals))})


@router.get("/api/v1/ho/reports/recovery")
async def recovery_report(actor: Actor = Depends(require_stakeholder("ho.recovery", "ho.compliance")), session: AsyncSession = Depends(db)):
    rows = [dict(r) for r in (await session.execute(select(recovery_cases))).mappings().all()]
    acts = (await session.execute(select(recovery_actions).where(recovery_actions.c.kind == "REALISATION"))).mappings().all()
    by_mode = Counter()
    for a in acts:
        by_mode[a["detail"]["mode"]] += int(a["detail"]["amount_paise"])
    views = [await view(session, r) for r in rows]
    open_ = [v for v in views if v["state"] != "CLOSED"]
    old = [v for v in open_ if now() - dt(v["issued_at"]) > timedelta(days=365)]
    return envelope({"as_of": now().isoformat(), "certificates": len(rows), "open": len(open_),
                     "certified_paise": sum(int(r["amount_paise"]) for r in rows), "realised_paise": sum(int(r["realised_paise"]) for r in rows),
                     "outstanding_paise": sum(v["outstanding_paise"] for v in open_), "realised_by_mode_paise": dict(by_mode),
                     "stayed_paise": sum(v["outstanding_paise"] for v in open_ if v["stayed"]),
                     "in_instalments": sum(1 for v in open_ if v["state"] == "INSTALMENTS"),
                     "older_than_a_year": len(old), "by_state": dict(Counter(v["state"] for v in views))})
