"""PAST ACCUM VDR RECO — the receipts of a de-exempted trust's past accumulations reconciled (SOP on surrender of exemption,
Dec 2023, (ix)-(xxiv); SOP on cancellation, (h)).

The exemption cell credits the members from the trust's ledgers (past-accumulation ingestion) against the trust transfer
receivable. The money arrives in parts: the cash component by demand draft, recorded by the cashier as a VDR entry; the SDS
balance and the permitted securities, which HO's Investment Division confirms with a reference number. DA (Accounts)
proposes the receipts against the trust's Form SE-6 statement; the APFC approves (step-up). Each receipt clears the
receivable in the ledger. The trust is reconciled when what was received equals what was credited and the SE-6 total;
otherwise the shortfall stays outstanding (damages and interest apply after 30 days, Para 28)."""
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.infra.claims_ledger import _post
from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
BASE = "/api/v1/office/exempted"
ACCOUNT = {"CASH": "BANK_COLLECTION", "SDS": "SDS_TRANSFER_RECEIVED", "SECURITIES": "SECURITIES_TRANSFER_RECEIVED"}


class Receipt(BaseModel):
    component: Literal["CASH", "SDS", "SECURITIES"]
    vdr_id: str | None = Field(default=None, max_length=40)              # CASH: the VDR entry of the demand draft
    ho_reference: str | None = Field(default=None, min_length=3, max_length=60)   # SDS / SECURITIES: Investment Division's reference
    amount_paise: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def complete(self):
        if self.component == "CASH" and not self.vdr_id:
            raise ValueError("a cash receipt names its VDR entry")
        if self.component != "CASH" and not (self.ho_reference and self.amount_paise):
            raise ValueError("an SDS or securities receipt gives the Investment Division's reference and the amount")
        return self


class Proposal(BaseModel):
    statement_total_paise: int = Field(gt=0)                              # Form SE-6
    receipts: list[Receipt] = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=500)


async def position(session, est: str) -> dict[str, Any]:
    """What was credited to the members, what has been received, and what is outstanding."""
    credited = int((await session.execute(text("SELECT COALESCE(SUM(total_paise), 0) FROM past_accumulation_ingestions WHERE establishment_id=:e"),
                                          {"e": est})).scalar_one())
    received = int((await session.execute(text("SELECT COALESCE(SUM(receipts_paise), 0) FROM past_accumulation_reconciliations "
                                               "WHERE establishment_id=:e AND state IN ('RECONCILED', 'SHORT')"), {"e": est})).scalar_one())
    return {"credited_paise": credited, "received_paise": received, "outstanding_paise": credited - received}


def _view(r: Any) -> dict[str, Any]:
    load = lambda v: v if isinstance(v, (list, dict)) else json.loads(v)  # noqa: E731
    return {"reco_id": r["reco_id"], "establishment_id": r["establishment_id"], "statement_total_paise": r["statement_total_paise"],
            "receipts": load(r["receipts"]), "receipts_paise": r["receipts_paise"], "state": r["state"], "summary": load(r["summary"]),
            "proposed_by": r["proposed_by"], "decided_by": r["decided_by"], "note": r["note"],
            "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else r["created_at"]}


@router.get(BASE + "/past-accumulation-vdr-reconciliations")
async def reconciliations(establishment_id: str | None = Query(default=None),
                          actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.apfc", "fo.exemption"))) -> dict:
    async with sessions()() as session:
        ests = (await session.execute(text("SELECT DISTINCT i.establishment_id, e.legal_name FROM past_accumulation_ingestions i "
                                           "JOIN establishments e ON e.id=i.establishment_id ORDER BY i.establishment_id"))).mappings().all()
        out = []
        for e in ests:
            if establishment_id and e["establishment_id"] != establishment_id:
                continue
            rows = (await session.execute(text("SELECT * FROM past_accumulation_reconciliations WHERE establishment_id=:e ORDER BY created_at DESC"),
                                          {"e": e["establishment_id"]})).mappings().all()
            cash = (await session.execute(text("SELECT * FROM vdr_entries WHERE establishment_id=:e AND state='UNRECONCILED' AND instrument IN ('DD','CHEQUE') "
                                               "ORDER BY received_on"), {"e": e["establishment_id"]})).mappings().all()
            out.append({"establishment_id": e["establishment_id"], "legal_name": e["legal_name"], **await position(session, e["establishment_id"]),
                        "unreconciled_receipts": [{"vdr_id": v["vdr_id"], "instrument": v["instrument"], "instrument_ref": v["instrument_ref"],
                                                   "amount_paise": v["amount_paise"], "received_on": str(v["received_on"])} for v in cash],
                        "reconciliations": [_view(r) for r in rows]})
    return envelope(out)


@router.post(BASE + "/{estId}/past-accumulation-vdr-reconciliations", status_code=201)
async def propose(estId: str, body: Proposal, actor: Actor = Depends(require_stakeholder("fo.da_accounts"))) -> dict:
    async with sessions()() as session, session.begin():
        pos = await position(session, estId)
        if pos["credited_paise"] == 0:
            raise Problem(409, "/problems/nothing-credited", "No past accumulations credited for this establishment yet",
                          "The exemption cell ingests the trust's member ledgers first.")
        if (await session.execute(text("SELECT 1 FROM past_accumulation_reconciliations WHERE establishment_id=:e AND state='PROPOSED'"),
                                  {"e": estId})).first():
            raise Problem(409, "/problems/pending", "A reconciliation is awaiting the APFC's decision")
        receipts, seen = [], set()
        for r in body.receipts:
            if r.component == "CASH":
                v = (await session.execute(text("SELECT * FROM vdr_entries WHERE vdr_id=:v"), {"v": r.vdr_id})).mappings().first()
                if not v or v["establishment_id"] != estId or v["state"] != "UNRECONCILED" or r.vdr_id in seen:
                    raise Problem(422, "/problems/validation", f"{r.vdr_id}: choose an unreconciled receipt of this establishment, once")
                seen.add(r.vdr_id)
                receipts.append({"component": "CASH", "vdr_id": r.vdr_id, "reference": f"{v['instrument']} {v['instrument_ref']}",
                                 "amount_paise": int(v["amount_paise"])})
            else:
                key = f"{r.component}:{r.ho_reference}"
                if key in seen or (await session.execute(text("SELECT 1 FROM journals WHERE business_key=:k"), {"k": f"PA-{key}"})).first():
                    raise Problem(409, "/problems/already-received", f"{r.ho_reference} is already accounted for")
                seen.add(key)
                receipts.append({"component": r.component, "reference": r.ho_reference, "amount_paise": r.amount_paise})
        total = sum(x["amount_paise"] for x in receipts)
        if total > pos["outstanding_paise"]:
            raise Problem(422, "/problems/more-than-credited", "The receipts exceed what is outstanding",
                          f"₹{pos['outstanding_paise'] // 100:,} is outstanding for the members credited; ingest the remaining members first.")
        after = pos["outstanding_paise"] - total
        summary = {**pos, "this_receipt_paise": total, "outstanding_after_paise": after,
                   "statement_difference_paise": body.statement_total_paise - pos["credited_paise"]}
        row = {"reco_id": f"PAR-{secrets.token_hex(4).upper()}", "establishment_id": estId, "statement_total_paise": body.statement_total_paise,
               "receipts": json.dumps(receipts), "receipts_paise": total, "state": "PROPOSED", "summary": json.dumps(summary),
               "proposed_by": actor.subject, "note": body.note or None, "created_at": datetime.now(UTC)}
        await session.execute(text("INSERT INTO past_accumulation_reconciliations (reco_id, establishment_id, statement_total_paise, receipts, receipts_paise, "
                                   "state, summary, proposed_by, note, created_at) VALUES (:reco_id, :establishment_id, :statement_total_paise, :receipts, "
                                   ":receipts_paise, :state, :summary, :proposed_by, :note, :created_at)"), row)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="past_accumulation.reco_proposed",
                    target_type="establishment", target_id=estId, detail=f"{row['reco_id']} {total}")
    return envelope(_view({**row, "decided_by": None}))


class Decision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=5, max_length=500)


