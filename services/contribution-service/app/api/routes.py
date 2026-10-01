"""Contribution filing, challan, passbook and public demo calculator APIs."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.domain.ecr import FIELDS, parse, split, validate
from app.infra.db import sessions
from epfo_auth import Actor, require_actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response
from app.infra.interest import interest_due, post_interest
from epfo_persistence.policy import financial_year, financial_year_bounds, interest_rate_bp, rules_on

router = APIRouter()


def wage_month_start(wage_month: str) -> date:
    return date.fromisoformat(wage_month + "-01")


class FilingInput(BaseModel):
    wage_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    type: str = "REGULAR"
    format: str
    content: str


class ApprovalInput(BaseModel):
    decision: str
    reason: str | None = None


class CalculatorInput(BaseModel):
    epf_wages_paise: int = Field(ge=0)
    eps_wages_paise: int = Field(ge=0)
    age_years: int = Field(ge=0, le=130)


class PublicTrrnLookup(BaseModel):
    trrn: str = Field(pattern=r"^TRRN[0-9]{13}$")
    challenge_id: str = Field(min_length=20, max_length=64)
    answer: int = Field(ge=0, le=99)


EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")
MEMBER = require_stakeholder("member")
FINANCE = require_stakeholder("ho.fa_cao")


def _establishment(actor: Actor) -> str:
    if not actor.establishment_id:
        raise Problem(403, "/problems/forbidden", "Not allowed", "No establishment is bound to this actor.")
    return actor.establishment_id


async def _fetch_filing(session, filing_id: str, establishment_id: str):
    r = await session.execute(text("SELECT * FROM ecr_filings WHERE id=:id AND establishment_id=:e"), {"id": filing_id, "e": establishment_id})
    row = r.mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Not found", "Filing not found.")
    return dict(row)


async def _members(session, establishment_id: str):
    r = await session.execute(text("SELECT * FROM establishment_members WHERE establishment_id=:e"), {"e": establishment_id})
    return [dict(x) for x in r.mappings().all()]


async def _validation(session, filing: dict[str, Any]):
    members = await _members(session, filing["establishment_id"])
    prior = (await session.execute(text("SELECT wage_month,validation_report FROM ecr_filings WHERE establishment_id=:e AND state='POSTED' AND wage_month<:m ORDER BY wage_month DESC LIMIT 1"), {"e":filing["establishment_id"],"m":filing["wage_month"]})).mappings().first()
    comparison = None
    if prior:
        old = prior["validation_report"] if isinstance(prior["validation_report"], dict) else json.loads(prior["validation_report"])
        comparison = {"wage_month":prior["wage_month"],"members_then":old["summary"]["rows"],"total_then_paise":old["summary"]["totals_paise"]["TOTAL"],"total_now_paise":0}
    # A return is checked against the rules in force on the first day of its wage month; until it is
    # submitted, re-validating picks up a newly published version for that month.
    rules = await rules_on(session, wage_month_start(filing["wage_month"]))
    report = validate(filing["content"], filing["format"], filing["wage_month"], members, rules, comparison)
    report.update({"filing_id": filing["id"], "version": filing["version"],
                   "state": "VALIDATED" if report["valid"] else "VALIDATION_FAILED",
                   "rule_version": rules["rule_version"]})
    return report


async def _create(body: FilingInput, actor: Actor):
    require_grant(actor, "ecr.prepare")
    eid = _establishment(actor)
    if body.format not in ("ECR_TXT", "CSV"):
        raise Problem(400, "/problems/invalid-ecr-format", "Unsupported ECR format")
    if body.type not in ("REGULAR", "ARREAR", "SUPPLEMENTARY"):
        raise Problem(400, "/problems/invalid-ecr-type", "The return type must be REGULAR, ARREAR or SUPPLEMENTARY")
    async with sessions()() as session, session.begin():
        est = (await session.execute(text("SELECT status FROM establishments WHERE id=:e"), {"e": eid})).scalar_one_or_none()
        if est != "VERIFIED":
            raise Problem(409, "/problems/establishment-not-verified", "Establishment is not verified")
        prior_rows = (await session.execute(text("SELECT * FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m ORDER BY version DESC"), {"e": eid, "m": body.wage_month})).mappings().all()
        regular = [x for x in prior_rows if x["filing_type"] == "REGULAR"]
        if body.type == "REGULAR":
            if any(x["state"] not in OPEN_DRAFT + ("SUPERSEDED", "CANCELLED", "REJECTED") for x in regular):
                raise Problem(409, "/problems/wage-month-already-filed", "Wage month already filed", "Use a supplementary return.", fix="use a supplementary return")
        elif not any(x["state"] == "POSTED" for x in regular):
            raise Problem(409, "/problems/regular-return-not-posted", f"File and pay the regular return for {body.wage_month} first",
                          f"An {body.type.lower()} return adds to a posted regular return of the same wage month.")
        for old in prior_rows:                                   # an unsubmitted draft of the same type is replaced
            if old["filing_type"] == body.type and old["state"] in OPEN_DRAFT:
                await session.execute(text("UPDATE ecr_filings SET state='SUPERSEDED' WHERE id=:id"), {"id": old["id"]})
        ver = (max((x["version"] for x in prior_rows), default=0) + 1)
        fid = str(uuid.uuid4()); rv = (await rules_on(session, wage_month_start(body.wage_month)))["rule_version"]
        await session.execute(text("INSERT INTO ecr_filings (id, establishment_id, wage_month, filing_type, format, content, version, state, preparer_subject, rule_version) VALUES (:id,:e,:m,:t,:f,:c,:v,'DRAFT',:p,:r)"),
                              {"id": fid, "e": eid, "m": body.wage_month, "t": body.type, "f": body.format, "c": body.content, "v": ver, "p": actor.subject, "r": rv})
        filing = await _fetch_filing(session, fid, eid)
        report = await _validation(session, filing)
        if body.type != "REGULAR":
            report = await _check_additional_return(session, filing, report)
        state = report["state"]
        await session.execute(text("UPDATE ecr_filings SET state=:s, validation_report=:r, rule_version=:v WHERE id=:id"), {"s": state, "r": json.dumps(report, default=str), "v": report["rule_version"], "id": fid})
        if report["valid"]:
            await add_event(session, producer="contribution-service", event_type="ECRValidated.v1", aggregate_type="ecr_filing", aggregate_id=fid,
                            payload={"filing_id":fid,"establishment_id":eid,"wage_month":body.wage_month,"member_count":report["summary"]["rows"]}, correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.create", target_type="ecr_filing", target_id=fid, detail=f"version={ver}; rule_version={rv}")
        filing["state"] = state
        return {"filing": _filing_json(filing), "validation_report": report}


OPEN_DRAFT = ("DRAFT", "VALIDATION_FAILED", "VALIDATED")


async def _check_additional_return(session, filing: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """A supplementary return adds members missed in the posted returns of the month; an arrear return pays
    wage-revision arrears for members already in them. Warnings about the whole workforce do not apply."""
    posted = (await session.execute(text("SELECT content, format FROM ecr_filings WHERE establishment_id=:e AND wage_month=:m AND state='POSTED'"),
                                    {"e": filing["establishment_id"], "m": filing["wage_month"]})).mappings().all()
    already = {row["UAN"] for f in posted for row in parse(f["content"], f["format"])[0]}
    issues = [x for x in report["issues"] if x["code"] not in ("W-MISSING-MEMBER", "W-HEADCOUNT-CHANGE")]
    for i, row in enumerate(parse(filing["content"], filing["format"])[0], 1):
        uan = row.get("UAN", "")
        if filing["filing_type"] == "SUPPLEMENTARY" and uan in already:
            issues.append({"row": i, "uan_masked": "*" * 8 + uan[-4:], "field": "UAN", "code": "E-SUPP-ALREADY-FILED", "severity": "error",
                           "message": "This member is already in a posted return for the wage month.", "expected": None, "actual": None,
                           "fix": "Leave the member out, or file an arrear return for a wage revision.", "auto_fixable": False})
        if filing["filing_type"] == "ARREAR" and uan not in already:
            issues.append({"row": i, "uan_masked": "*" * 8 + uan[-4:], "field": "UAN", "code": "E-ARREAR-NOT-FILED", "severity": "error",
                           "message": "Arrears are paid only for a member in a posted return of the wage month.", "expected": None, "actual": None,
                           "fix": "File a supplementary return for a member who was missed.", "auto_fixable": False})
    errors = sum(x["severity"] == "error" for x in issues)
    report = {**report, "issues": issues, "valid": errors == 0, "state": "VALIDATED" if errors == 0 else "VALIDATION_FAILED"}
    report["summary"] = {**report["summary"], "warnings": sum(x["severity"] == "warning" for x in issues),
                         "rows_with_errors": len({x["row"] for x in issues if x["severity"] == "error"})}
    return report


def _filing_json(f):
    return {"filing_id": f["id"], "wage_month": f["wage_month"], "type": f["filing_type"], "version": f["version"], "state": f["state"], "rule_version": f["rule_version"], "trrn": f.get("trrn")}


@router.post("/api/v1/employers/me/ecr-filings", status_code=201)
async def create_filing(body: FilingInput, actor: Actor = Depends(EMPLOYER)):
    return envelope(await _create(body, actor))


@router.post("/api/v1/partners/sandbox/payroll/ecr-filings", status_code=201)
async def partner_create(body: FilingInput, actor: Actor = Depends(require_stakeholder("payroll_provider"))):
    return envelope(await _create(body, actor))


@router.post("/api/v1/employers/me/ecr-filings/{filingId}/validations")
async def validate_filing(filingId: str, actor: Actor = Depends(EMPLOYER)):
    require_grant(actor, "ecr.prepare"); eid = _establishment(actor)
    async with sessions()() as session, session.begin():
        f = await _fetch_filing(session, filingId, eid)
        if f["state"] not in ("DRAFT", "VALIDATION_FAILED", "VALIDATED"):
            raise Problem(409, "/problems/invalid-state", "This filing can no longer be validated")
        report = await _validation(session, f)
        if f["filing_type"] != "REGULAR":
            report = await _check_additional_return(session, f, report)
        await session.execute(text("UPDATE ecr_filings SET state=:s, validation_report=:r, rule_version=:v WHERE id=:id"), {"s": report["state"], "r": json.dumps(report, default=str), "v": report["rule_version"], "id": filingId})
        if report["valid"]:
            await add_event(session, producer="contribution-service", event_type="ECRValidated.v1", aggregate_type="ecr_filing", aggregate_id=filingId,
                            payload={"filing_id": filingId, "establishment_id": eid, "wage_month": f["wage_month"], "member_count": report["summary"]["rows"]}, correlation_id=actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.validate", target_type="ecr_filing", target_id=filingId, detail=f"state={report['state']}; rule_version={f['rule_version']}")
        return envelope(report)


async def _not_frozen(session, eid: str) -> None:
    row = (await session.execute(text("SELECT order_ref FROM establishment_freezes WHERE establishment_id=:e"), {"e": eid})).first()
    if row:
        raise Problem(403, "/problems/establishment-frozen", "The establishment is frozen",
                      f"No ECR is approved or submitted while freeze order {row[0] or ''} stands. Contact your regional office.".replace("  ", " "))


@router.post("/api/v1/employers/me/ecr-filings/{filingId}/approvals")
async def approve_filing(filingId: str, body: ApprovalInput, actor: Actor = Depends(EMPLOYER)):
    require_grant(actor, "ecr.approve"); eid = _establishment(actor)
    async with sessions()() as session, session.begin():
        f = await _fetch_filing(session, filingId, eid)
        await _not_frozen(session, eid)
        if f["state"] != "VALIDATED": raise Problem(409, "/problems/invalid-state", "Filing must be validated")
        if f["preparer_subject"] == actor.subject: raise Problem(403, "/problems/self-approval", "Self approval is not allowed")
        report = f["validation_report"] if isinstance(f["validation_report"], dict) else json.loads(f["validation_report"])
        _check_stepup(actor, "approve-ecr", f, report["summary"]["totals_paise"]["TOTAL"])
        if body.decision not in ("APPROVE", "RETURN"): raise Problem(400, "/problems/invalid-decision", "Decision must be APPROVE or RETURN")
        if body.decision == "RETURN" and not body.reason:
            raise Problem(400, "/problems/reason-required", "A reason is required when returning a filing")
        state = "APPROVED" if body.decision == "APPROVE" else "DRAFT"
        await session.execute(text("UPDATE ecr_filings SET state=:s, approver_subject=:a WHERE id=:i"), {"s": state, "a": actor.subject, "i": filingId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"ecr.{body.decision.lower()}", target_type="ecr_filing", target_id=filingId, detail=body.reason)
        return envelope({"filing_id": filingId, "state": state})


def _check_stepup(actor: Actor, action: str, filing: dict[str, Any], amount: int):
    require_step_up(actor, action, filing["id"], filing["version"], amount)


async def _next_trrn(session) -> str:
    if session.bind.dialect.name == "postgresql":
        n = (await session.execute(text("SELECT nextval('trrn_sequence')"))).scalar_one()
    else:  # SQLite in unit tests has no sequences
        n = (await session.execute(text("SELECT COUNT(*) FROM challans"))).scalar_one() + 1
    return f"TRRN{n:013d}"


@router.post("/api/v1/employers/me/ecr-filings/{filingId}/submissions", status_code=201)
async def submit_filing(filingId: str, actor: Actor = Depends(EMPLOYER), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), if_match: str | None = Header(default=None, alias="If-Match")):
    require_grant(actor, "ecr.submit"); eid = _establishment(actor)
    if not idempotency_key: raise Problem(400, "/problems/idempotency-key-required", "Idempotency-Key is required")
    async with sessions()() as session, session.begin():
        bodyhash = request_hash({"filing_id": filingId, "if_match": if_match})
        cached = await find_response(session, actor.subject, "submit-ecr", idempotency_key, bodyhash)
        if cached: return JSONResponse(cached.body, status_code=cached.status)
        f = await _fetch_filing(session, filingId, eid)
        if if_match is None or if_match.strip('"') != str(f["version"]): raise Problem(412, "/problems/version-mismatch", "Filing version does not match If-Match")
        await _not_frozen(session, eid)
        if f["state"] != "APPROVED": raise Problem(409, "/problems/invalid-state", "Filing must be approved before submission")
        report = f["validation_report"] if isinstance(f["validation_report"], dict) else json.loads(f["validation_report"])
        total = report["summary"]["totals_paise"]["TOTAL"]
        _check_stepup(actor, "submit-ecr", f, total)
        trrn = await _next_trrn(session)
        breakdown = report["summary"]["totals_paise"]
        await session.execute(text("INSERT INTO challans (trrn, filing_id, establishment_id, status, total_paise, breakdown) VALUES (:t,:f,:e,'DUE',:a,:b)"), {"t": trrn, "f": filingId, "e": eid, "a": total, "b": json.dumps(breakdown)})
        await session.execute(text("UPDATE ecr_filings SET state='SUBMITTED', trrn=:t WHERE id=:f"), {"t": trrn, "f": filingId})
        await add_event(session, producer="contribution-service", event_type="ECRSubmitted.v1", aggregate_type="ecr_filing", aggregate_id=filingId,
                        payload={"filing_id": filingId, "establishment_id": eid, "trrn": trrn, "total_paise": total, "rule_version": f["rule_version"]}, correlation_id=actor.correlation_id)
        result = envelope({"filing_id": filingId, "state": "SUBMITTED", "trrn": trrn, "total_paise": total, "breakdown_paise": breakdown})
        await store_response(session, actor.subject, "submit-ecr", idempotency_key, bodyhash, 201, result)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.submit", target_type="ecr_filing", target_id=filingId)
        return JSONResponse(result, status_code=201)


@router.get("/api/v1/employers/me/ecr-filings/{filingId}")
async def get_filing(filingId: str, actor: Actor = Depends(EMPLOYER)):
    eid = _establishment(actor)
    async with sessions()() as session:
        f = await _fetch_filing(session, filingId, eid)
        return envelope({**_filing_json(f), "validation_report": f["validation_report"]})


@router.get("/api/v1/employers/me/ecr-filings")
async def list_filings(actor: Actor = Depends(EMPLOYER), wageMonth: str | None = Query(default=None), type: str | None = Query(default=None)):
    eid = _establishment(actor)
    async with sessions()() as session:
        result = await session.execute(text("SELECT * FROM ecr_filings WHERE establishment_id=:e AND (CAST(:m AS TEXT) IS NULL OR wage_month=:m) AND (CAST(:t AS TEXT) IS NULL OR filing_type=:t) ORDER BY wage_month DESC,version DESC"), {"e": eid, "m": wageMonth, "t": type})
        return envelope([_filing_json(dict(x)) for x in result.mappings().all()])


async def _challan(trrn: str, eid: str):
    async with sessions()() as session:
        r = await session.execute(text("SELECT * FROM challans WHERE trrn=:t AND establishment_id=:e"), {"t": trrn, "e": eid})
        row = r.mappings().first()
        if not row: raise Problem(404, "/problems/not-found", "Not found", "Challan not found.")
        return dict(row)


@router.get("/api/v1/employers/me/challans")
async def list_challans(actor: Actor = Depends(EMPLOYER)):
    eid = _establishment(actor)
    async with sessions()() as session:
        r = await session.execute(text("SELECT * FROM challans WHERE establishment_id=:e ORDER BY created_at DESC"), {"e": eid})
        return envelope([dict(x) for x in r.mappings().all()])


@router.get("/api/v1/employers/me/challans/{trrn}")
async def get_challan(trrn: str, actor: Actor = Depends(EMPLOYER)):
    return envelope(await _challan(trrn, _establishment(actor)))


@router.get("/api/v1/employers/me/challans/{trrn}/receipt")
async def challan_receipt(trrn: str, actor: Actor = Depends(EMPLOYER)):
    row = await _challan(trrn, _establishment(actor))
    if row["status"] != "PAID": raise Problem(409, "/problems/challan-not-paid", "Challan is not paid", f"Current status: {row['status']}. Pay the challan and retry for a receipt.", current_status=row["status"], next="Pay the challan")
    return envelope({"trrn": trrn, "status": row["status"], "paid_at": row.get("paid_at"), "total_paise": row["total_paise"]})


@router.post("/api/v1/public/demo-calculations/epf")
async def calculate(body: CalculatorInput, actor: Actor = Depends(require_actor)):  # anonymous callers still pass the gateway
    calc_id = str(uuid.uuid4())
    async with sessions()() as session, session.begin():
        rs = await rules_on(session, date.today())
        out = split(body.epf_wages_paise, body.eps_wages_paise, body.age_years, rs)
        await session.execute(text("INSERT INTO demo_calculations (id,epf_wages_paise,eps_wages_paise,age_years,rule_version,result) VALUES (:id,:epf,:eps,:age,:rv,:result)"),
                              {"id":calc_id,"epf":body.epf_wages_paise,"eps":body.eps_wages_paise,"age":body.age_years,"rv":rs["rule_version"],"result":json.dumps(out)})
    return envelope({**out, "calculation_id":calc_id, "rule_version": rs["rule_version"], "label": "ILLUSTRATIVE_ONLY"})


@router.post("/api/v1/public/trrn-status-lookups")
async def public_trrn_status(body: PublicTrrnLookup, actor: Actor = Depends(require_actor)):
    """Expose only payment state; never disclose employer, member, or amount data."""
    async with sessions()() as session:
        row = (await session.execute(text("""SELECT c.status,c.created_at,c.paid_at,f.wage_month
                                       FROM challans c JOIN ecr_filings f ON f.id=c.filing_id
                                       WHERE c.trrn=:trrn"""),
                                     {"trrn": body.trrn})).mappings().first()
    status = row["status"] if row else "NOT_FOUND"
    next_step = {"DUE": "Awaiting payment", "PAID": "Payment recorded", "FAILED": "Payment failed or returned",
                 "NOT_FOUND": "Check the reference and try again"}.get(status, "Check with the issuing office")
    return envelope({"trrn": body.trrn, "status": status, "wage_month": row["wage_month"] if row else None,
                     "issued_at": row["created_at"].isoformat() if row and row["created_at"] else None,
                     "paid_at": row["paid_at"].isoformat() if row and row["paid_at"] else None,
                     "next_step": next_step, "label": "SYNTHETIC_DEMO"})


@router.get("/api/v1/members/me/passbook")
async def passbook(actor: Actor = Depends(MEMBER)):
    return envelope(await _passbook(actor.subject, None))


@router.get("/api/v1/members/me/accounts/{accountLinkId}/passbook")
async def account_passbook(accountLinkId: str, actor: Actor = Depends(MEMBER)):
    data = await _passbook(actor.subject, accountLinkId)
    if not data["accounts"]: raise Problem(404, "/problems/not-found", "Not found", "Account not found.")
    return envelope(data)


def _month(at) -> str:
    return at.strftime("%Y-%m") if hasattr(at, "strftime") else str(at)[:7]


async def _passbook(subject: str, account_link_id: str | None):
    async with sessions()() as session:
        q = text("SELECT account_link_id, establishment_id FROM establishment_members WHERE member_subject=:s AND (CAST(:a AS TEXT) IS NULL OR account_link_id=:a)")
        accounts = (await session.execute(q, {"s": subject, "a": account_link_id})).mappings().all()
        out=[]; pending=[]
        for a in accounts:
            lines = (await session.execute(text(
                "SELECT j.id AS journal_id, j.kind, j.business_key, j.occurred_at, j.claim_id, f.wage_month, f.trrn, jl.side, jl.amount_paise, jl.share, "
                "ip.financial_year, ip.rate_bp, ip.account_link_id AS interest_account FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id "
                "LEFT JOIN ecr_filings f ON f.id=j.filing_id LEFT JOIN interest_postings ip ON ip.journal_id=j.id "
                "WHERE jl.account_link_id=:a AND jl.account_code='AC01_EPF' ORDER BY j.occurred_at, COALESCE(ip.revision, 0), j.id"),
                {"a": a["account_link_id"]})).mappings().all()
            name = (await session.execute(text("SELECT legal_name FROM establishments WHERE id=:e"),
                                          {"e": a["establishment_id"]})).scalar_one_or_none()
            grouped = {}
            for ln in lines:
                kind = {"CONTRIBUTION": "CONTRIBUTION", "OPENING_BALANCE": "OPENING_BALANCE", "CLAIM_DEBIT": "WITHDRAWAL",
                        "CLAIM_REVERSAL": "WITHDRAWAL_REVERSED", "INTEREST": "INTEREST", "INTEREST_REVISION": "INTEREST",
                        "TRANSFER": "TRANSFER_OUT" if ln["side"] == "debit" else "TRANSFER_IN",
                        "TRANSFER_RECREDIT": "TRANSFER_RECREDITED" if ln["side"] == "credit" else "TRANSFER_RECREDIT_OUT",
                        "REVERSAL": "REVERSAL", "APPENDIX_E": "ADJUSTMENT"}.get(ln["kind"], ln["kind"])
                rate = f"{ln['rate_bp'] / 100:g}%" if ln["rate_bp"] is not None else ""
                ent = grouped.setdefault(ln["journal_id"], {
                    "kind": kind, "wage_month": ln["wage_month"] or _month(ln["occurred_at"]),
                    "description": {"CONTRIBUTION": "Monthly contribution", "OPENING_BALANCE": "Balance brought forward",
                                    "WITHDRAWAL": f"Claim {ln['claim_id']} paid out",
                                    "WITHDRAWAL_REVERSED": f"Claim {ln['claim_id']} not paid: amount returned",
                                    "TRANSFER_OUT": f"Transferred to another member ID (Form 13, {ln['business_key'][9:]})",
                                    "TRANSFER_IN": f"Transferred in from a previous member ID (Form 13, {ln['business_key'][9:]})",
                                    "ADJUSTMENT": "Adjusted by the PF office (Appendix E)",
                                    "REVERSAL": "Entry reversed by the PF office",
                                    "TRANSFER_RECREDITED": "Transfer rejected by the receiving office: balance recredited",
                                    "TRANSFER_RECREDIT_OUT": "Transfer rejected by the receiving office: taken back",
                                    "INTEREST": (f"Interest for {ln['financial_year']} at {rate}" if ln["kind"] == "INTEREST"
                                                 else f"Interest for {ln['financial_year']} revised to {rate}: difference")
                                                + (f" (earned on {ln['interest_account']}, transferred)" if ln["interest_account"] and ln["interest_account"] != a["account_link_id"] else "")}.get(kind, kind),
                    "employee_share_paise": 0, "employer_share_paise": 0, "establishment_name": name,
                    "trrn": ln["trrn"], "claim_id": ln["claim_id"], "posted_at": ln["occurred_at"]})
                if ln["share"] in ("employee", "employer"):
                    ent[f"{ln['share']}_share_paise"] += ln["amount_paise"] if ln["side"] == "credit" else -ln["amount_paise"]
            balance = 0
            entries = []
            for ent in grouped.values():
                balance += ent["employee_share_paise"] + ent["employer_share_paise"]
                entries.append({**ent, "running_balance_paise": balance})
            out.append({"account_link_id": a["account_link_id"], "entries": entries})
        pending_rows=(await session.execute(text("SELECT f.wage_month,f.state,f.content,f.format,c.trrn,m.uan,m.account_link_id FROM ecr_filings f LEFT JOIN challans c ON c.filing_id=f.id JOIN establishment_members m ON m.establishment_id=f.establishment_id WHERE m.member_subject=:s AND (CAST(:a AS TEXT) IS NULL OR m.account_link_id=:a) AND f.state IN ('SUBMITTED','PAYMENT_PENDING')"), {"s":subject,"a":account_link_id})).mappings().all()
        for x in pending_rows:
            members,_,_=parse(x["content"],x["format"])
            if any(m["UAN"] == x["uan"] for m in members):
                pending.append({"account_link_id":x["account_link_id"],"wage_month":x["wage_month"],"trrn":x["trrn"],"status":x["state"],"message":"filed by employer, awaiting payment"})
        return {"accounts":out,"pending":pending}


# ── annual interest crediting (ho.fa_cao; the rate comes from the rule set in force today) ─────────────

class InterestRunInput(BaseModel):
    financial_year: str = Field(pattern=r"^\d{4}-\d{2}$")


def _today() -> date:
    return datetime.now(UTC).date()


async def _interest_plan(session, fy: str) -> dict[str, Any]:
    try:
        _, last_day = financial_year_bounds(fy)
    except ValueError as exc:
        raise Problem(422, "/problems/validation", "Invalid financial year", str(exc)) from exc
    rules = await rules_on(session, _today())
    rate = interest_rate_bp(rules, fy)
    accounts = await interest_due(session, fy, rate) if rate is not None else []
    history = (await session.execute(text(
        "SELECT rule_version, rate_bp, revision, COUNT(*) AS accounts, SUM(employee_paise + employer_paise) AS total_paise, "
        "MAX(posted_at) AS posted_at FROM interest_postings WHERE financial_year = :y GROUP BY rule_version, rate_bp, revision "
        "ORDER BY MAX(posted_at)"), {"y": fy})).mappings().all()
    return {"financial_year": fy, "year_ended": last_day < _today(), "rate_bp": rate, "rule_version": rules["rule_version"],
            "method": "Monthly running balance: the twelve month-end balances x rate / 12, per share, to the nearest rupee.",
            "accounts": [{k: a[k] for k in ("account_link_id", "employee", "employer", "to_credit_paise")} for a in accounts],
            "total_to_credit_paise": sum(a["to_credit_paise"] for a in accounts),
            "history": [{**dict(h), "total_paise": int(h["total_paise"] or 0),
                         "posted_at": h["posted_at"].isoformat() if hasattr(h["posted_at"], "isoformat") else h["posted_at"]} for h in history]}


@router.get("/api/v1/office/accounts/interest-postings")
async def interest_preview(financialYear: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"), actor: Actor = Depends(FINANCE)):
    fy = financialYear or financial_year(_today().replace(year=_today().year - 1, day=1))     # the last completed year
    async with sessions()() as session:
        return envelope(await _interest_plan(session, fy))


@router.post("/api/v1/office/accounts/interest-postings")
async def interest_run(body: InterestRunInput, actor: Actor = Depends(FINANCE)):
    async with sessions()() as session, session.begin():
        plan = await _interest_plan(session, body.financial_year)
        if not plan["year_ended"]:
            raise Problem(409, "/problems/financial-year-open", "The financial year has not ended",
                          f"Interest for {body.financial_year} is credited after 31 March.")
        if plan["rate_bp"] is None:
            raise Problem(409, "/problems/interest-rate-not-declared", "No interest rate is declared for that year",
                          "Publish a rule set with the rate for this financial year first (Policy administration).")
        if not plan["total_to_credit_paise"] and not any(a["employee"]["now_paise"] or a["employer"]["now_paise"] for a in plan["accounts"]):
            raise Problem(409, "/problems/nothing-to-credit", "Nothing to credit",
                          f"Interest for {body.financial_year} at {plan['rate_bp'] / 100:g}% is already credited to every account.")
        require_step_up(actor, "post-interest", body.financial_year, None, abs(plan["total_to_credit_paise"]))
        posted = await post_interest(session, body.financial_year, plan["rate_bp"], plan["rule_version"], actor.subject, actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="interest.posted",
                    target_type="interest_run", target_id=f"{body.financial_year}-{plan['rule_version']}",
                    detail=f"{len(posted)} accounts at {plan['rate_bp']} bp")
    return envelope({"financial_year": body.financial_year, "rate_bp": plan["rate_bp"], "rule_version": plan["rule_version"],
                     "accounts": len(posted), "credited_paise": plan["total_to_credit_paise"],
                     "revision": any(p["revision"] for p in posted), "postings": posted})


# ── Annexure K: the member's transfer statement (Form 13) ────────────────────────────────────────

@router.get("/api/v1/members/me/transfers/{transferId}/annexure-k")
async def annexure_k(transferId: str, actor: Actor = Depends(MEMBER)):
    async with sessions()() as session:
        t = (await session.execute(text("SELECT * FROM transfer_postings WHERE transfer_id=:t AND member_subject=:s"),
                                   {"t": transferId, "s": actor.subject})).mappings().first()
        if not t:
            raise Problem(404, "/problems/not-found", "Transfer not found", "Annexure K is available once the transfer is posted.")
        accounts = {r["account_link_id"]: r for r in (await session.execute(text(
            "SELECT m.account_link_id, m.name, m.uan, m.date_of_joining, m.date_of_exit, e.legal_name FROM establishment_members m "
            "JOIN establishments e ON e.id=m.establishment_id WHERE m.account_link_id IN (:f, :to)"),
            {"f": t["from_account_link_id"], "to": t["to_account_link_id"]})).mappings().all()}
    frm, to = accounts[t["from_account_link_id"]], accounts[t["to_account_link_id"]]

    def iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v        # SQLite (unit tests) returns text

    def side(a):
        return {"member_id": a["account_link_id"], "establishment": a["legal_name"],
                "date_of_joining": iso(a["date_of_joining"]), "date_of_exit": iso(a["date_of_exit"])}
    return envelope({"title": "Annexure K — transfer statement (illustrative)", "transfer_id": t["transfer_id"], "uan": t["uan"],
                     "member_name": frm["name"], "transferred_from": side(frm), "transferred_to": side(to),
                     "employee_share_paise": t["employee_paise"], "employer_share_paise": t["employer_paise"],
                     "total_paise": t["employee_paise"] + t["employer_paise"],
                     "posted_at": iso(t["posted_at"]),
                     "note": "Synthetic demonstration; the real Annexure K also carries pension service details."})


# ── an employee's wage and contribution ledger, for their employer ─────────────────────────────────

@router.get("/api/v1/employers/me/members/{uan}/contribution-ledger")
async def employee_ledger(uan: str, actor: Actor = Depends(EMPLOYER)):
    est = _establishment(actor)
    async with sessions()() as session:
        m = (await session.execute(text("SELECT account_link_id, name, date_of_joining, date_of_exit FROM establishment_members "
                                        "WHERE uan=:u AND establishment_id=:e"), {"u": uan, "e": est})).mappings().first()
        if not m:
            raise Problem(404, "/problems/not-found", "No such employee of this establishment")
        rows = (await session.execute(text(
            "SELECT f.wage_month, f.trrn, jl.share, jl.side, jl.amount_paise FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id "
            "JOIN ecr_filings f ON f.id=j.filing_id WHERE j.kind='CONTRIBUTION' AND jl.account_code='AC01_EPF' AND jl.account_link_id=:a "
            "ORDER BY f.wage_month"), {"a": m["account_link_id"]})).mappings().all()
    months: dict[str, dict] = {}
    for r in rows:
        row = months.setdefault(r["wage_month"], {"wage_month": r["wage_month"], "trrn": r["trrn"], "employee_paise": 0, "employer_paise": 0})
        row[f"{r['share']}_paise"] += r["amount_paise"] if r["side"] == "credit" else -r["amount_paise"]
    return envelope({"uan": uan, "member_id": m["account_link_id"], "name": m["name"], "months": list(months.values()),
                     "note": "Employee and employer (EPF) shares credited from this establishment's paid returns."})


# ── ANNEXURE K VDR RECO: the inter-office Annexure K amount against the VDR receipt (P2.5c) ────────────

class VdrReco(BaseModel):
    receipt_ref: str = Field(min_length=3, max_length=60)
    vdr_receipt_paise: int = Field(ge=0)


@router.post("/api/v1/office/annexure-k-files/{annexureId}/vdr-reconciliations")
async def annexure_k_vdr_reco(annexureId: str, body: VdrReco, actor: Actor = Depends(require_stakeholder("fo.da_accounts"))):
    """The Annexure K of a Form 13 transfer is matched with the amount the VDR (receipt register) shows as received."""
    async with sessions()() as session, session.begin():
        t = (await session.execute(text("SELECT * FROM transfer_postings WHERE transfer_id=:t"), {"t": annexureId})).mappings().first()
        if not t:
            raise Problem(404, "/problems/not-found", "Annexure K not found")
        done = (await session.execute(text("SELECT result FROM annexure_k_vdr_recos WHERE annexure_id=:a"), {"a": annexureId})).first()
        if done and done[0] == "MATCHED":
            raise Problem(409, "/problems/already-reconciled", "This Annexure K is already reconciled with the VDR")
        require_step_up(actor, "reconcile-annexure-k-vdr", annexureId, None, body.vdr_receipt_paise)
        amount = int(t["employee_paise"]) + int(t["employer_paise"])
        result = "MATCHED" if body.vdr_receipt_paise == amount else "MISMATCH"
        values = {"a": annexureId, "r": body.receipt_ref, "v": body.vdr_receipt_paise, "k": amount, "res": result, "by": actor.subject,
                  "at": datetime.now(UTC)}
        await session.execute(text("DELETE FROM annexure_k_vdr_recos WHERE annexure_id=:a"), {"a": annexureId})
        await session.execute(text("INSERT INTO annexure_k_vdr_recos (annexure_id, receipt_ref, vdr_receipt_paise, annexure_amount_paise, result, "
                                   "reconciled_by, reconciled_at) VALUES (:a, :r, :v, :k, :res, :by, :at)"), values)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="annexure_k.vdr_reconciled",
                    target_type="annexure_k", target_id=annexureId, detail=f"{result} {body.receipt_ref}")
    return envelope({"annexure_id": annexureId, "receipt_ref": body.receipt_ref, "vdr_receipt_paise": body.vdr_receipt_paise,
                     "annexure_amount_paise": amount, "difference_paise": body.vdr_receipt_paise - amount, "result": result,
                     "next_step": "Nothing more to do." if result == "MATCHED" else "Trace the difference with the sending office before re-reconciling."})
