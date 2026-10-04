"""P2.19c: rectification of erroneous EPS contributions (HO circular WSU/2025/E-961539, 19 Dec 2025; see
app/domain/eps_rectification.py). The DA (Accounts) works it out from the member ID's posted returns and proposes it with
a notesheet; the APFC approves it (one-time code); the ledger moves, the member's PF balance and pension service follow.
Where the PF is with an exempted trust, the money goes to the trust (scenario I) or comes from it (scenario II: the trust
works it out at its own declared rate and remits it; Cash records the receipt)."""
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.domain.ecr import FIELDS, parse
from app.domain.eps_rectification import SCENARIOS, work_out
from app.infra.claims_ledger import _post, member_shares
from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import capped_wages, financial_year, interest_rate_bp, rules_for_wage_month, rules_on, section

router = APIRouter()
PRODUCER = "contribution-service"
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
CIRCULAR = "HO circular WSU/2025/E-961539 (19 Dec 2025)"


class Proposal(BaseModel):
    account_link_id: str = Field(min_length=3, max_length=80)
    scenario: str = Field(pattern="^(WRONGLY_ALLOWED|WRONGLY_DENIED)$")
    from_month: str = Field(pattern=MONTH)
    to_month: str = Field(pattern=MONTH)
    notesheet_no: str = Field(min_length=3, max_length=60)
    remarks: str = Field(min_length=10, max_length=1000)
    trust_rate_bp: int | None = Field(default=None, ge=0, le=2000)   # scenario II with an exempted trust: the trust's declared rate


def _view(r: Any) -> dict[str, Any]:
    import json
    ws = r["worksheet"] if isinstance(r["worksheet"], dict) else json.loads(r["worksheet"])
    return {k: (r[k].isoformat() if hasattr(r[k], "isoformat") else r[k]) for k in (
        "rectification_id", "account_link_id", "uan", "establishment_id", "scenario", "exempted_trust", "from_month", "to_month",
        "total_paise", "notesheet_no", "remarks", "state", "decision_note", "journal_id", "trust_reference", "created_at")} | {
        "worksheet": ws, "scenario_label": SCENARIOS[r["scenario"]], "circular": CIRCULAR}


async def _months(session, establishment_id: str, uan: str, frm: str, to: str) -> list[dict[str, Any]]:
    """The member's rows of the posted returns, month by month."""
    filings = (await session.execute(text(
        "SELECT wage_month, content, format FROM ecr_filings WHERE establishment_id=:e AND state='POSTED' "
        "AND wage_month BETWEEN :f AND :t ORDER BY wage_month, version"), {"e": establishment_id, "f": frm, "t": to})).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for f in filings:
        rows, _, _ = parse(f["content"], f["format"])
        for row in rows:
            if row.get("UAN") != uan:
                continue
            epf, eps, eps_share = (int(row.get(k) or 0) * 100 if str(row.get(k) or "0").isdigit() else 0 for k in (FIELDS[3], FIELDS[4], FIELDS[7]))
            rules = await rules_for_wage_month(session, f["wage_month"])
            c = rules["contribution"]
            ceiling = capped_wages(epf, c, "eps_wage_ceiling_paise") if c.get("ceiling_periods") else c["eps_wage_ceiling_paise"]
            m = out.setdefault(f["wage_month"], {"wage_month": f["wage_month"], "epf_wages_paise": 0, "eps_wages_paise": 0, "eps_paise": 0,
                                                 "ceiling_paise": ceiling, "eps_rate_bp": c["eps_rate_bp"]})
            m["epf_wages_paise"] += epf
            m["eps_wages_paise"] += eps
            m["eps_paise"] += eps_share
    return list(out.values())


