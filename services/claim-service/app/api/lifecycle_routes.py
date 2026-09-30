"""Phase 2, slice 5a: the rest of a claim's life — the member's pre-flight check for one form, documents,
cancellation before a decision and audit trail; the Claim Approval Docket (CAD) each scrutinising officer generates, payment scrolls
with return reconciliation, audit trail and the forms filed with a claim."""
import base64
import hashlib
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import (MEMBER, _instruct, claim_view, db, ensure_not_frozen, load_claim, member_accounts, previous_claims,
                            staff_office, transition, work_out_tax)
from app.domain.claims import CANCELLABLE, eligibility
from app.infra.tables import accounts, cads, claim_documents, claims, payment_scrolls, tax_declarations
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
PRODUCER = "claim-service"
STATIC_DATA_VERSION = "cad-static-2026.09"
BANK_BRANCHES = {"DEMO0000001": "Demo Bank, Connaught Place", "DEMO0000002": "Demo Bank, Karol Bagh", "DEMO0000004": "Demo Bank, Saket",
                 "DEMO0000006": "Demo Bank, Dwarka", "DEMO0000007": "Demo Bank, Rohini", "UBIN0822124": "Union Bank (synthetic entry)"}
OFFICE_READERS = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic", "fo.cash", "fo.fa_accounts",
                                     "zo.rpfc1_audit", "ho.audit")
CASHIER = require_stakeholder("fo.cash")
TERMINAL = {"SETTLED", "REJECTED_WITH_REASON", "CANCELLED"}


def iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


# ── member ─────────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/members/me/claims/eligibility-preview")
async def eligibility_preview(formType: str = Query(pattern="^(31|19|10C)$"), actor: Actor = Depends(MEMBER),
                              session: AsyncSession = Depends(db)) -> dict:
    """Pre-flight for one form: for each member ID, each claim type of that form — eligible or not, the maximum,
    and why not."""
    today = date.today()
    rules = await rules_on(session, today)
    out = []
    for a in await member_accounts(session, actor.subject):
        blockers = (["ACCOUNT_FROZEN"] if a["frozen"] else []) + (["BALANCE_EMPTY"] if a["employee_paise"] + a["employer_paise"] <= 0 else [])
        types = [{k: v for k, v in eligibility(a, t, rules, today, await previous_claims(session, a["account_link_id"], t)).items() if k != "trace"}
                 for t, spec in rules["claims"]["types"].items() if spec.get("form_type") == formType and not spec.get("retired")]
        out.append({"account_link_id": a["account_link_id"], "blockers": blockers, "types": types})
    return envelope({"form_type": formType, "rule_version": rules["rule_version"], "accounts": out,
                     "note": "No claim type of this form is offered." if all(not x["types"] for x in out) else None})


