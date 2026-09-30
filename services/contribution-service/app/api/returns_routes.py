"""Phase 2, slice 7a: returns and payments around a monthly return — cancelling an unpaid TRRN, the office rejecting
a return before posting or a payment stuck at the bank, the monthly returns dashboard, demands for late payment
(14B damages, 7Q interest), direct challans (administrative charges; miscellaneous 14B / 7Q) and the office's
knock-off of demands against a paid miscellaneous challan (DA Compliance proposes, SS approves)."""
import json
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from app.api.routes import _establishment, _next_trrn, _not_frozen
from app.infra.db import sessions
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import due_date, rules_on

router = APIRouter()
PRODUCER = "contribution-service"
EMPLOYER = require_stakeholder("employer.owner", "employer.operator", "employer.signatory")
SIGNATORY = require_stakeholder("employer.signatory")


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _filing(session, filing_id: str) -> dict[str, Any]:
    row = (await session.execute(text("SELECT * FROM ecr_filings WHERE id=:id"), {"id": filing_id})).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Return not found")
    return dict(row)


async def _unpaid_challan(session, filing: dict[str, Any]) -> dict[str, Any]:
    ch = (await session.execute(text("SELECT * FROM challans WHERE filing_id=:f"), {"f": filing["id"]})).mappings().first()
    if filing["state"] not in ("SUBMITTED", "PAYMENT_FAILED") or not ch or ch["status"] not in ("DUE", "FAILED"):
        raise Problem(409, "/problems/invalid-state", "Only a submitted return whose challan is unpaid can be cancelled or rejected",
                      f"Return {filing['state']}; challan {ch['status'] if ch else 'none'}.")
    return dict(ch)


async def _challan_status(session, trrn: str, status: str, reason: str, actor: Actor) -> None:
    await add_event(session, producer=PRODUCER, event_type="ChallanStatusChanged.v1", aggregate_type="challan", aggregate_id=trrn,
                    correlation_id=actor.correlation_id, payload={"trrn": trrn, "status": status, "reason": reason})


# ── cancel an unpaid TRRN (employer) and reject before posting (office) ──────────────────────────

class Reason(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/employers/me/ecr-filings/{filingId}/cancellations")
async def cancel_trrn(filingId: str, body: Reason, actor: Actor = Depends(SIGNATORY)) -> dict:
    """Cancel an unpaid TRRN: the challan can no longer be paid and the wage month is free for a new return."""
    require_grant(actor, "ecr.submit")
    eid = _establishment(actor)
    async with sessions()() as session, session.begin():
        f = await _filing(session, filingId)
        if f["establishment_id"] != eid:
            raise Problem(404, "/problems/not-found", "Return not found")
        ch = await _unpaid_challan(session, f)
        require_step_up(actor, "cancel-trrn", filingId, None, ch["total_paise"])
        await session.execute(text("UPDATE challans SET status='CANCELLED' WHERE trrn=:t"), {"t": ch["trrn"]})
        await session.execute(text("UPDATE ecr_filings SET state='CANCELLED' WHERE id=:f"), {"f": filingId})
        await _challan_status(session, ch["trrn"], "CANCELLED", body.reason, actor)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.trrn_cancelled",
                    target_type="ecr_filing", target_id=filingId, detail=f"{ch['trrn']}: {body.reason}")
    return envelope({"filing_id": filingId, "state": "CANCELLED", "trrn": ch["trrn"], "challan": "CANCELLED",
                     "next_step": "The wage month is free: prepare a new return."})


@router.post("/api/v1/office/ecr-filings/{filingId}/rejections")
async def reject_return(filingId: str, body: Reason, actor: Actor = Depends(require_stakeholder("fo.da_accounts"))) -> dict:
    """The office rejects a submitted return before it is paid and posted (e.g. a wrong wage month)."""
    async with sessions()() as session, session.begin():
        f = await _filing(session, filingId)
        ch = await _unpaid_challan(session, f)
        require_step_up(actor, "reject-ecr", filingId)
        await session.execute(text("UPDATE challans SET status='CANCELLED' WHERE trrn=:t"), {"t": ch["trrn"]})
        await session.execute(text("UPDATE ecr_filings SET state='REJECTED' WHERE id=:f"), {"f": filingId})
        await _challan_status(session, ch["trrn"], "REJECTED", body.reason, actor)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.rejected",
                    target_type="ecr_filing", target_id=filingId, detail=body.reason)
    return envelope({"filing_id": filingId, "state": "REJECTED", "trrn": ch["trrn"], "reason": body.reason})