@router.post(BASE + "/past-accumulation-vdr-reconciliations/{recoId}/approvals")
async def decide(recoId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc"))) -> dict:
    async with sessions()() as session, session.begin():
        r = (await session.execute(text("SELECT * FROM past_accumulation_reconciliations WHERE reco_id=:r"), {"r": recoId})).mappings().first()
        if not r:
            raise Problem(404, "/problems/not-found", "Reconciliation not found")
        if r["state"] != "PROPOSED":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {r['state']}.")
        if r["proposed_by"] == actor.subject:
            raise Problem(403, "/problems/maker-checker", "The officer who proposed cannot approve")
        view = _view(r)
        require_step_up(actor, "approve-pa-reco", recoId, None, r["receipts_paise"])
        if body.decision == "REJECT":
            state = "REJECTED"
        else:
            pos = await position(session, r["establishment_id"])
            if r["receipts_paise"] > pos["outstanding_paise"]:
                raise Problem(409, "/problems/more-than-credited", "The receipts now exceed what is outstanding; reject and propose again")
            for x in view["receipts"]:
                if x["component"] == "CASH":
                    v = (await session.execute(text("SELECT * FROM vdr_entries WHERE vdr_id=:v"), {"v": x["vdr_id"]})).mappings().first()
                    if not v or v["state"] != "UNRECONCILED":
                        raise Problem(409, "/problems/receipt-used", f"{x['vdr_id']} was used or rejected meanwhile; reject and propose again")
                    allocations = [*(v["allocations"] if isinstance(v["allocations"], list) else json.loads(v["allocations"] or "[]")),
                                   {"past_accumulation": recoId, "amount_paise": x["amount_paise"], "at": datetime.now(UTC).isoformat()}]
                    await session.execute(text("UPDATE vdr_entries SET allocated_paise=:a, state='RECONCILED', allocations=:al WHERE vdr_id=:v"),
                                          {"a": x["amount_paise"], "al": json.dumps(allocations), "v": x["vdr_id"]})
                    key = f"PA-CASH:{x['vdr_id']}"
                else:
                    key = f"PA-{x['component']}:{x['reference']}"
                await _post(session, key, "PAST_ACCUMULATION_RECEIPT", None, [
                    {"account_code": ACCOUNT[x["component"]], "side": "debit", "amount_paise": x["amount_paise"]},
                    {"account_code": "TRUST_TRANSFER_RECEIVABLE", "side": "credit", "amount_paise": x["amount_paise"]}])
            after = pos["outstanding_paise"] - r["receipts_paise"]
            state = "RECONCILED" if after == 0 and r["statement_total_paise"] == pos["credited_paise"] else "SHORT"
            view["summary"] = {**view["summary"], "outstanding_after_paise": after}
        await session.execute(text("UPDATE past_accumulation_reconciliations SET state=:s, decided_by=:d, note=:n, summary=:sm WHERE reco_id=:r"),
                              {"s": state, "d": actor.subject, "n": body.note, "sm": json.dumps(view["summary"]), "r": recoId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"past_accumulation.reco_{state.lower()}",
                    target_type="establishment", target_id=r["establishment_id"], detail=f"{recoId}: {body.note}")
    return envelope({**view, "state": state, "decided_by": actor.subject, "note": body.note})
