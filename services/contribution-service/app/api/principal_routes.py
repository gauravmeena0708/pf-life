"""Contractor ECR rows attributed to a principal employer (illustrative)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from app.api.routes import _establishment, _fetch_filing
from app.domain.ecr import parse
from app.infra.db import sessions
from epfo_auth import Actor, require_grant, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
CONTRACTOR = require_stakeholder("employer.operator", "employer.signatory")
TAGGABLE = {"SUBMITTED", "PAYMENT_PENDING", "PAYMENT_FAILED", "PAYMENT_CONFIRMED", "POSTED"}


class PrincipalTagInput(BaseModel):
    principal_establishment_id: str = Field(min_length=1, max_length=80)
    work_order_ref: str = Field(min_length=1, max_length=120)
    uans: list[str] = Field(min_length=1, max_length=10000)


@router.post("/api/v1/employers/me/ecr-filings/{filingId}/principal-employer-tags", status_code=201)
async def tag_principal(filingId: str, body: PrincipalTagInput, actor: Actor = Depends(CONTRACTOR)) -> dict:
    require_grant(actor, "ecr.prepare")
    eid = _establishment(actor)
    uans = list(dict.fromkeys(body.uans))
    async with sessions()() as session, session.begin():
        f = await _fetch_filing(session, filingId, eid)
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT id FROM ecr_filings WHERE id=:f FOR UPDATE"), {"f": filingId})
        if f["state"] not in TAGGABLE:
            raise Problem(409, "/problems/invalid-state", "Filing must be submitted before members can be tagged")
        rows = {r["UAN"]: r for r in parse(f["content"], f["format"])[0]}
        missing = [uan for uan in uans if uan not in rows]
        if missing:
            raise Problem(422, "/problems/validation", "UANs are not in this filing", ", ".join(missing))
        existing = (await session.execute(text("SELECT uan, principal_establishment_id, work_order_ref "
                                               "FROM principal_employer_tags WHERE filing_id=:f AND uan IN :u").bindparams(
                                                   bindparam("u", expanding=True)), {"f": filingId, "u": uans})).mappings().all()
        conflicts = [r["uan"] for r in existing if r["principal_establishment_id"] != body.principal_establishment_id]
        if conflicts:
            raise Problem(409, "/problems/principal-tag-conflict", "UANs are already tagged to another principal", ", ".join(conflicts))
        changed = [uan for uan in uans if uan not in {r["uan"] for r in existing}]
        if any(r["work_order_ref"] != body.work_order_ref for r in existing):
            raise Problem(409, "/problems/principal-tag-conflict", "UANs are already tagged to another work order")
        for uan in changed:
            row = rows[uan]
            wages = int(row["EPF Wages"]) * 100
            amount = sum(int(row[field]) for field in ("EPF Contribution (EE share)", "EPF-EPS Difference (ER share)",
                                                      "EPS Contribution")) * 100
            await session.execute(text("INSERT INTO principal_employer_tags "
                                       "(filing_id, uan, principal_establishment_id, work_order_ref, epf_wages_paise, contribution_paise) "
                                       "VALUES (:f,:u,:p,:w,:e,:c)"),
                                  {"f": filingId, "u": uan, "p": body.principal_establishment_id,
                                   "w": body.work_order_ref, "e": wages, "c": amount})
        totals = (await session.execute(text("SELECT COUNT(*) AS members, SUM(epf_wages_paise) AS epf_wages_paise, "
                                             "SUM(contribution_paise) AS contribution_paise FROM principal_employer_tags "
                                             "WHERE filing_id=:f AND principal_establishment_id=:p AND work_order_ref=:w"),
                                        {"f": filingId, "p": body.principal_establishment_id,
                                         "w": body.work_order_ref})).mappings().one()
        challan = (await session.execute(text("SELECT status FROM challans WHERE filing_id=:f"), {"f": filingId})).scalar_one_or_none()
        result = {"filing_id": filingId, "wage_month": f["wage_month"], "contractor_establishment_id": eid,
                  "principal_establishment_id": body.principal_establishment_id, "work_order_ref": body.work_order_ref,
                  "members": int(totals["members"]), "epf_wages_paise": int(totals["epf_wages_paise"] or 0),   # Postgres SUM is a Decimal
                  "contribution_paise": int(totals["contribution_paise"] or 0),
                  "paid": challan == "PAID"}
        if changed:
            await add_event(session, producer="contribution-service", event_type="PrincipalEmployerTagged.v1",
                            aggregate_type="ecr_filing", aggregate_id=filingId, payload=result,
                            correlation_id=actor.correlation_id)
            await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                        action="ecr.principal_employer_tagged", target_type="ecr_filing", target_id=filingId,
                        detail=f"{body.principal_establishment_id}; {body.work_order_ref}; {len(changed)} members")
    return envelope(result)
