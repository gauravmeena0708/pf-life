"""Employees' Enrolment Campaign, 2026 (P2.26b; PIB 2300475 of 17 Aug 2026, with the EPF Scheme, 2026).

An employer enrols an employee left out of EPF between 1 April 2009 and 31 March 2026 who still works for it: the employee is
registered first (face-authenticated UAN, the usual onboarding), then declared here. The past dues are worked out month by
month from joining to March 2026 at each month's wage ceiling — the employer's share (EPF and EPS), EDLI and administrative
charges, 7Q interest from each month's due date — and the employee's share only where it was deducted from the wages (else
it is waived), with lump-sum damages of ₹100. They are paid on one challan (kind EEC); the payment credits the member."""
import json
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes import _establishment, _next_trrn, _not_frozen
from app.infra.db import sessions
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import baseline, due_date, round_rupee_half_up, rules_on, section

router = APIRouter()
BASE = "/api/v1/employers/me/eec-declarations"
LAST_MONTH = "2026-03"


def today() -> date:
    return date.today()


def _months(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def ceiling_for(month: str, ceilings: list[dict[str, Any]]) -> int:
    """The wage ceiling of a past wage month (the table the higher-pension dues use: ₹6,500 from 2001, ₹15,000 from Sep 2014)."""
    return [c["ceiling_paise"] for c in ceilings if c["from_month"] <= month][-1]


def eec_dues(joined: date, born: date | None, wages: int, deducted: bool, rules: dict[str, Any], on: date) -> dict[str, Any]:
    """The month-by-month dues of a left-out employee, from the month of joining (not before April 2009) to March 2026."""
    c, lp, eec = rules["contribution"], section(rules, "late_payment"), section(rules, "eec")
    ceilings = section(rules, "higher_pension")["wage_ceilings"]
    first = max(joined.strftime("%Y-%m"), eec["joined_from"][:7])
    months, totals = [], {"AC01_EPF_EE": 0, "AC01_EPF_ER": 0, "AC10_EPS": 0, "AC21_EDLI": 0, "AC02_ADMIN": 0, "INTEREST_7Q": 0}
    for month in _months(first, LAST_MONTH):
        base = min(wages, ceiling_for(month, ceilings))
        age = int(month[:4]) - born.year - ((int(month[5:7]), 28) < (born.month, born.day)) if born else 0
        share = round_rupee_half_up(base * c["epf_employee_rate_bp"])
        eps = 0 if age >= c["eps_age_limit_years"] else round_rupee_half_up(base * c["eps_rate_bp"])
        line = {"wage_month": month, "wages_paise": base, "AC01_EPF_EE": share if deducted else 0, "AC01_EPF_ER": share - eps, "AC10_EPS": eps,
                "AC21_EDLI": round_rupee_half_up(base * c["edli_rate_bp"]), "AC02_ADMIN": round_rupee_half_up(base * c["admin_charges_rate_bp"])}
        owed = line["AC01_EPF_EE"] + line["AC01_EPF_ER"] + line["AC10_EPS"] + line["AC21_EDLI"]
        days = max(0, (on - due_date(month, rules)).days)
        line["INTEREST_7Q"] = round_rupee_half_up(owed * lp["interest_7q_rate_bp_pa"] * days // 365)
        for k in totals:
            totals[k] += line[k]
        months.append(line)
    totals["DAMAGES_14B"] = eec["damages_paise"]
    totals["TOTAL"] = sum(totals.values())
    return {"from_month": first, "to_month": LAST_MONTH, "months": months, "totals_paise": totals,
            "employee_share_waived": not deducted}


def _view(r: Any) -> dict[str, Any]:
    return {"declaration_id": r["declaration_id"], "uan": r["uan"], "from_month": r["from_month"], "to_month": r["to_month"],
            "monthly_wages_paise": r["monthly_wages_paise"], "employee_share_deducted": bool(r["employee_share_deducted"]),
            "totals_paise": r["totals"] if isinstance(r["totals"], dict) else json.loads(r["totals"]), "trrn": r["trrn"], "state": r["state"]}


async def _candidates(session, establishment_id: str, eec: dict[str, Any]) -> list[dict[str, Any]]:
    """Members still working here who joined in the campaign's period and have nothing ever contributed for them."""
    rows = (await session.execute(text(
        "SELECT m.* FROM establishment_members m WHERE m.establishment_id=:e AND m.status='ACTIVE' AND m.date_of_exit IS NULL "
        "AND m.date_of_joining BETWEEN :a AND :b AND NOT EXISTS (SELECT 1 FROM journal_lines l WHERE l.account_link_id=m.account_link_id) "
        "AND NOT EXISTS (SELECT 1 FROM eec_declarations d WHERE d.account_link_id=m.account_link_id)"),
        {"e": establishment_id, "a": date.fromisoformat(eec["joined_from"]), "b": date.fromisoformat(eec["joined_until"])})).mappings().all()
    return [{"uan": r["uan"], "name": r["name"], "account_link_id": r["account_link_id"], "date_of_joining": str(r["date_of_joining"])} for r in rows]


@router.get(BASE)
async def declarations(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory", "employer.operator"))) -> dict:
    eid = _establishment(actor)
    eec = section(baseline(), "eec")
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM eec_declarations WHERE establishment_id=:e ORDER BY created_at DESC"),
                                      {"e": eid})).mappings().all()
        candidates = await _candidates(session, eid, eec)
    return envelope({"scheme": {k: eec[k] for k in ("scheme", "open_from", "open_until", "joined_from", "joined_until", "damages_paise")},
                     "open": eec["open_from"] <= today().isoformat() <= eec["open_until"],
                     "candidates": candidates, "declarations": [_view(r) for r in rows]})


class Declaration(BaseModel):
    uan: str = Field(pattern=r"^\d{12}$")
    monthly_wages_paise: int = Field(gt=0)
    employee_share_deducted: bool
    declaration: bool


async def _work_out(session, eid: str, body: Declaration, on: date) -> tuple[dict[str, Any], dict[str, Any]]:
    """The member and the dues of a declaration, or why it cannot be made."""
    eec = section(baseline(), "eec")
    if not eec["open_from"] <= on.isoformat() <= eec["open_until"]:
        raise Problem(422, "/problems/campaign-closed", f"{eec['scheme']} is open from {eec['open_from']} to {eec['open_until']}")
    member = next((m for m in await _candidates(session, eid, eec) if m["uan"] == body.uan), None)
    if member is None:
        raise Problem(422, "/problems/not-eligible", "Not an employee left out under the campaign",
                      f"Register the employee first (face-authenticated UAN). They must still work here, have joined between "
                      f"{eec['joined_from']} and {eec['joined_until']}, and have nothing contributed for them, nor a declaration.")
    rules = await rules_on(session, on)
    ceilings = section(rules, "higher_pension")["wage_ceilings"]
    joined = date.fromisoformat(member["date_of_joining"])
    at_joining = ceiling_for(max(joined.strftime("%Y-%m"), eec["joined_from"][:7]), ceilings)
    if body.monthly_wages_paise > at_joining:
        raise Problem(422, "/problems/excluded-employee", "Above the wage ceiling when the employee joined",
                      f"An employee earning more than ₹{at_joining // 100:,} then was an excluded employee, not one left out.")
    born = (await session.execute(text("SELECT date_of_birth FROM establishment_members WHERE account_link_id=:a"),
                                  {"a": member["account_link_id"]})).scalar_one_or_none()
    born = date.fromisoformat(str(born)) if born else None
    return member, eec_dues(joined, born, body.monthly_wages_paise, body.employee_share_deducted, rules, on)


@router.get(BASE + "/dues")
async def dues_of(uan: str = Query(pattern=r"^\d{12}$"), monthly_wages_paise: int = Query(gt=0), employee_share_deducted: bool = Query(),
                  actor: Actor = Depends(require_stakeholder("employer.signatory", "employer.owner"))) -> dict:
    """The dues a declaration would raise, before declaring."""
    eid = _establishment(actor)
    body = Declaration(uan=uan, monthly_wages_paise=monthly_wages_paise, employee_share_deducted=employee_share_deducted, declaration=False)
    async with sessions()() as session:
        member, dues = await _work_out(session, eid, body, today())
    return envelope({**dues, "uan": uan, "name": member["name"]})


@router.post(BASE, status_code=201)
async def declare(body: Declaration, actor: Actor = Depends(require_stakeholder("employer.signatory"))) -> dict:
    """Declare a left-out employee (registered first: a face-authenticated UAN) and raise the challan for the past dues."""
    require_grant(actor, "payment.initiate")
    eid = _establishment(actor)
    if not body.declaration:
        raise Problem(422, "/problems/validation", "Accept the declaration")
    on = today()
    async with sessions()() as session, session.begin():
        await _not_frozen(session, eid)
        member, dues = await _work_out(session, eid, body, on)
        total = dues["totals_paise"]["TOTAL"]
        require_step_up(actor, "declare-eec", body.uan, None, total)
        trrn = await _next_trrn(session)
        did = f"EEC-{secrets.token_hex(4).upper()}"
        breakdown = {k: v for k, v in dues["totals_paise"].items() if k != "TOTAL"}
        await session.execute(text("INSERT INTO challans (trrn, filing_id, establishment_id, status, total_paise, breakdown, kind, applied_paise) "
                                   "VALUES (:t, NULL, :e, 'DUE', :a, :b, 'EEC', 0)"), {"t": trrn, "e": eid, "a": total, "b": json.dumps(breakdown)})
        await session.execute(text(
            "INSERT INTO eec_declarations (declaration_id, establishment_id, uan, account_link_id, monthly_wages_paise, employee_share_deducted, "
            "from_month, to_month, months, totals, trrn, state, declared_by, created_at) VALUES (:d,:e,:u,:a,:w,:x,:f,:to,:m,:tot,:t,'DUE',:by,:at)"),
            {"d": did, "e": eid, "u": body.uan, "a": member["account_link_id"], "w": body.monthly_wages_paise, "x": body.employee_share_deducted,
             "f": dues["from_month"], "to": dues["to_month"], "m": json.dumps(dues["months"]), "tot": json.dumps(dues["totals_paise"]),
             "t": trrn, "by": actor.subject, "at": datetime.now(UTC)})
        await add_event(session, producer="contribution-service", event_type="ChallanGenerated.v1", aggregate_type="challan", aggregate_id=trrn,
                        correlation_id=actor.correlation_id, payload={"trrn": trrn, "establishment_id": eid, "kind": "EEC", "total_paise": total,
                                                                      "reference_id": trrn})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="eec.declared",
                    target_type="member", target_id=body.uan, detail=f"{did} {trrn} {total}")
    return envelope({**dues, "declaration_id": did, "trrn": trrn, "state": "DUE", "uan": body.uan, "name": member["name"],
                     "next_step": "Pay the challan (Payments › TRRN query / challan status); the member's account is credited when it is paid."})