class DocumentInput(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(pattern="^(application/pdf|image/jpeg|image/png)$")
    content_base64: str = Field(min_length=4, max_length=1_400_000)


@router.post("/api/v1/members/me/claims/{claim_id}/documents", status_code=201)
async def upload_document(claim_id: str, body: DocumentInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except ValueError as exc:
        raise Problem(422, "/problems/validation", "The file is not valid base64") from exc
    if len(content) > 1_000_000:
        raise Problem(413, "/problems/too-large", "The file is larger than 1 MB")
    magic = {"application/pdf": b"%PDF", "image/jpeg": b"\xff\xd8", "image/png": b"\x89PNG"}[body.content_type]
    if not content.startswith(magic):
        raise Problem(422, "/problems/validation", "The file content does not match its type")
    async with session.begin():
        claim = await load_claim(session, claim_id, member=actor.subject)
        if claim["state"] in TERMINAL:
            raise Problem(409, "/problems/invalid-state", "Documents cannot be added to a closed claim")
        doc = {"doc_id": f"DOC-{secrets.token_hex(4).upper()}", "claim_id": claim_id, "filename": body.filename, "content_type": body.content_type,
               "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "content": content}
        await session.execute(insert(claim_documents).values(**doc))
    return envelope({k: v for k, v in doc.items() if k != "content"})


@router.post("/api/v1/members/me/claims/{claim_id}/cancellations")
async def cancel(claim_id: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        claim = await load_claim(session, claim_id, member=actor.subject, lock=True)
        if claim["state"] not in CANCELLABLE:
            raise Problem(409, "/problems/not-cancellable", "This claim can no longer be withdrawn",
                          "A claim can be withdrawn only before an approving officer decides on it.")
        require_step_up(actor, "cancel-claim", claim_id)
        claim = await transition(session, claim, "CANCELLED", "member", "You withdrew the claim.", reason="MEMBER_CANCELLED")
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.cancelled",
                    target_type="claim", target_id=claim_id)
        view = await claim_view(session, claim)
    return envelope(view)


@router.get("/api/v1/members/me/claims/{claim_id}/audit-trail")
async def member_trail(claim_id: str, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    claim = await load_claim(session, claim_id, member=actor.subject)
    view = await claim_view(session, claim)
    return envelope({"claim_id": claim_id, "rule_version": claim["rule_version"], "events": view["timeline"],
                     "note": "Officers are shown by role, never by name."})


# ── office: CAD ──────────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/office/system/cad-static-data")
async def cad_static(actor: Actor = Depends(OFFICE_READERS), session: AsyncSession = Depends(db)) -> dict:
    rules = await rules_on(session, date.today())
    return envelope({"version": STATIC_DATA_VERSION, "loaded": True, "interest_rates_bp": section(rules, "interest")["rates_bp"],
                     "tds": {k: v for k, v in section(rules, "tds").items()}, "rule_version": rules["rule_version"],
                     "bank_branch_master": {"version": "ifsc-demo-2026.09", "branches": len(BANK_BRANCHES)}})


def _cad(c: Any) -> dict[str, Any]:
    return {"cad_id": c["cad_id"], "claim_id": c["claim_id"], "generated_by_role": c.get("officer_role"), "gross_paise": c["gross_paise"],
            "interest_paise": c["interest_paise"], "tds_paise": c["tds_paise"], "net_paise": c["net_paise"], "tax_basis": c["tax"]["basis"],
            "rule_version": c["rule_version"], "static_data_version": c["static_data_version"], "created_at": iso(c["created_at"])}


REVIEWERS = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic")
IN_REVIEW = ("UNDER_REVIEW", "RECOMMENDED", "AWAITING_NEXT_APPROVAL")


@router.post("/api/v1/office/claims/{claim_id}/cad", status_code=201)
async def generate_cad(claim_id: str, actor: Actor = Depends(REVIEWERS), session: AsyncSession = Depends(db)) -> dict:
    """Claim Approval Docket (CITES manuals): the initiator generates it, and every verifier and the approver
    generates it again before acting — gross, interest in it, TDS and net payable, with the rule and static-data
    versions. The work queue refuses an officer's action without a docket of their own since the last action."""
    async with session.begin():
        claim = await load_claim(session, claim_id, office=await staff_office(session, actor), lock=True)
        if claim["state"] not in IN_REVIEW:
            raise Problem(409, "/problems/invalid-state", "A docket is generated while the claim is being scrutinised", f"State: {claim['state']}.")
        account = (await session.execute(select(accounts).where(accounts.c.account_link_id == claim["account_link_id"]))).mappings().one()
        tax = await work_out_tax(session, claim, date.today())
        balance = account["employee_paise"] + account["employer_paise"] + (claim["amount_paise"] if claim["debit_journal_id"] else 0)
        interest = claim["amount_paise"] * account["interest_paise"] // balance if balance else 0
        if claim["claim_type"] in ("PENSION_WITHDRAWAL", "DEATH_EDLI"):          # paid from the EPS / EDLI fund, not the PF balance
            interest = 0
        row = {"cad_id": f"CAD-{secrets.token_hex(4).upper()}", "claim_id": claim_id, "officer_role": actor.stakeholder,
               "gross_paise": claim["amount_paise"], "interest_paise": interest, "tds_paise": tax["tds_paise"], "net_paise": tax["net_paise"],
               "tax": tax, "rule_version": tax["rule_version"], "static_data_version": STATIC_DATA_VERSION, "created_by": actor.subject}
        await session.execute(insert(cads).values(**row, created_at=datetime.now(UTC)))
        await add_event(session, producer=PRODUCER, event_type="CADGenerated.v1", aggregate_type="claim", aggregate_id=claim_id,
                        correlation_id=actor.correlation_id, payload={"claim_id": claim_id, "cad_id": row["cad_id"], "net_payable_paise": row["net_paise"],
                                                                      "tds_paise": row["tds_paise"], "rule_version": row["rule_version"],
                                                                      "static_data_version": STATIC_DATA_VERSION, "officer_role": actor.stakeholder})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.cad_generated",
                    target_type="claim", target_id=claim_id, detail=row["cad_id"])
    return envelope(_cad({**row, "created_at": datetime.now(UTC)}))


@router.get("/api/v1/office/claims/{claim_id}/cad")
async def view_cad(claim_id: str, actor: Actor = Depends(OFFICE_READERS), session: AsyncSession = Depends(db)) -> dict:
    await load_claim(session, claim_id, office=await staff_office(session, actor))
    rows = (await session.execute(select(cads).where(cads.c.claim_id == claim_id).order_by(cads.c.created_at, cads.c.cad_id))).mappings().all()
    if not rows:
        raise Problem(404, "/problems/not-found", "No Claim Approval Docket for this claim yet")
    return envelope({**_cad(rows[-1]), "versions": [_cad(r) for r in rows]})


# ── office: payment scrolls ────────────────────────────────────────────────────────────────────

class ScrollInput(BaseModel):
    demo_scenario: str = Field(default="SUCCESS", pattern="^(SUCCESS|RETURN)$")


async def _ready(session: AsyncSession, office: str) -> list[dict[str, Any]]:
    """Approved claims of the office whose ledger debit is posted and whose account is not frozen."""
    ready = [dict(r) for r in (await session.execute(select(claims).where(
        claims.c.office_id == office, claims.c.state.in_(("APPROVED", "AUTO_APPROVED")), claims.c.debit_journal_id.is_not(None))
        .order_by(claims.c.created_at))).mappings().all()]
    frozen = set((await session.execute(select(accounts.c.account_link_id).where(accounts.c.frozen.is_(True)))).scalars())
    return [c for c in ready if c["account_link_id"] not in frozen]


@router.get("/api/v1/office/payment-scrolls/ready")
async def scroll_ready(actor: Actor = Depends(CASHIER), session: AsyncSession = Depends(db)) -> dict:
    ready = await _ready(session, await staff_office(session, actor))
    return envelope({"claims": [{"claim_id": c["claim_id"], "amount_paise": c["amount_paise"]} for c in ready],
                     "total_paise": sum(c["amount_paise"] for c in ready)})


@router.post("/api/v1/office/payment-scrolls", status_code=201)
async def payment_scroll(body: ScrollInput, actor: Actor = Depends(CASHIER), session: AsyncSession = Depends(db)) -> dict:
    """Every approved claim of the office whose debit is posted goes to the bank in one scroll."""
    async with session.begin():
        office = await staff_office(session, actor)
        ready = await _ready(session, office)
        total = sum(c["amount_paise"] for c in ready)
        if not ready:
            raise Problem(409, "/problems/nothing-to-pay", "No approved claim is waiting for payment")
        scroll_id = f"SCR-{secrets.token_hex(4).upper()}"
        require_step_up(actor, "generate-scroll", office, None, total)
        paid = []
        for c in ready:
            await ensure_not_frozen(session, c, 409)
            paid.append(await _instruct(session, c, actor, body.demo_scenario, None))
        await session.execute(insert(payment_scrolls).values(scroll_id=scroll_id, office_id=office, claim_ids=[c["claim_id"] for c in ready],
                                                             total_paise=total, created_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="PaymentScrollGenerated.v1", aggregate_type="payment_scroll", aggregate_id=scroll_id,
                        correlation_id=actor.correlation_id, payload={"scroll_id": scroll_id, "claim_ids": [c["claim_id"] for c in ready], "total_paise": total})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.scroll_generated",
                    target_type="payment_scroll", target_id=scroll_id, detail=f"{len(ready)} claims")
    return envelope({"scroll_id": scroll_id, "claims": len(ready), "total_paise": total, "net_paise": sum(p["net_paise"] for p in paid)})


@router.post("/api/v1/office/payment-scrolls/{scroll_id}/return-reconciliations")
async def reconcile_scroll(scroll_id: str, actor: Actor = Depends(CASHIER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await staff_office(session, actor)
        scroll = (await session.execute(select(payment_scrolls).where(payment_scrolls.c.scroll_id == scroll_id))).mappings().first()
        if not scroll or scroll["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Scroll not found")
        require_step_up(actor, "reconcile-scroll", scroll_id, None, scroll["total_paise"])
        rows = (await session.execute(select(claims.c.claim_id, claims.c.state, claims.c.amount_paise).where(claims.c.claim_id.in_(scroll["claim_ids"])))).all()
        result = {"paid": [c for c, s, _ in rows if s == "SETTLED"],
                  "returned": [c for c, s, _ in rows if s in ("PAYMENT_RETURNED", "CORRECTION_PENDING", "REISSUE_APPROVED")],
                  "pending": [c for c, s, _ in rows if s == "PAYMENT_PENDING"], "reconciled_at": datetime.now(UTC).isoformat()}
        result["returned_paise"] = sum(a for c, _, a in rows if c in result["returned"])
        result["note"] = ("Returned claims are open for re-settlement: the member gives a new bank account and an APFC approves the re-payment."
                          if result["returned"] else "Nothing returned.")
        await session.execute(update(payment_scrolls).where(payment_scrolls.c.scroll_id == scroll_id).values(reconciliation=result))
    return envelope({"scroll_id": scroll_id, **result})


# ── office: audit trail and the forms filed with a claim ─────────────────────────────────────────

async def _office_claim(session: AsyncSession, claim_id: str, actor: Actor) -> dict[str, Any]:
    if actor.stakeholder in ("zo.rpfc1_audit", "ho.audit"):              # auditors see any office
        return await load_claim(session, claim_id)
    return await load_claim(session, claim_id, office=await staff_office(session, actor))


@router.get("/api/v1/office/claims/{claim_id}/audit-trail")
async def office_trail(claim_id: str, actor: Actor = Depends(OFFICE_READERS), session: AsyncSession = Depends(db)) -> dict:
    claim = await _office_claim(session, claim_id, actor)
    view = await claim_view(session, claim)
    cad = (await session.execute(select(cads).where(cads.c.claim_id == claim_id).order_by(cads.c.created_at.desc(), cads.c.cad_id)
                                 .limit(1))).mappings().first()
    await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="claim.audit_trail_viewed",
                target_type="claim", target_id=claim_id)
    await session.commit()
    return envelope({"claim_id": claim_id, "member_account": claim["account_link_id"], "claim_type": claim["claim_type"], "form_type": claim["form_type"],
                     "amount_paise": claim["amount_paise"], "state": claim["state"], "rule_version": claim["rule_version"],
                     "evaluation": claim["evaluation"], "transitions": [{**t, "role": t["by"]} for t in view["timeline"]],
                     "payments": {"attempts": claim["payment_attempt"], "last_payment_id": claim["payment_id"], "tax": claim.get("tax")},
                     "cad": _cad(cad) if cad else None,
                     "note": "Officer identities are kept with each case decision in the work queue (workflow-service)."})


@router.get("/api/v1/office/claims/{claim_id}/additional-forms")
async def additional_forms(claim_id: str, actor: Actor = Depends(OFFICE_READERS), session: AsyncSession = Depends(db)) -> dict:
    claim = await _office_claim(session, claim_id, actor)
    docs = (await session.execute(select(claim_documents).where(claim_documents.c.claim_id == claim_id).order_by(claim_documents.c.uploaded_at))).mappings().all()
    declared = (await session.execute(select(tax_declarations).where(tax_declarations.c.member_subject == claim["member_subject"]))).mappings().all()
    forms = [{"form_type": "DOCUMENT", "reference": d["doc_id"], "detail": f"{d['filename']} ({d['size_bytes']} bytes, sha256 {d['sha256'][:12]}…)",
              "filed": iso(d["uploaded_at"]), "status": "RECEIVED"} for d in docs]
    forms += [{"form_type": f"FORM_{t['form']}", "reference": f"{t['form']}-{t['financial_year']}", "detail": f"No-tax declaration for {t['financial_year']}",
               "filed": iso(t["submitted_at"]), "status": "ON_FILE"} for t in declared]
    return envelope({"claim_id": claim_id, "forms": forms})

