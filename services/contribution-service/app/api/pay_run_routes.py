"""Pay run routes for payroll provider B2B integration (P2.22)."""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes import EMPLOYER, OPEN_DRAFT, FilingInput, _create, _establishment, _members
from app.domain.pay_runs import check_rows, ecr_lines
from app.infra.db import sessions
from epfo_auth import Actor, require_grant, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit
from epfo_persistence.policy import rules_for_wage_month

router = APIRouter()

PAYROLL_PROVIDER = require_stakeholder("payroll_provider")


class PayRunRowInput(BaseModel):
    uan: str
    name: str
    gross_wages_paise: int = Field(ge=0)
    epf_wages_paise: int = Field(ge=0)
    eps_wages_paise: int = Field(ge=0)
    edli_wages_paise: int = Field(ge=0)
    ncp_days: int = Field(ge=0)


class PayRunInput(BaseModel):
    wage_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    run_ref: str = Field(min_length=3, max_length=60)
    pay_date: date
    rows: list[PayRunRowInput] = Field(min_length=1, max_length=1000)


def _pay_run_json(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "pay_run_id": d["pay_run_id"],
        "wage_month": d["wage_month"],
        "run_ref": d["run_ref"],
        "pay_date": d["pay_date"].isoformat() if hasattr(d["pay_date"], "isoformat") else str(d["pay_date"]),
        "state": d["state"],
        "rows": d["rows"] if isinstance(d["rows"], list) else json.loads(d["rows"]),
        "issues": d["issues"] if isinstance(d["issues"], list) else json.loads(d["issues"]),
        "totals": d["totals"] if isinstance(d["totals"], dict) else json.loads(d["totals"]),
    }


def _pay_run_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "pay_run_id": d["pay_run_id"],
        "wage_month": d["wage_month"],
        "run_ref": d["run_ref"],
        "pay_date": d["pay_date"].isoformat() if hasattr(d["pay_date"], "isoformat") else str(d["pay_date"]),
        "state": d["state"],
        "totals": d["totals"] if isinstance(d["totals"], dict) else json.loads(d["totals"]),
        "filing_id": d.get("filing_id"),
    }


@router.post("/api/v1/partners/payroll/pay-runs", status_code=201)
async def submit_pay_run(body: PayRunInput, actor: Actor = Depends(PAYROLL_PROVIDER)):
    require_grant(actor, "payroll.submit")
    eid = _establishment(actor)

    async with sessions()() as session, session.begin():
        existing = (await session.execute(
            text("SELECT * FROM pay_runs WHERE establishment_id=:e AND run_ref=:ref"),
            {"e": eid, "ref": body.run_ref}
        )).mappings().first()
        if existing:
            return JSONResponse(status_code=200, content=envelope(_pay_run_json(dict(existing))))

        est = (await session.execute(
            text("SELECT status, last_wage_month FROM establishments WHERE id=:e"),
            {"e": eid}
        )).mappings().first()
        if not est or est["status"] != "VERIFIED":
            raise Problem(409, "/problems/establishment-not-verified", "Establishment is not verified")
        if est["last_wage_month"] and body.wage_month > est["last_wage_month"]:
            raise Problem(409, "/problems/establishment-closed", "Establishment is closed",
                          f"The last permitted wage month is {est['last_wage_month']}.")

        regular_posted = (await session.execute(
            text("SELECT id FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m AND filing_type='REGULAR' AND state='POSTED'"),
            {"e": eid, "m": body.wage_month}
        )).first() is not None

        members = await _members(session, eid)
        rules = await rules_for_wage_month(session, body.wage_month)

    row_dicts = [r.model_dump() for r in body.rows]
    issues = check_rows(row_dicts, body.wage_month, members, rules, regular_posted=regular_posted)
    if any(i["severity"] == "error" for i in issues):
        raise Problem(422, "/problems/pay-run-invalid", "Pay run invalid", "Issues found in pay run rows.", issues=issues)

    gross_paise = sum(r["gross_wages_paise"] for r in row_dicts)
    epf_wages_paise = sum(r["epf_wages_paise"] for r in row_dicts)
    totals = {
        "gross_paise": gross_paise,
        "epf_wages_paise": epf_wages_paise,
        "rows": len(row_dicts),
    }
    pid = f"PR-{uuid.uuid4().hex[:16]}"

    async with sessions()() as session, session.begin():
        await session.execute(
            text("INSERT INTO pay_runs (pay_run_id, establishment_id, provider_subject, wage_month, run_ref, pay_date, rows, issues, totals, state, created_at) "
                 "VALUES (:pid, :e, :p, :m, :ref, :pd, :rows, :issues, :totals, 'ACCEPTED', CURRENT_TIMESTAMP)"),
            {
                "pid": pid,
                "e": eid,
                "p": actor.subject,
                "m": body.wage_month,
                "ref": body.run_ref,
                "pd": body.pay_date,
                "rows": json.dumps(row_dicts),
                "issues": json.dumps(issues),
                "totals": json.dumps(totals),
            }
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pay_run.create",
                    target_type="pay_run", target_id=pid, detail=f"run_ref={body.run_ref}; wage_month={body.wage_month}; rows={len(row_dicts)}")

    data = {
        "pay_run_id": pid,
        "wage_month": body.wage_month,
        "run_ref": body.run_ref,
        "pay_date": body.pay_date.isoformat(),
        "state": "ACCEPTED",
        "rows": row_dicts,
        "issues": issues,
        "totals": totals,
    }
    return JSONResponse(status_code=201, content=envelope(data))