@router.post("/api/v1/office/ecr-filings/{filingId}/payment-rejections")
async def reject_payment(filingId: str, body: Reason, actor: Actor = Depends(require_stakeholder("fo.cash"))) -> dict:
    """Cash rejects a payment stuck in pending bank status: the pending payment is dropped and the challan can be
    paid again (tracker: "Unable to reject ecr payment")."""
    async with sessions()() as session, session.begin():
        f = await _filing(session, filingId)
        ch = (await session.execute(text("SELECT * FROM challans WHERE filing_id=:f"), {"f": filingId})).mappings().first()
        if f["state"] != "SUBMITTED" or not ch or ch["status"] != "DUE":
            raise Problem(409, "/problems/invalid-state", "Only a submitted return whose payment has not been confirmed", f"Return {f['state']}.")
        require_step_up(actor, "reject-ecr-payment", filingId)
        await session.execute(text("UPDATE challans SET status='FAILED' WHERE trrn=:t"), {"t": ch["trrn"]})
        await session.execute(text("UPDATE ecr_filings SET state='PAYMENT_FAILED' WHERE id=:f"), {"f": filingId})
        await _challan_status(session, ch["trrn"], "PAYMENT_REJECTED", body.reason, actor)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ecr.payment_rejected",
                    target_type="ecr_filing", target_id=filingId, detail=body.reason)
    return envelope({"filing_id": filingId, "state": "PAYMENT_FAILED", "trrn": ch["trrn"], "next_step": "The employer pays the challan again."})


@router.get("/api/v1/office/ecr-filings")
async def office_filings(actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.cash"))) -> dict:
    """Returns submitted but not yet paid and posted — what the office may reject, or whose stuck payment Cash may reject."""
    async with sessions()() as session:
        rows = (await session.execute(text(
            "SELECT f.id, f.establishment_id, f.wage_month, f.filing_type, f.state, f.trrn, c.status AS challan_status, c.total_paise, c.created_at "
            "FROM ecr_filings f JOIN challans c ON c.filing_id = f.id WHERE f.state IN ('SUBMITTED', 'PAYMENT_FAILED') ORDER BY c.created_at"))).mappings().all()
    return envelope([{"filing_id": r["id"], "establishment_id": r["establishment_id"], "wage_month": r["wage_month"], "type": r["filing_type"],
                      "state": r["state"], "trrn": r["trrn"], "challan": r["challan_status"], "total_paise": r["total_paise"],
                      "submitted_at": _iso(r["created_at"])} for r in rows])


# ── the monthly returns dashboard and demands ──────────────────────────────────────────────────────

@router.get("/api/v1/employers/me/returns/dashboard")
async def dashboard(actor: Actor = Depends(EMPLOYER)) -> dict:
    eid = _establishment(actor)
    async with sessions()() as session:
        rows = (await session.execute(text(
            "SELECT f.wage_month, f.filing_type, f.state, f.trrn, c.status AS challan_status, c.total_paise, c.paid_at "
            "FROM ecr_filings f LEFT JOIN challans c ON c.filing_id = f.id WHERE f.establishment_id=:e AND f.state <> 'SUPERSEDED' "
            "ORDER BY f.wage_month DESC, f.version"), {"e": eid})).mappings().all()
        rules = await rules_on(session, date.today())
    months: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = months.setdefault(r["wage_month"], {"wage_month": r["wage_month"], "due_date": due_date(r["wage_month"], rules).isoformat(),
                                                "regular": None, "additional": [], "paid_paise": 0})
        entry = {"type": r["filing_type"], "state": r["state"], "trrn": r["trrn"], "challan": r["challan_status"], "total_paise": r["total_paise"],
                 "paid_on": _iso(r["paid_at"])[:10] if r["paid_at"] else None}
        if r["challan_status"] == "PAID":
            m["paid_paise"] += r["total_paise"] or 0
        if r["filing_type"] == "REGULAR":
            m["regular"] = entry if m["regular"] is None or r["state"] not in ("CANCELLED", "REJECTED") else m["regular"]
        else:
            m["additional"].append(entry)
    for m in months.values():
        reg = m["regular"] or {}
        m["status"] = ("PAID" if reg.get("challan") == "PAID" else "AWAITING_PAYMENT" if reg.get("state") in ("SUBMITTED", "PAYMENT_FAILED")
                       else "NOT_FILED" if not reg or reg.get("state") in ("CANCELLED", "REJECTED") else "IN_PREPARATION")
        m["paid_late"] = bool(reg.get("paid_on") and reg["paid_on"] > m["due_date"])
    return envelope(sorted(months.values(), key=lambda x: x["wage_month"], reverse=True))


def _demand(d: Any) -> dict[str, Any]:
    return {"demand_id": d["demand_id"], "kind": d["kind"], "trrn": d["trrn"], "wage_month": d["wage_month"], "amount_paise": d["amount_paise"],
            "days_late": d["days_late"], "working": d["working"], "rule_version": d["rule_version"], "state": d["state"],
            "settled_by": d["settled_by"], "created_at": _iso(d["created_at"])}


@router.get("/api/v1/employers/me/demands")
async def demands(actor: Actor = Depends(EMPLOYER)) -> dict:
    eid = _establishment(actor)
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM demands WHERE establishment_id=:e ORDER BY created_at DESC"), {"e": eid})).mappings().all()
    items = [_demand(r) for r in rows]
    return envelope({"items": items, "open_paise": sum(d["amount_paise"] for d in items if d["state"] == "OPEN"),
                     "note": "Raised when contributions are paid after the due date (illustrative 14B / 7Q rates in the rules). "
                             "Pay them with a miscellaneous direct challan; the PF office knocks them off."})


# ── direct challans ─────────────────────────────────────────────────────────────────────────────────

class DirectChallan(BaseModel):
    kind: str = Field(pattern="^(ADMIN_CHARGES|MISC_14B_7Q)$")
    admin_paise: int = Field(default=0, ge=0)
    damages_14b_paise: int = Field(default=0, ge=0)
    interest_7q_paise: int = Field(default=0, ge=0)
    reason: str = Field(min_length=5, max_length=300)


@router.post("/api/v1/employers/me/direct-challans", status_code=201)
async def direct_challan(body: DirectChallan, actor: Actor = Depends(SIGNATORY)) -> dict:
    require_grant(actor, "payment.initiate")
    eid = _establishment(actor)
    breakdown = ({"AC02_ADMIN": body.admin_paise} if body.kind == "ADMIN_CHARGES"
                 else {"DAMAGES_14B": body.damages_14b_paise, "INTEREST_7Q": body.interest_7q_paise})
    total = sum(breakdown.values())
    if total <= 0 or total % 100:
        raise Problem(422, "/problems/validation", "Enter the amounts in whole rupees, more than zero")
    async with sessions()() as session, session.begin():
        await _not_frozen(session, eid)
        require_step_up(actor, "raise-direct-challan", eid, None, total)
        trrn = await _next_trrn(session)
        kind = "DIRECT_ADMIN" if body.kind == "ADMIN_CHARGES" else "DIRECT_MISC"
        await session.execute(text("INSERT INTO challans (trrn, filing_id, establishment_id, status, total_paise, breakdown, kind, applied_paise) "
                                   "VALUES (:t, NULL, :e, 'DUE', :a, :b, :k, 0)"), {"t": trrn, "e": eid, "a": total, "b": json.dumps(breakdown), "k": kind})
        await add_event(session, producer=PRODUCER, event_type="ChallanGenerated.v1", aggregate_type="challan", aggregate_id=trrn,
                        correlation_id=actor.correlation_id, payload={"trrn": trrn, "establishment_id": eid, "kind": kind, "total_paise": total,
                                                                      "reference_id": trrn})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="challan.direct_raised",
                    target_type="challan", target_id=trrn, detail=f"{kind} {total}: {body.reason}")
    return envelope({"trrn": trrn, "kind": kind, "status": "DUE", "total_paise": total, "breakdown_paise": breakdown,
                     "next_step": "Pay the challan (Payments › TRRN query / challan status)."})


