"""Phase 2, slice 8d: two HO / office records that move money later. Illustrative.

* The approved annual interest rate: HO F&A records the CBT's recommendation and the Ministry's concurrence;
  InterestRateDeclared.v1 makes platform-service prepare a draft rule set with that rate, which ACC (HQ) submits and
  the CPFC approves as any rule change. Interest is credited only from the published rule set.
* A surrendered PF trust's past accumulations: the exemption cell ingests the trust's member ledgers (one batch per
  transfer reference) for member IDs of the establishment; each line is a balanced journal crediting the member's
  employee and employer shares (and the pension fund) against the trust's transfer, published as LedgerAdjusted.v1
  (PAST_ACCUMULATION) so the claims projection sees the balances. All lines or none."""
import json
import re
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.claims_ledger import _post
from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "contribution-service"
FY = re.compile(r"^(\d{4})-(\d{2})$")


class RateInput(BaseModel):
    rate_bp: int = Field(ge=0, le=2000)
    cbt_recommended_on: date
    ministry_concurrence_ref: str = Field(min_length=3, max_length=80)
    ministry_concurrence_on: date
    note: str = Field(default="", max_length=1000)


@router.put("/api/v1/ho/config/interest-rates/{financialYear}")
async def record_rate(financialYear: str, body: RateInput, actor: Actor = Depends(require_stakeholder("ho.fa_cao"))) -> dict:
    m = FY.match(financialYear)
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise Problem(422, "/problems/validation", "Write the financial year as 2025-26")
    if body.ministry_concurrence_on < body.cbt_recommended_on:
        raise Problem(422, "/problems/validation", "The Ministry concurs after the CBT recommends")
    if body.ministry_concurrence_on > date.today():
        raise Problem(422, "/problems/validation", "The concurrence cannot be dated in the future")
    require_step_up(actor, "record-interest-rate", financialYear, None, body.rate_bp)
    declaration_id = f"IRD-{secrets.token_hex(4).upper()}"
    async with sessions()() as session, session.begin():
        await session.execute(text(
            "INSERT INTO interest_rate_declarations (declaration_id, financial_year, rate_bp, cbt_recommended_on, ministry_concurrence_ref, "
            "ministry_concurrence_on, note, recorded_by, created_at) VALUES (:d, :fy, :r, :cbt, :ref, :on, :note, :by, CURRENT_TIMESTAMP)"),
            {"d": declaration_id, "fy": financialYear, "r": body.rate_bp, "cbt": body.cbt_recommended_on, "ref": body.ministry_concurrence_ref,
             "on": body.ministry_concurrence_on, "note": body.note or None, "by": actor.subject})
        await add_event(session, producer=PRODUCER, event_type="InterestRateDeclared.v1", aggregate_type="interest_rate",
                        aggregate_id=declaration_id, correlation_id=actor.correlation_id, payload={
                            "declaration_id": declaration_id, "financial_year": financialYear, "rate_bp": body.rate_bp,
                            "cbt_recommended_on": body.cbt_recommended_on.isoformat(),
                            "ministry_concurrence_ref": body.ministry_concurrence_ref,
                            "ministry_concurrence_on": body.ministry_concurrence_on.isoformat()})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="interest.rate_recorded",
                    target_type="interest_rate", target_id=financialYear, detail=f"{body.rate_bp} bp ({declaration_id})")
        history = (await session.execute(text(
            "SELECT declaration_id, rate_bp, ministry_concurrence_ref, created_at FROM interest_rate_declarations "
            "WHERE financial_year=:fy ORDER BY created_at"), {"fy": financialYear})).mappings().all()
    return envelope({"declaration_id": declaration_id, "financial_year": financialYear, "rate_bp": body.rate_bp,
                     "recorded": [{**dict(h), "created_at": h["created_at"].isoformat() if hasattr(h["created_at"], "isoformat") else h["created_at"]}
                                  for h in history],
                     "next_step": "A draft rule set with this rate is prepared for ACC (HQ) to submit and the CPFC to approve; "
                                  "interest is credited from the published rule set only."})


class Ingestion(BaseModel):
    transfer_reference: str = Field(min_length=4, max_length=80)
    content: str = Field(min_length=10, max_length=200_000)   # uan,account_link_id,employee_rupees,employer_rupees,pension_rupees


