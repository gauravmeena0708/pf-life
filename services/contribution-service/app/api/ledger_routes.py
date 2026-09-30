"""Phase 2, slice 7b: office ledger work. Receipts outside the challan flow (VDR entries) are recorded by Cash and
allocated to TRRNs by the DA (Accounts) — or rejected; a posted journal is reversed by new reversing entries, never
edited; a rejected transfer-in is recredited to the member ID it came from; Appendix E (CITES manual) adjusts a
member ID's balances with a notesheet, proposed by the DA and approved by the APFC before it is posted."""
import base64
import hashlib
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infra.claims_ledger import _post, member_shares
from app.infra.db import sessions
from app.infra.messaging import handle_payment_confirmed
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "contribution-service"
DA = require_stakeholder("fo.da_accounts")


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _json(v: Any) -> Any:
    import json
    return v if isinstance(v, (list, dict)) or v is None else json.loads(v)


# ── receipts outside the challan flow (VDR) ────────────────────────────────────────────────────────

class VdrInput(BaseModel):
    establishment_id: str = Field(min_length=3, max_length=80)
    instrument: str = Field(pattern="^(CHEQUE|DD|NEFT_UNMATCHED)$")
    instrument_ref: str = Field(min_length=3, max_length=60)
    amount_paise: int = Field(gt=0)
    received_on: date
    remarks: str | None = Field(default=None, max_length=300)


def _vdr(v: Any) -> dict[str, Any]:
    return {"vdr_id": v["vdr_id"], "establishment_id": v["establishment_id"], "instrument": v["instrument"], "instrument_ref": v["instrument_ref"],
            "amount_paise": v["amount_paise"], "allocated_paise": v["allocated_paise"], "unallocated_paise": v["amount_paise"] - v["allocated_paise"],
            "received_on": _iso(v["received_on"]), "state": v["state"], "allocations": _json(v["allocations"]), "remarks": v["remarks"],
            "created_at": _iso(v["created_at"])}


@router.post("/api/v1/office/vdr-entries", status_code=201)
async def record_vdr(body: VdrInput, actor: Actor = Depends(require_stakeholder("fo.cash"))) -> dict:
    if body.received_on > date.today() or body.amount_paise % 100:
        raise Problem(422, "/problems/validation", "Enter a whole-rupee amount and a receipt date not in the future")
    async with sessions()() as session, session.begin():
        if not (await session.execute(text("SELECT 1 FROM establishments WHERE id=:e"), {"e": body.establishment_id})).first():
            raise Problem(404, "/problems/not-found", "Establishment not found")
        require_step_up(actor, "record-vdr", body.instrument_ref, None, body.amount_paise)
        row = {"vdr_id": f"VDR-{secrets.token_hex(4).upper()}", **body.model_dump(), "allocated_paise": 0, "state": "UNRECONCILED",
               "allocations": "[]", "recorded_by": actor.subject, "created_at": datetime.now(UTC)}
        await session.execute(text("INSERT INTO vdr_entries (vdr_id, establishment_id, instrument, instrument_ref, amount_paise, allocated_paise, "
                                   "received_on, state, allocations, remarks, recorded_by, created_at) VALUES (:vdr_id, :establishment_id, :instrument, "
                                   ":instrument_ref, :amount_paise, 0, :received_on, 'UNRECONCILED', :allocations, :remarks, :recorded_by, :created_at)"), row)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vdr.recorded",
                    target_type="vdr_entry", target_id=row["vdr_id"], detail=f"{body.instrument} {body.instrument_ref} {body.amount_paise}")
    return envelope(_vdr({**row, "allocations": []}))


@router.get("/api/v1/office/receipts/unreconciled")
async def unreconciled(actor: Actor = Depends(require_stakeholder("fo.cash", "fo.da_accounts"))) -> dict:
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM vdr_entries WHERE state IN ('UNRECONCILED', 'PARTIAL') ORDER BY received_on"))).mappings().all()
        due = (await session.execute(text("SELECT trrn, establishment_id, total_paise, status, kind FROM challans WHERE status IN ('DUE', 'FAILED') "
                                          "ORDER BY created_at"))).mappings().all()
    return envelope({"receipts": [_vdr(r) for r in rows], "unpaid_challans": [dict(d) for d in due]})


class TrrnAdjustment(BaseModel):
    trrn: str = Field(min_length=5, max_length=17)