@router.post("/api/v1/office/eps-rectifications", status_code=201)
async def propose(body: Proposal, actor: Actor = Depends(require_stakeholder("fo.da_accounts"))) -> dict:
    if body.from_month > body.to_month:
        raise Problem(422, "/problems/validation", "The period starts after it ends")
    import json
    async with sessions()() as session, session.begin():
        m = (await session.execute(text("SELECT uan, establishment_id FROM establishment_members WHERE account_link_id=:a"),
                                   {"a": body.account_link_id})).mappings().first()
        if not m:
            raise Problem(404, "/problems/not-found", "Member ID not found")
        open_case = (await session.execute(text("SELECT rectification_id FROM eps_rectifications WHERE account_link_id=:a "
                                                "AND state IN ('PROPOSED','AWAITING_TRUST_REMITTANCE')"), {"a": body.account_link_id})).scalar_one_or_none()
        if open_case:
            raise Problem(409, "/problems/already-open", "A rectification is already open for this member ID", f"{open_case}.")
        trust = (await session.execute(text("SELECT trust_name FROM exempted_establishments WHERE establishment_id=:e AND pf_exempt "
                                            "AND status='ACTIVE'"), {"e": m["establishment_id"]})).scalar_one_or_none()
        if trust and body.scenario == "WRONGLY_DENIED" and body.trust_rate_bp is None:
            raise Problem(422, "/problems/validation", "Enter the trust's declared rate",
                          "The PF is with the trust: the trust works out the EPS due with interest at its own declared rate.")
        today_rules = await rules_on(session, date.today())
        latest = max((section(today_rules, "interest").get("rates_bp") or {"": 0}).items())[1]

        def rate_for(wage_month: str) -> int:
            if trust and body.scenario == "WRONGLY_DENIED":
                return body.trust_rate_bp or 0
            return interest_rate_bp(today_rules, financial_year(date.fromisoformat(wage_month + "-01"))) or latest
        ws = work_out(await _months(session, m["establishment_id"], m["uan"], body.from_month, body.to_month), body.scenario, date.today(), rate_for)
        if not ws["months"]:
            raise Problem(422, "/problems/nothing-to-rectify", "Nothing to rectify in that period",
                          "No posted return in the period carries EPS for this member ID." if body.scenario == "WRONGLY_ALLOWED"
                          else "Every posted return in the period already carries EPS for this member ID.")
        if body.scenario == "WRONGLY_DENIED" and not trust and ws["total_paise"] > (await member_shares(session, body.account_link_id))["employer"]:
            raise Problem(422, "/problems/balance", "The employer share in the PF does not hold the EPS due with interest")
        # the code confirms the member ID; the amount is worked out here, and the APFC's approval is bound to it
        require_step_up(actor, "propose-eps-rectification", body.account_link_id)
        row = {"rectification_id": f"EPSR-{secrets.token_hex(4).upper()}", "account_link_id": body.account_link_id, "uan": m["uan"],
               "establishment_id": m["establishment_id"], "scenario": body.scenario, "exempted_trust": trust, "from_month": body.from_month,
               "to_month": body.to_month, "worksheet": ws, "total_paise": ws["total_paise"], "notesheet_no": body.notesheet_no,
               "remarks": body.remarks, "state": "PROPOSED", "proposed_by": actor.subject, "decision_note": None, "journal_id": None,
               "trust_reference": None, "created_at": datetime.now(UTC)}
        await session.execute(text(
            "INSERT INTO eps_rectifications (rectification_id, account_link_id, uan, establishment_id, scenario, exempted_trust, from_month, "
            "to_month, worksheet, total_paise, notesheet_no, remarks, state, proposed_by, created_at) VALUES (:rectification_id, "
            ":account_link_id, :uan, :establishment_id, :scenario, :exempted_trust, :from_month, :to_month, :worksheet, :total_paise, "
            ":notesheet_no, :remarks, 'PROPOSED', :proposed_by, :created_at)"), {**row, "worksheet": json.dumps(ws)})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="eps_rectification.proposed",
                    target_type="member_account", target_id=body.account_link_id, detail=f"{row['rectification_id']} {body.scenario} {ws['total_paise']}")
    return envelope(_view(row))


@router.get("/api/v1/office/eps-rectifications")
async def list_rectifications(actor: Actor = Depends(require_stakeholder("fo.da_accounts", "fo.apfc", "fo.cash"))) -> dict:
    async with sessions()() as session:
        rows = (await session.execute(text("SELECT * FROM eps_rectifications ORDER BY created_at DESC"))).mappings().all()
    return envelope([_view(r) for r in rows])


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


async def _load(session, rectification_id: str) -> dict[str, Any]:
    r = (await session.execute(text("SELECT * FROM eps_rectifications WHERE rectification_id=:r"), {"r": rectification_id})).mappings().first()
    if not r:
        raise Problem(404, "/problems/not-found", "Rectification not found")
    return dict(r)


async def _complete(session, r: dict[str, Any], lines: list[dict[str, Any]], kind_key: str, actor: Actor) -> str | None:
    """Post the journal; tell claim-service (the member's PF moved) and pension-service (the service deleted or credited);
    future returns follow the member ID's EPS eligibility."""
    journal_id = await _post(session, f"EPS-RECTIFICATION-{kind_key}-{r['rectification_id']}", "EPS_RECTIFICATION", None, lines)
    if any(x.get("account_link_id") for x in lines):
        await add_event(session, producer=PRODUCER, event_type="LedgerAdjusted.v1", aggregate_type="ledger_journal", aggregate_id=journal_id,
                        correlation_id=actor.correlation_id, payload={"adjustment_id": r["rectification_id"], "journal_id": journal_id,
                                                                      "account_link_id": r["account_link_id"], "appendix_type": "EPS_RECTIFICATION",
                                                                      "postings": lines})
    ws = r["worksheet"] if isinstance(r["worksheet"], dict) else __import__("json").loads(r["worksheet"])
    await add_event(session, producer=PRODUCER, event_type="EpsRectified.v1", aggregate_type="member_account", aggregate_id=r["account_link_id"],
                    correlation_id=actor.correlation_id, payload={
                        "rectification_id": r["rectification_id"], "uan": r["uan"], "account_link_id": r["account_link_id"],
                        "scenario": r["scenario"], "from_month": r["from_month"], "to_month": r["to_month"], "months": len(ws["months"]),
                        "amount_paise": ws["amount_paise"], "interest_paise": ws["interest_paise"], "exempted": bool(r["exempted_trust"])})
    if r["scenario"] == "WRONGLY_ALLOWED":
        await session.execute(text("INSERT INTO eps_ineligible_members (account_link_id, rectification_id, since) VALUES (:a, :r, :d) "
                                   "ON CONFLICT (account_link_id) DO NOTHING"), {"a": r["account_link_id"], "r": r["rectification_id"], "d": date.today()})
    else:
        await session.execute(text("DELETE FROM eps_ineligible_members WHERE account_link_id=:a"), {"a": r["account_link_id"]})
    return journal_id