def parse_lines(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows, problems, seen = [], [], set()
    for n, raw in enumerate([x.strip() for x in content.strip().splitlines() if x.strip()], start=1):
        if raw.lower().startswith("uan"):
            continue
        parts = [x.strip() for x in raw.split(",")]
        if len(parts) != 5 or not re.fullmatch(r"[0-9]{12}", parts[0]) or not all(p.isdigit() for p in parts[2:]):
            problems.append(f"line {n}: write uan,account_link_id,employee_rupees,employer_rupees,pension_rupees")
            continue
        if parts[1] in seen:
            problems.append(f"line {n}: {parts[1]} is given twice")
            continue
        employee, employer, pension = (int(p) * 100 for p in parts[2:])
        if not employee + employer + pension:
            problems.append(f"line {n}: nothing to credit")
            continue
        seen.add(parts[1])
        rows.append({"line": n, "uan": parts[0], "account_link_id": parts[1], "employee_paise": employee,
                     "employer_paise": employer, "pension_paise": pension})
    if not rows and not problems:
        problems.append("the file has no member lines")
    return rows, problems


@router.post("/api/v1/office/exempted/{estId}/past-accumulation-ingestions", status_code=201)
async def ingest(estId: str, body: Ingestion, actor: Actor = Depends(require_stakeholder("fo.exemption"))) -> dict:
    rows, problems = parse_lines(body.content)
    async with sessions()() as session, session.begin():
        est = (await session.execute(text("SELECT id, legal_name, exemption_status FROM establishments WHERE id=:e"), {"e": estId})).mappings().first()
        if not est:
            raise Problem(404, "/problems/not-found", "Establishment not found")
        if est["exemption_status"] not in ("UNEXEMPTED_COMPLIANCE", "SURRENDERED", "CANCELLED"):
            raise Problem(409, "/problems/not-surrendered", "Only a trust whose exemption has ended is taken over",
                          f"{est['legal_name']}: exemption status {est['exemption_status'] or 'not exempted'}.")
        due = (await session.execute(text("SELECT past_accumulations_due FROM exempted_establishments WHERE establishment_id=:e"),
                                     {"e": estId})).scalar_one_or_none()
        if isinstance(due, str):
            due = date.fromisoformat(due)
        late_days = max(0, (date.today() - due).days) if due else 0
        late_note = (f"Past accumulations received {late_days} days late: damages (s.14B) and interest (s.7Q) apply"
                     if late_days else None)
        if (await session.execute(text("SELECT 1 FROM past_accumulation_ingestions WHERE transfer_reference=:r"),
                                  {"r": body.transfer_reference})).first():
            raise Problem(409, "/problems/already-ingested", "This transfer reference was already ingested")
        members = {r["account_link_id"]: dict(r) for r in (await session.execute(text(
            "SELECT uan, account_link_id FROM establishment_members WHERE establishment_id=:e"), {"e": estId})).mappings().all()}
        for r in rows:
            m = members.get(r["account_link_id"])
            if not m or m["uan"] != r["uan"]:
                problems.append(f"line {r['line']}: {r['account_link_id']} is not a member ID of UAN {r['uan']} at this establishment")
        if problems:
            raise Problem(422, "/problems/validation", "The file has errors; nothing was ingested", "; ".join(problems[:10]), errors=problems)
        total = sum(r["employee_paise"] + r["employer_paise"] + r["pension_paise"] for r in rows)
        require_step_up(actor, "ingest-past-accumulation", estId, None, total)
        batch_id = f"PAI-{secrets.token_hex(4).upper()}"
        posted = []
        for r in rows:
            lines = [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": r[f"{s}_paise"], "account_link_id": r["account_link_id"], "share": s}
                     for s in ("employee", "employer") if r[f"{s}_paise"]]
            if r["pension_paise"]:
                lines.append({"account_code": "AC10_EPS", "side": "credit", "amount_paise": r["pension_paise"]})
            amount = r["employee_paise"] + r["employer_paise"] + r["pension_paise"]
            lines.append({"account_code": "TRUST_TRANSFER_RECEIVABLE", "side": "debit", "amount_paise": amount})
            journal_id = await _post(session, f"PAST-ACCUM-{batch_id}-{r['account_link_id']}", "PAST_ACCUMULATION", None, lines)
            await add_event(session, producer=PRODUCER, event_type="LedgerAdjusted.v1", aggregate_type="ledger_journal", aggregate_id=journal_id,
                            correlation_id=actor.correlation_id, payload={"adjustment_id": f"{batch_id}-{r['line']}", "journal_id": journal_id,
                                                                          "account_link_id": r["account_link_id"], "appendix_type": "PAST_ACCUMULATION",
                                                                          "postings": lines})
            posted.append({**r, "journal_id": journal_id})
        await session.execute(text(
            "INSERT INTO past_accumulation_ingestions (batch_id, establishment_id, transfer_reference, lines, total_paise, ingested_by, created_at) "
            "VALUES (:b, :e, :r, :l, :t, :by, CURRENT_TIMESTAMP)"),
            {"b": batch_id, "e": estId, "r": body.transfer_reference, "l": json.dumps(posted), "t": total, "by": actor.subject})
        await add_event(session, producer=PRODUCER, event_type="TrustAccumulationIngested.v1", aggregate_type="past_accumulation_ingestion",
                        aggregate_id=batch_id, correlation_id=actor.correlation_id, payload={
                            "batch_id": batch_id, "establishment_id": estId, "transfer_reference": body.transfer_reference,
                            "members": len(posted), "total_paise": total})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="exempted.past_accumulation_ingestion",
                    target_type="establishment", target_id=estId,
                    detail=f"{batch_id} {len(posted)} members {total}" + (f"; late_days={late_days}; {late_note}" if late_note else ""))
    return envelope({"batch_id": batch_id, "establishment_id": estId, "legal_name": est["legal_name"],
                     "transfer_reference": body.transfer_reference, "members": len(posted), "total_paise": total,
                     "late_days": late_days, "note": late_note,
                     "lines": [{k: p[k] for k in ("line", "uan", "account_link_id", "employee_paise", "employer_paise", "pension_paise", "journal_id")}
                               for p in posted]})