@router.post("/api/v1/office/receipts/{receiptId}/trrn-adjustments")
async def trrn_adjustment(receiptId: str, body: TrrnAdjustment, actor: Actor = Depends(DA)) -> dict:
    """Allocate an unallocated receipt against an unpaid TRRN of the same establishment: the challan is paid and
    the return posted exactly as if paid online; the mock bank stops accepting an online payment for it."""
    async with sessions()() as session, session.begin():
        v = (await session.execute(text("SELECT * FROM vdr_entries WHERE vdr_id=:v"), {"v": receiptId})).mappings().first()
        ch = (await session.execute(text("SELECT * FROM challans WHERE trrn=:t"), {"t": body.trrn})).mappings().first()
        if not v:
            raise Problem(404, "/problems/not-found", "Receipt not found")
        if v["state"] not in ("UNRECONCILED", "PARTIAL"):
            raise Problem(409, "/problems/invalid-state", "This receipt is already reconciled or rejected")
        if not ch or ch["establishment_id"] != v["establishment_id"] or ch["status"] not in ("DUE", "FAILED"):
            raise Problem(422, "/problems/validation", "Choose an unpaid TRRN of the same establishment")
        left = v["amount_paise"] - v["allocated_paise"]
        if ch["total_paise"] > left:
            raise Problem(422, "/problems/receipt-too-small", "The receipt does not cover this challan",
                          f"₹{left // 100:,} is unallocated; the challan is ₹{ch['total_paise'] // 100:,}.")
        require_step_up(actor, "adjust-trrn", receiptId, None, ch["total_paise"])
        payment_id = f"{receiptId}-{body.trrn}"
        await handle_payment_confirmed(session, {"correlation_id": actor.correlation_id, "payload": {
            "payment_id": payment_id, "purpose": "CHALLAN", "reference_type": "trrn", "reference_id": body.trrn,
            "amount_paise": ch["total_paise"], "mock": True}})
        allocations = [*_json(v["allocations"]), {"trrn": body.trrn, "amount_paise": ch["total_paise"], "at": datetime.now(UTC).isoformat()}]
        allocated = v["allocated_paise"] + ch["total_paise"]
        state = "RECONCILED" if allocated == v["amount_paise"] else "PARTIAL"
        import json
        await session.execute(text("UPDATE vdr_entries SET allocated_paise=:a, state=:s, allocations=:al WHERE vdr_id=:v"),
                              {"a": allocated, "s": state, "al": json.dumps(allocations), "v": receiptId})
        await add_event(session, producer=PRODUCER, event_type="ChallanStatusChanged.v1", aggregate_type="challan", aggregate_id=body.trrn,
                        correlation_id=actor.correlation_id, payload={"trrn": body.trrn, "status": "SETTLED_OFFLINE",
                                                                      "reason": f"Receipt {receiptId} ({v['instrument']} {v['instrument_ref']})"})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vdr.trrn_adjusted",
                    target_type="vdr_entry", target_id=receiptId, detail=f"{body.trrn} {ch['total_paise']}")
        row = {**dict(v), "allocated_paise": allocated, "state": state, "allocations": allocations}
    return envelope({**_vdr(row), "trrn": body.trrn, "challan": "PAID"})