@router.post("/api/v1/partners/sandbox/payroll/pay-runs/validations")
async def validate_pay_run_sandbox(body: PayRunInput, actor: Actor = Depends(PAYROLL_PROVIDER)):
    require_grant(actor, "payroll.submit")
    eid = _establishment(actor)

    async with sessions()() as session, session.begin():
        regular_posted = (await session.execute(
            text("SELECT id FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m AND filing_type='REGULAR' AND state='POSTED'"),
            {"e": eid, "m": body.wage_month}
        )).first() is not None
        members = await _members(session, eid)
        rules = await rules_for_wage_month(session, body.wage_month)

    row_dicts = [r.model_dump() for r in body.rows]
    issues = check_rows(row_dicts, body.wage_month, members, rules, regular_posted=regular_posted)
    valid = not any(i["severity"] == "error" for i in issues)
    return envelope({"valid": valid, "issues": issues})


@router.get("/api/v1/partners/payroll/pay-runs")
async def list_provider_pay_runs(wage_month: str | None = Query(None), actor: Actor = Depends(PAYROLL_PROVIDER)):
    require_grant(actor, "payroll.submit")
    eid = _establishment(actor)

    async with sessions()() as session, session.begin():
        sql = "SELECT pay_run_id, wage_month, run_ref, pay_date, state, totals, filing_id FROM pay_runs WHERE establishment_id=:e"
        params: dict[str, Any] = {"e": eid}
        if wage_month:
            sql += " AND wage_month=:m"
            params["m"] = wage_month
        sql += " ORDER BY created_at ASC"
        rows = (await session.execute(text(sql), params)).mappings().all()

    items = [_pay_run_summary(dict(r)) for r in rows]
    return envelope(items)