# ── 14B / 7Q knock-off (DA Compliance proposes, SS approves) ───────────────────────────────────────

class KnockOffInput(BaseModel):
    trrn: str = Field(min_length=5, max_length=17)
    demand_ids: list[str] = Field(min_length=1, max_length=50)


def _knock_off(k: Any) -> dict[str, Any]:
    return {"knock_off_id": k["knock_off_id"], "establishment_id": k["establishment_id"], "trrn": k["trrn"], "demand_ids": k["demand_ids"],
            "amount_paise": k["amount_paise"], "state": k["state"], "note": k["note"], "created_at": _iso(k["created_at"])}


@router.post("/api/v1/office/establishments/{estId}/damages-knock-offs", status_code=201)
async def propose_knock_off(estId: str, body: KnockOffInput, actor: Actor = Depends(require_stakeholder("fo.da_compliance"))) -> dict:
    async with sessions()() as session, session.begin():
        ch = (await session.execute(text("SELECT * FROM challans WHERE trrn=:t AND establishment_id=:e"), {"t": body.trrn, "e": estId})).mappings().first()
        if not ch or ch["kind"] != "DIRECT_MISC" or ch["status"] != "PAID":
            raise Problem(422, "/problems/validation", "Choose a paid miscellaneous (14B / 7Q) challan of this establishment")
        rows = (await session.execute(text("SELECT * FROM demands WHERE establishment_id=:e"), {"e": estId})).mappings().all()
        chosen = [r for r in rows if r["demand_id"] in body.demand_ids]
        if len(chosen) != len(set(body.demand_ids)) or any(r["state"] != "OPEN" for r in chosen):
            raise Problem(422, "/problems/validation", "Every demand must be open and belong to this establishment")
        pending = (await session.execute(text("SELECT COALESCE(SUM(amount_paise), 0) FROM damages_knock_offs WHERE trrn=:t AND state='PROPOSED'"),
                                         {"t": body.trrn})).scalar_one()
        amount = sum(r["amount_paise"] for r in chosen)
        available = ch["total_paise"] - ch["applied_paise"] - int(pending)
        if amount > available:
            raise Problem(422, "/problems/knock-off-exceeds-challan", "The demands exceed what is left on the challan",
                          f"₹{available // 100:,} is left on {body.trrn}; the demands come to ₹{amount // 100:,}.")
        require_step_up(actor, "propose-knock-off", estId, None, amount)
        row = {"knock_off_id": f"KO-{secrets.token_hex(4).upper()}", "establishment_id": estId, "trrn": body.trrn, "demand_ids": list(body.demand_ids),
               "amount_paise": amount, "state": "PROPOSED", "proposed_by": actor.subject, "note": None, "created_at": datetime.now(UTC)}
        await session.execute(text("INSERT INTO damages_knock_offs (knock_off_id, establishment_id, trrn, demand_ids, amount_paise, state, proposed_by, created_at) "
                                   "VALUES (:knock_off_id, :establishment_id, :trrn, :demand_ids, :amount_paise, :state, :proposed_by, :created_at)"),
                              {**row, "demand_ids": json.dumps(row["demand_ids"])})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="knock_off.proposed",
                    target_type="establishment", target_id=estId, detail=f"{row['knock_off_id']} {amount}")
    return envelope(_knock_off(row))