@router.post("/api/v1/office/eps-rectifications/{rectificationId}/approvals")
async def approve(rectificationId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc"))) -> dict:
    async with sessions()() as session, session.begin():
        r = await _load(session, rectificationId)
        if r["state"] != "PROPOSED":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {r['state']}.")
        if r["proposed_by"] == actor.subject:
            raise Problem(403, "/problems/same-officer", "The officer who worked it out cannot approve it")
        require_step_up(actor, "approve-eps-rectification", rectificationId, None, r["total_paise"])
        total, acc, journal_id, state = r["total_paise"], r["account_link_id"], None, "REJECTED"
        if body.decision == "APPROVE":
            member = {"account_code": "AC01_EPF", "amount_paise": total, "account_link_id": acc, "share": "employer"}
            if r["scenario"] == "WRONGLY_ALLOWED":                # A/c 10 → A/c 1, or → the trust
                lines = [{"account_code": "AC10_EPS", "side": "debit", "amount_paise": total},
                         {**member, "side": "credit"} if not r["exempted_trust"] else
                         {"account_code": "TRUST_PAYABLE", "side": "credit", "amount_paise": total}]
            elif not r["exempted_trust"]:                         # A/c 1 → A/c 10
                if total > (await member_shares(session, acc))["employer"]:
                    raise Problem(409, "/problems/balance-already-used", "The employer share no longer holds the amount")
                lines = [{**member, "side": "debit"}, {"account_code": "AC10_EPS", "side": "credit", "amount_paise": total}]
            else:                                                 # the trust remits; Cash records it
                lines = []
            if lines:
                journal_id = await _complete(session, r, lines, "APPROVAL", actor)
                state = "APPROVED"
            else:
                state = "AWAITING_TRUST_REMITTANCE"
        await session.execute(text("UPDATE eps_rectifications SET state=:s, decided_by=:d, decision_note=:n, journal_id=:j WHERE rectification_id=:r"),
                              {"s": state, "d": actor.subject, "n": body.note, "j": journal_id, "r": rectificationId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"eps_rectification.{body.decision.lower()}",
                    target_type="member_account", target_id=acc, detail=f"{rectificationId}: {body.note}")
    return envelope(_view({**r, "state": state, "decision_note": body.note, "journal_id": journal_id}))


class TrustRemittance(BaseModel):
    reference: str = Field(min_length=4, max_length=80)
    amount_paise: int = Field(gt=0)


@router.post("/api/v1/office/eps-rectifications/{rectificationId}/trust-remittances")
async def trust_remittance(rectificationId: str, body: TrustRemittance, actor: Actor = Depends(require_stakeholder("fo.cash"))) -> dict:
    """Scenario II, exempted: the trust's remittance of the EPS due with interest reaches A/c 10; the service is credited."""
    async with sessions()() as session, session.begin():
        r = await _load(session, rectificationId)
        if r["state"] != "AWAITING_TRUST_REMITTANCE":
            raise Problem(409, "/problems/invalid-state", "Not waiting for the trust", f"State: {r['state']}.")
        if body.amount_paise != r["total_paise"]:
            raise Problem(422, "/problems/amount-mismatch", "The remittance does not match the amount worked out",
                          f"Expected ₹{r['total_paise'] / 100:,.2f}.")
        lines = [{"account_code": "BANK_COLLECTION", "side": "debit", "amount_paise": body.amount_paise},
                 {"account_code": "AC10_EPS", "side": "credit", "amount_paise": body.amount_paise}]
        journal_id = await _complete(session, r, lines, "TRUST", actor)
        await session.execute(text("UPDATE eps_rectifications SET state='APPROVED', journal_id=:j, trust_reference=:t WHERE rectification_id=:r"),
                              {"j": journal_id, "t": body.reference, "r": rectificationId})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="eps_rectification.trust_remittance",
                    target_type="member_account", target_id=r["account_link_id"], detail=f"{rectificationId}: {body.reference}")
    return envelope(_view({**r, "state": "APPROVED", "journal_id": journal_id, "trust_reference": body.reference}))