@router.get("/api/v1/employers/me/pay-runs")
async def get_employer_pay_runs(wage_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), actor: Actor = Depends(EMPLOYER)):
    require_grant(actor, "ecr.prepare")
    eid = _establishment(actor)

    async with sessions()() as session, session.begin():
        rows = (await session.execute(
            text("SELECT pay_run_id, wage_month, run_ref, pay_date, state, totals, filing_id, rows FROM pay_runs WHERE establishment_id=:e AND wage_month=:m ORDER BY created_at ASC"),
            {"e": eid, "m": wage_month}
        )).mappings().all()

        regular_filings = (await session.execute(
            text("SELECT state FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m AND filing_type='REGULAR'"),
            {"e": eid, "m": wage_month}
        )).mappings().all()

    run_summaries = [_pay_run_summary(dict(r)) for r in rows]

    member_map: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["state"] not in ("ACCEPTED", "INCLUDED"):
            continue
        r_rows = r["rows"] if isinstance(r["rows"], list) else json.loads(r["rows"])
        for item in r_rows:
            uan = str(item["uan"])
            if uan not in member_map:
                member_map[uan] = {
                    "uan": uan,
                    "name": item.get("name", ""),
                    "runs": 0,
                    "gross_paise": 0,
                    "epf_wages_paise": 0,
                    "eps_wages_paise": 0,
                    "edli_wages_paise": 0,
                    "ncp_days": 0,
                }
            m_entry = member_map[uan]
            m_entry["runs"] += 1
            m_entry["gross_paise"] += item.get("gross_wages_paise", 0)
            m_entry["epf_wages_paise"] += item.get("epf_wages_paise", 0)
            m_entry["eps_wages_paise"] += item.get("eps_wages_paise", 0)
            m_entry["edli_wages_paise"] += item.get("edli_wages_paise", 0)
            m_entry["ncp_days"] += item.get("ncp_days", 0)

    members_list = sorted(member_map.values(), key=lambda x: x["uan"])

    has_accepted = any(r["state"] == "ACCEPTED" for r in rows)
    regular_submitted = any(x["state"] not in OPEN_DRAFT + ("SUPERSEDED", "CANCELLED", "REJECTED") for x in regular_filings)

    if not has_accepted:
        can_make_ecr = False
        reason = "No accepted pay runs for this wage month"
    elif regular_submitted:
        can_make_ecr = False
        reason = "A regular return for this wage month has already been submitted"
    else:
        can_make_ecr = True
        reason = None

    data: dict[str, Any] = {
        "wage_month": wage_month,
        "runs": run_summaries,
        "members": members_list,
        "can_make_ecr": can_make_ecr,
    }
    if reason:
        data["reason"] = reason

    return envelope(data)


@router.post("/api/v1/employers/me/pay-runs/{wageMonth}/ecr-drafts", status_code=201)
async def draft_ecr_from_pay_runs(wageMonth: str, actor: Actor = Depends(EMPLOYER)):
    require_grant(actor, "ecr.prepare")
    eid = _establishment(actor)

    async with sessions()() as session, session.begin():
        est = (await session.execute(
            text("SELECT status, last_wage_month FROM establishments WHERE id=:e"),
            {"e": eid}
        )).mappings().first()
        if not est or est["status"] != "VERIFIED":
            raise Problem(409, "/problems/establishment-not-verified", "Establishment is not verified")
        if est["last_wage_month"] and wageMonth > est["last_wage_month"]:
            raise Problem(409, "/problems/establishment-closed", "Establishment is closed",
                          f"The last permitted wage month is {est['last_wage_month']}.")

        regular_filings = (await session.execute(
            text("SELECT state FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m AND filing_type='REGULAR'"),
            {"e": eid, "m": wageMonth}
        )).mappings().all()
        if any(x["state"] not in OPEN_DRAFT + ("SUPERSEDED", "CANCELLED", "REJECTED") for x in regular_filings):
            raise Problem(409, "/problems/wage-month-already-filed", "Wage month already filed", "Use a supplementary return.")

        accepted_rows = (await session.execute(
            text("SELECT * FROM pay_runs WHERE establishment_id=:e AND wage_month=:m AND state='ACCEPTED' ORDER BY created_at ASC"),
            {"e": eid, "m": wageMonth}
        )).mappings().all()

        if not accepted_rows:
            raise Problem(409, "/problems/no-accepted-pay-runs", "No accepted pay runs", "There are no accepted pay runs for this wage month to draft an ECR.")

        members = await _members(session, eid)
        rules = await rules_for_wage_month(session, wageMonth)

    run_list = []
    for r in accepted_rows:
        d = dict(r)
        if isinstance(d["rows"], str):
            d["rows"] = json.loads(d["rows"])
        run_list.append(d)

    ecr_content = ecr_lines(run_list, members=members, rules=rules)
    filing_input = FilingInput(wage_month=wageMonth, type="REGULAR", format="ECR_TXT", content=ecr_content)
    result = await _create(filing_input, actor)
    filing_id = result["filing"]["filing_id"]

    async with sessions()() as session, session.begin():
        await session.execute(
            text("UPDATE pay_runs SET state='INCLUDED', filing_id=:fid WHERE establishment_id=:e AND wage_month=:m AND state='ACCEPTED'"),
            {"fid": filing_id, "e": eid, "m": wageMonth}
        )
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="pay_run.draft_ecr",
                    target_type="ecr_filing", target_id=filing_id, detail=f"wage_month={wageMonth}; filing_id={filing_id}; runs={len(run_list)}")

    return JSONResponse(status_code=201, content=envelope(result))