@router.get("/api/v1/office/damages-knock-offs")
async def knock_offs(actor: Actor = Depends(require_stakeholder("fo.da_compliance", "fo.ss"))) -> dict:
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM damages_knock_offs ORDER BY created_at DESC"))).mappings().all()
        open_demands = (await session.execute(text("SELECT * FROM demands WHERE state='OPEN' ORDER BY created_at"))).mappings().all()
        misc = (await session.execute(text("SELECT trrn, establishment_id, total_paise, applied_paise FROM challans "
                                           "WHERE kind='DIRECT_MISC' AND status='PAID' AND applied_paise < total_paise"))).mappings().all()
    return envelope({"knock_offs": [_knock_off({**dict(r), "demand_ids": r["demand_ids"] if isinstance(r["demand_ids"], list) else json.loads(r["demand_ids"])})
                                    for r in rows],
                     "open_demands": [{**_demand(d), "establishment_id": d["establishment_id"]} for d in open_demands],
                     "misc_challans_with_balance": [dict(m) for m in misc]})


class KnockOffDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/damages-knock-offs/{knockOffId}/approvals")
async def approve_knock_off(knockOffId: str, body: KnockOffDecision, actor: Actor = Depends(require_stakeholder("fo.ss"))) -> dict:
    async with sessions()() as session, session.begin():
        k = (await session.execute(text("SELECT * FROM damages_knock_offs WHERE knock_off_id=:k"), {"k": knockOffId})).mappings().first()
        if not k:
            raise Problem(404, "/problems/not-found", "Knock-off not found")
        if k["state"] != "PROPOSED":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {k['state']}.")
        if k["proposed_by"] == actor.subject:
            raise Problem(403, "/problems/separation-of-duties", "You proposed this knock-off")
        require_step_up(actor, "approve-knock-off", knockOffId, None, k["amount_paise"])
        ids = k["demand_ids"] if isinstance(k["demand_ids"], list) else json.loads(k["demand_ids"])
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        if state == "APPROVED":
            still_open = (await session.execute(text("SELECT COUNT(*) FROM demands WHERE state='OPEN' AND demand_id IN :ids").bindparams(
                bindparam("ids", expanding=True)), {"ids": ids})).scalar_one()
            if still_open != len(ids):
                raise Problem(409, "/problems/demand-settled", "A demand in this knock-off is already settled")
            await session.execute(text("UPDATE demands SET state='KNOCKED_OFF', settled_by=:k WHERE demand_id IN :ids").bindparams(
                bindparam("ids", expanding=True)), {"k": knockOffId, "ids": ids})
            await session.execute(text("UPDATE challans SET applied_paise = applied_paise + :a WHERE trrn=:t"), {"a": k["amount_paise"], "t": k["trrn"]})
            from app.infra.demands import publish
            await publish(session, ids, actor.correlation_id)
        await session.execute(text("UPDATE damages_knock_offs SET state=:s, decided_by=:d, note=:n WHERE knock_off_id=:k"),
                              {"s": state, "d": actor.subject, "n": body.note, "k": knockOffId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"knock_off.{state.lower()}",
                    target_type="knock_off", target_id=knockOffId, detail=body.note)
    return envelope(_knock_off({**dict(k), "demand_ids": ids, "state": state, "note": body.note}))