async def post_eec_challan(session, row: Any, p: dict[str, Any]) -> None:
    """A paid EEC challan: the bank collection against the member's shares, the pension and EDLI funds, the charges, interest
    and damages; the declaration is PAID."""
    import uuid
    await session.execute(text("UPDATE challans SET status='PAID',payment_id=:p,paid_at=:at WHERE trrn=:t"),
                          {"p": p["payment_id"], "t": row["trrn"], "at": datetime.now(UTC)})
    d = (await session.execute(text("SELECT * FROM eec_declarations WHERE trrn=:t"), {"t": row["trrn"]})).mappings().first()
    if not d or (await session.execute(text("SELECT id FROM journals WHERE business_key=:k"), {"k": p["payment_id"]})).first():
        return
    t = d["totals"] if isinstance(d["totals"], dict) else json.loads(d["totals"])
    lines = [{"account_code": "BANK_COLLECTION", "side": "debit", "amount_paise": int(p["amount_paise"])}]
    for share, key in (("employee", "AC01_EPF_EE"), ("employer", "AC01_EPF_ER")):
        if t[key]:
            lines.append({"account_code": "AC01_EPF", "side": "credit", "amount_paise": t[key], "account_link_id": d["account_link_id"], "share": share})
    for code in ("AC10_EPS", "AC21_EDLI", "AC02_ADMIN", "INTEREST_7Q", "DAMAGES_14B"):
        if t[code]:
            lines.append({"account_code": code, "side": "credit", "amount_paise": t[code]})
    if sum(x["amount_paise"] for x in lines if x["side"] == "credit") != int(p["amount_paise"]):
        raise ValueError("EEC challan amount does not balance")
    jid = str(uuid.uuid4())
    await session.execute(text("INSERT INTO journals (id,business_key,kind,occurred_at) VALUES (:id,:k,'EEC',:at)"),
                          {"id": jid, "k": p["payment_id"], "at": datetime.now(UTC)})
    for line in lines:
        await session.execute(text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise,account_link_id,share) VALUES (:j,:a,:s,:n,:l,:h)"),
                              {"j": jid, "a": line["account_code"], "s": line["side"], "n": line["amount_paise"],
                               "l": line.get("account_link_id"), "h": line.get("share")})
    await session.execute(text("UPDATE eec_declarations SET state='PAID' WHERE declaration_id=:d"), {"d": d["declaration_id"]})
    # claim-service learns the credit as it does a trust's past accumulations (found missing by the consistency check, P2.27)
    await add_event(session, producer="contribution-service", event_type="LedgerAdjusted.v1", aggregate_type="ledger_journal", aggregate_id=jid,
                    correlation_id=None, payload={"adjustment_id": d["declaration_id"], "journal_id": jid, "account_link_id": d["account_link_id"],
                                                  "appendix_type": "EEC_ARREARS", "postings": lines})