class Reason(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


@router.post("/api/v1/office/vdr-entries/{vdrId}/rejections")
async def reject_vdr(vdrId: str, body: Reason, actor: Actor = Depends(DA)) -> dict:
    """VDR Rejection: a receipt nothing was allocated from (e.g. a dishonoured cheque) is rejected with a reason."""
    async with sessions()() as session, session.begin():
        v = (await session.execute(text("SELECT * FROM vdr_entries WHERE vdr_id=:v"), {"v": vdrId})).mappings().first()
        if not v:
            raise Problem(404, "/problems/not-found", "Receipt not found")
        if v["state"] != "UNRECONCILED":
            raise Problem(409, "/problems/invalid-state", "Only a receipt with nothing allocated can be rejected", f"State: {v['state']}.")
        require_step_up(actor, "reject-vdr", vdrId)
        await session.execute(text("UPDATE vdr_entries SET state='REJECTED', remarks=:r WHERE vdr_id=:v"), {"r": body.reason, "v": vdrId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vdr.rejected",
                    target_type="vdr_entry", target_id=vdrId, detail=body.reason)
    return envelope({**_vdr({**dict(v), "state": "REJECTED", "remarks": body.reason})})


# ── reversal of a posted journal; recredit of a transfer ───────────────────────────────────────────

REVERSIBLE = {"CONTRIBUTION", "DIRECT_CHALLAN", "APPENDIX_E"}


async def _reverse(session, journal_id: str, reason: str, actor: Actor, reversed_kind: str, reference_id: str) -> dict[str, Any]:
    rows = (await session.execute(text("SELECT account_code, side, amount_paise, account_link_id, share FROM journal_lines WHERE journal_id=:j"),
                                  {"j": journal_id})).mappings().all()
    lines = [{"account_code": r["account_code"], "side": "credit" if r["side"] == "debit" else "debit", "amount_paise": r["amount_paise"],
              **({"account_link_id": r["account_link_id"]} if r["account_link_id"] else {}), **({"share": r["share"]} if r["share"] else {})}
             for r in rows]
    for account in {x["account_link_id"] for x in lines if x.get("account_link_id") and x["side"] == "debit"}:
        shares = await member_shares(session, account)                # never take a member ID below zero
        for share in ("employee", "employer"):
            take = sum(x["amount_paise"] for x in lines if x.get("account_link_id") == account and x["side"] == "debit" and x.get("share") == share)
            if take > shares[share]:
                raise Problem(409, "/problems/balance-already-used", "The member ID no longer holds this amount",
                              f"{account} has ₹{shares[share] // 100:,} of the {share} share; the reversal needs ₹{take // 100:,}.")
    new_id = await _post(session, f"REVERSAL-{journal_id}", "REVERSAL" if reversed_kind != "TRANSFER" else "TRANSFER_RECREDIT", None, lines,
                         reverses=journal_id)
    await add_event(session, producer=PRODUCER, event_type="LedgerReversed.v1", aggregate_type="ledger_journal", aggregate_id=new_id,
                    correlation_id=actor.correlation_id, payload={"journal_id": new_id, "reverses_journal_id": journal_id, "reason": reason,
                                                                  "claim_id": "", "postings": lines, "reversed_kind": reversed_kind,
                                                                  "reference_id": reference_id})
    return {"journal_id": new_id, "reverses_journal_id": journal_id, "lines": lines}


@router.post("/api/v1/office/ledger-journals/{journalId}/reversals")
async def reverse_journal(journalId: str, body: Reason, actor: Actor = Depends(DA)) -> dict:
    async with sessions()() as session, session.begin():
        j = (await session.execute(text("SELECT * FROM journals WHERE id=:j"), {"j": journalId})).mappings().first()
        if not j:
            raise Problem(404, "/problems/not-found", "Journal not found")
        if j["kind"] not in REVERSIBLE:
            raise Problem(422, "/problems/not-reversible", f"A {j['kind'].lower().replace('_', ' ')} journal is not reversed here",
                          "Claims, interest and transfers have their own corrections (claim rejection, rate revision, recredit).")
        if (await session.execute(text("SELECT 1 FROM journals WHERE reverses_journal_id=:j"), {"j": journalId})).first():
            raise Problem(409, "/problems/already-reversed", "This journal is already reversed")
        amount = (await session.execute(text("SELECT COALESCE(SUM(amount_paise), 0) FROM journal_lines WHERE journal_id=:j AND side='credit'"),
                                        {"j": journalId})).scalar_one()
        require_step_up(actor, "reverse-journal", journalId, None, int(amount))
        result = await _reverse(session, journalId, body.reason, actor, j["kind"], j["filing_id"] or journalId)
        if j["kind"] == "CONTRIBUTION" and j["filing_id"]:
            await session.execute(text("UPDATE ecr_filings SET state='REVERSED' WHERE id=:f"), {"f": j["filing_id"]})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="ledger.reversed",
                    target_type="journal", target_id=journalId, detail=body.reason)
    return envelope({**result, "amount_paise": int(amount), "reason": body.reason})


@router.post("/api/v1/office/transfers/{transferId}/recredits")
async def recredit_transfer(transferId: str, body: Reason, actor: Actor = Depends(DA)) -> dict:
    """A transfer-in the receiving office rejected: the balance goes back to the member ID it came from."""
    async with sessions()() as session, session.begin():
        t = (await session.execute(text("SELECT * FROM transfer_postings WHERE transfer_id=:t"), {"t": transferId})).mappings().first()
        if not t or not t["journal_id"]:
            raise Problem(404, "/problems/not-found", "Posted transfer not found")
        if t["recredit_journal_id"]:
            raise Problem(409, "/problems/already-recredited", "This transfer is already recredited")
        amount = int(t["employee_paise"]) + int(t["employer_paise"])
        require_step_up(actor, "recredit-transfer", transferId, None, amount)
        result = await _reverse(session, t["journal_id"], body.reason, actor, "TRANSFER", transferId)
        await session.execute(text("UPDATE transfer_postings SET recredit_journal_id=:j WHERE transfer_id=:t"), {"j": result["journal_id"], "t": transferId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="transfer.recredited",
                    target_type="transfer", target_id=transferId, detail=body.reason)
    return envelope({**result, "transfer_id": transferId, "recredited_to": t["from_account_link_id"], "amount_paise": amount})


# ── Appendix E (CITES manual): four kinds of adjustment, proposed with a notesheet, approved by the APFC ──

class AppendixE(BaseModel):
    type: str = Field(default="APPENDIX_E", pattern="^APPENDIX_E$")
    appendix_type: str = Field(pattern="^(OTHER|INTEREST_ON_RETURNS|EPS_DIVERSION|EXCESS_INTEREST_DEBIT)$")
    account_link_id: str = Field(min_length=3, max_length=80)
    employee_paise: int = 0
    employer_paise: int = 0
    eps_paise: int = 0
    notesheet_no: str = Field(min_length=3, max_length=60)
    notesheet_date: date
    remarks: str = Field(min_length=10, max_length=1000)
    notesheet_pdf_base64: str | None = Field(default=None, max_length=1_400_000)


def _lines(body: AppendixE, shares: dict[str, int]) -> list[dict[str, Any]]:
    """Journal lines for each Appendix E type (CITES): what may be edited, and what balances it."""
    acc, t = body.account_link_id, body.appendix_type
    member = lambda amount, share: {"account_code": "AC01_EPF", "side": "credit" if amount > 0 else "debit",  # noqa: E731
                                    "amount_paise": abs(amount), "account_link_id": acc, "share": share}
    if t == "EPS_DIVERSION":                  # 1.16% on higher wages: from the employer share to EPS, never more than it holds
        if body.employee_paise or body.eps_paise or body.employer_paise <= 0:
            raise Problem(422, "/problems/validation", "EPS diversion moves a positive amount from the employer share only (employer_paise)")
        if body.employer_paise > shares["employer"]:
            raise Problem(422, "/problems/validation", "The amount moved to EPS cannot exceed the employer share")
        return [member(-body.employer_paise, "employer"), {"account_code": "AC10_EPS", "side": "credit", "amount_paise": body.employer_paise}]
    if t in ("INTEREST_ON_RETURNS", "EXCESS_INTEREST_DEBIT"):
        if body.eps_paise:
            raise Problem(422, "/problems/validation", "This Appendix E does not edit the EPS balance")
        if body.employee_paise < 0 or body.employer_paise < 0 or not (body.employee_paise or body.employer_paise):
            raise Problem(422, "/problems/validation", "Enter positive employee / employer amounts")
        sign = 1 if t == "INTEREST_ON_RETURNS" else -1
        if sign < 0 and (body.employee_paise > shares["employee"] or body.employer_paise > shares["employer"]):
            raise Problem(422, "/problems/validation", "The excess interest debited cannot exceed the balance")
        lines = [member(sign * a, s) for a, s in ((body.employee_paise, "employee"), (body.employer_paise, "employer")) if a]
        total = body.employee_paise + body.employer_paise
        return lines + [{"account_code": "INTEREST_SUSPENSE", "side": "debit" if sign > 0 else "credit", "amount_paise": total}]
    # OTHER: employee, employer and EPS balances, each up or down; the difference goes to the office's adjustment account
    if not (body.employee_paise or body.employer_paise or body.eps_paise):
        raise Problem(422, "/problems/validation", "Nothing to adjust")
    if -body.employee_paise > shares["employee"] or -body.employer_paise > shares["employer"]:
        raise Problem(422, "/problems/validation", "A reduction cannot exceed the balance")
    lines = [member(a, s) for a, s in ((body.employee_paise, "employee"), (body.employer_paise, "employer")) if a]
    if body.eps_paise:
        lines.append({"account_code": "AC10_EPS", "side": "credit" if body.eps_paise > 0 else "debit", "amount_paise": abs(body.eps_paise)})
    net = body.employee_paise + body.employer_paise + body.eps_paise
    if net:
        lines.append({"account_code": "ADJUSTMENT_SUSPENSE", "side": "debit" if net > 0 else "credit", "amount_paise": abs(net)})
    return lines


def _adjustment(a: Any) -> dict[str, Any]:
    return {"adjustment_id": a["adjustment_id"], "account_link_id": a["account_link_id"], "uan": a["uan"], "appendix_type": a["appendix_type"],
            "lines": _json(a["lines"]), "notesheet_no": a["notesheet_no"], "notesheet_date": _iso(a["notesheet_date"]), "remarks": a["remarks"],
            "attachment": _json(a["attachment"]), "state": a["state"], "decision_note": a["decision_note"], "journal_id": a["journal_id"],
            "created_at": _iso(a["created_at"])}


@router.post("/api/v1/office/ledger-adjustments", status_code=201)
async def propose_adjustment(body: AppendixE, actor: Actor = Depends(DA)) -> dict:
    import json
    async with sessions()() as session, session.begin():
        m = (await session.execute(text("SELECT uan FROM establishment_members WHERE account_link_id=:a"), {"a": body.account_link_id})).first()
        if not m:
            raise Problem(404, "/problems/not-found", "Member ID not found")
        lines = _lines(body, await member_shares(session, body.account_link_id))
        attachment = None
        if body.notesheet_pdf_base64:
            content = base64.b64decode(body.notesheet_pdf_base64)
            if not content.startswith(b"%PDF") or len(content) > 1_000_000:
                raise Problem(422, "/problems/validation", "Attach the notesheet as a PDF of at most 1 MB")
            attachment = {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
        amount = abs(body.employee_paise) + abs(body.employer_paise) + abs(body.eps_paise)   # what the DA entered, signs aside
        require_step_up(actor, "propose-appendix-e", body.account_link_id, None, amount)
        row = {"adjustment_id": f"APE-{secrets.token_hex(4).upper()}", "account_link_id": body.account_link_id, "uan": m[0],
               "appendix_type": body.appendix_type, "lines": lines, "notesheet_no": body.notesheet_no, "notesheet_date": body.notesheet_date,
               "remarks": body.remarks, "attachment": attachment, "state": "PROPOSED", "proposed_by": actor.subject, "decision_note": None,
               "journal_id": None, "created_at": datetime.now(UTC)}
        await session.execute(text("INSERT INTO ledger_adjustments (adjustment_id, account_link_id, uan, appendix_type, lines, notesheet_no, notesheet_date, "
                                   "remarks, attachment, state, proposed_by, created_at) VALUES (:adjustment_id, :account_link_id, :uan, :appendix_type, "
                                   ":lines, :notesheet_no, :notesheet_date, :remarks, :attachment, 'PROPOSED', :proposed_by, :created_at)"),
                              {**row, "lines": json.dumps(lines), "attachment": json.dumps(attachment) if attachment else None})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="appendix_e.proposed",
                    target_type="member_account", target_id=body.account_link_id, detail=f"{row['adjustment_id']} {body.appendix_type} {body.notesheet_no}")
    return envelope(_adjustment(row))


@router.get("/api/v1/office/ledger-adjustments")
async def list_adjustments(actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.apfc"))) -> dict:
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM ledger_adjustments ORDER BY created_at DESC"))).mappings().all()
    return envelope([_adjustment(r) for r in rows])


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/ledger-adjustments/{adjustmentId}/approvals")
async def approve_adjustment(adjustmentId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc"))) -> dict:
    async with sessions()() as session, session.begin():
        a = (await session.execute(text("SELECT * FROM ledger_adjustments WHERE adjustment_id=:a"), {"a": adjustmentId})).mappings().first()
        if not a:
            raise Problem(404, "/problems/not-found", "Adjustment not found")
        if a["state"] != "PROPOSED":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {a['state']}.")
        lines = _json(a["lines"])
        amount = sum(x["amount_paise"] for x in lines if x["side"] == "credit")
        require_step_up(actor, "approve-appendix-e", adjustmentId, None, amount)
        journal_id = None
        if body.decision == "APPROVE":
            shares = await member_shares(session, a["account_link_id"])      # the balance may have moved since it was proposed
            for share in ("employee", "employer"):
                take = sum(x["amount_paise"] for x in lines if x.get("share") == share and x["side"] == "debit")
                if take > shares[share]:
                    raise Problem(409, "/problems/balance-already-used", "The member ID no longer holds the amount to be reduced")
            journal_id = await _post(session, f"APPENDIX-E-{adjustmentId}", "APPENDIX_E", None, lines)
            await add_event(session, producer=PRODUCER, event_type="LedgerAdjusted.v1", aggregate_type="ledger_journal", aggregate_id=journal_id,
                            correlation_id=actor.correlation_id, payload={"adjustment_id": adjustmentId, "journal_id": journal_id,
                                                                          "account_link_id": a["account_link_id"], "appendix_type": a["appendix_type"],
                                                                          "postings": lines})
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        await session.execute(text("UPDATE ledger_adjustments SET state=:s, decided_by=:d, decision_note=:n, journal_id=:j WHERE adjustment_id=:a"),
                              {"s": state, "d": actor.subject, "n": body.note, "j": journal_id, "a": adjustmentId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"appendix_e.{state.lower()}",
                    target_type="member_account", target_id=a["account_link_id"], detail=f"{adjustmentId}: {body.note}")
    return envelope(_adjustment({**dict(a), "state": state, "decision_note": body.note, "journal_id": journal_id}))
