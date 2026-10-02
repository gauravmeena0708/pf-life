"""compliance-service (Phase 2, slice 8a): compliance cases opened by the DA (Compliance) against an establishment —
not filing, not paying, damages — searched and read by the office; the published defaulter list; and VISHWAS, the
settlement of disputed 14B damages: the employer applies over its open 14B demands, the APFC decides, and an
approval replaces them with one revised demand (DemandRaised.v1 to contribution-service). Illustrative throughout."""
import json
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import compliance_cases, demands, establishments, office_staff, vishwas_applications
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import baseline, section

router = APIRouter()
PRODUCER = "compliance-service"
CASE_OFFICERS = require_stakeholder("fo.da_compliance", "fo.ss", "fo.apfc", "fo.oic", "do.staff")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _office(session: AsyncSession, actor: Actor) -> str:
    office = (await session.execute(select(office_staff.c.office_id).where(office_staff.c.subject == actor.subject))).scalar_one_or_none()
    if not office:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return office


async def _names(session: AsyncSession) -> dict[str, str]:
    return dict((await session.execute(select(establishments.c.establishment_id, establishments.c.legal_name))).all())


def _case(c: Any, names: dict[str, str]) -> dict[str, Any]:
    return {"case_id": c["case_id"], "establishment_id": c["establishment_id"], "legal_name": names.get(c["establishment_id"]),
            "office_id": c["office_id"], "kind": c["kind"], "wage_months": c["wage_months"], "amount_paise": c["amount_paise"],
            "state": c["state"], "history": c["history"], "opened_at": _iso(c["created_at"])}


# ── compliance cases ────────────────────────────────────────────────────────────────────────────

class CaseInput(BaseModel):
    establishment_id: str = Field(min_length=3, max_length=40)
    kind: str = Field(pattern="^(NON_FILING|NON_PAYMENT|LATE_PAYMENT_DAMAGES|OTHER|INQUIRY_7A|INQUIRY_14B)$")
    wage_months: list[str] = Field(default_factory=list, max_length=60)
    amount_paise: int = Field(default=0, ge=0)
    note: str = Field(min_length=10, max_length=1000)
    dispute: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    inspection_id: str | None = None
    contributory_uans: int | None = None
    oic_approval: str | None = None
    demand_ids: list[str] | None = None        # INQUIRY_14B: the auto-calculated demands the notice covers


@router.post("/api/v1/office/compliance/cases", status_code=201)
async def open_case(body: CaseInput, actor: Actor = Depends(require_stakeholder("fo.da_compliance", "fo.ss")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        if body.kind == "INQUIRY_14B":
            if actor.stakeholder != "fo.da_compliance" or body.contributory_uans is None:
                raise Problem(422, "/problems/validation", "The DA drafts the 14B notice with the contributory UANs of the last month of default")
            from app.api.proceedings_b import register_14b
            return envelope(await register_14b(body.establishment_id, body.demand_ids or [], body.contributory_uans, body.note, actor, session))
        if body.kind == "INQUIRY_7A":
            from app.api.proceedings import InquiryInput, register
            if body.dispute is None or body.period_from is None or body.period_to is None or body.contributory_uans is None:
                raise Problem(422, "/problems/validation", "Dispute, period and contributory UANs are required")
            inquiry_body = InquiryInput(**body.model_dump(exclude_none=True))
            return envelope(await register(inquiry_body, actor, session))
        if actor.stakeholder != "fo.da_compliance":
            raise Problem(403, "/problems/role", "Only DA Compliance opens this kind of case")
        office = await _office(session, actor)
        if any(len(m) != 7 or m[4] != "-" for m in body.wage_months):
            raise Problem(422, "/problems/validation", "Wage months are written YYYY-MM")
        open_same = (await session.execute(select(compliance_cases.c.case_id).where(
            compliance_cases.c.establishment_id == body.establishment_id, compliance_cases.c.kind == body.kind,
            compliance_cases.c.state == "OPEN"))).scalar_one_or_none()
        if open_same:
            raise Problem(409, "/problems/case-open", "A case of this kind is already open for the establishment", f"Case {open_same}.",
                          case_id=open_same)
        now = datetime.now(UTC)
        row = {"case_id": f"CMP-{secrets.token_hex(4).upper()}", "establishment_id": body.establishment_id, "office_id": office, "kind": body.kind,
               "wage_months": sorted(body.wage_months), "amount_paise": body.amount_paise, "state": "OPEN",
               "history": [{"at": now.isoformat(), "by_role": actor.stakeholder, "action": "OPENED", "note": body.note}],
               "opened_by": actor.subject, "created_at": now}
        await session.execute(insert(compliance_cases).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="compliance.case_opened",
                    target_type="establishment", target_id=body.establishment_id, detail=f"{row['case_id']} {body.kind}")
        names = await _names(session)
    return envelope(_case(row, names))


@router.get("/api/v1/office/compliance/cases")
async def search_cases(type: str | None = Query(default=None), status: str | None = Query(default=None),
                       actor: Actor = Depends(CASE_OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    q = select(compliance_cases).where(compliance_cases.c.office_id == office).order_by(compliance_cases.c.created_at.desc())
    if type:
        q = q.where(compliance_cases.c.kind == type)
    if status:
        q = q.where(compliance_cases.c.state == status)
    names = await _names(session)
    return envelope([_case(c, names) for c in (await session.execute(q)).mappings().all()])


@router.get("/api/v1/office/compliance/cases/{caseId}")
async def get_case(caseId: str, actor: Actor = Depends(CASE_OFFICERS), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    c = (await session.execute(select(compliance_cases).where(compliance_cases.c.case_id == caseId))).mappings().first()
    if not c or c["office_id"] != office:
        raise Problem(404, "/problems/not-found", "Case not found")
    names = await _names(session)
    open_demands = (await session.execute(select(demands).where(demands.c.establishment_id == c["establishment_id"],
                                                                demands.c.state == "OPEN"))).mappings().all()
    detail = {**_case(c, names), "open_demands": [dict(d) for d in open_demands]}
    if c["kind"].startswith("INQUIRY_"):                           # the inquiry behind the case (7A, 7C, 14B), with its history
        from app.api.proceedings import case_actions, inquiry, inquiry_view
        detail["inquiry"] = {**inquiry_view(await inquiry(session, caseId)), "actions": await case_actions(session, caseId)}
    return envelope(detail)


@router.get("/api/v1/public/defaulting-establishments")
async def defaulters(actor: Actor = Depends(require_stakeholder("public", "gov.mole")), session: AsyncSession = Depends(db)) -> dict:
    """The published list: establishments with an open case for not filing or not paying. Synthetic."""
    rows = (await session.execute(select(compliance_cases).where(compliance_cases.c.state == "OPEN",
                                                                 compliance_cases.c.kind.in_(("NON_FILING", "NON_PAYMENT")))
                                  .order_by(compliance_cases.c.created_at))).mappings().all()
    names = await _names(session)
    out: dict[str, dict[str, Any]] = {}
    for c in rows:
        e = out.setdefault(c["establishment_id"], {"establishment_id": c["establishment_id"], "legal_name": names.get(c["establishment_id"]),
                                                   "office_id": c["office_id"], "defaults": [], "since": _iso(c["created_at"])[:10]})
        e["defaults"].append({"kind": c["kind"], "wage_months": c["wage_months"]})
    return envelope({"establishments": list(out.values()), "label": "SYNTHETIC_DEMO",
                     "note": "Establishments with an open case for not filing returns or not paying dues (synthetic data)."})


# ── VISHWAS: settling disputed 14B damages ─────────────────────────────────────────────────────

class VishwasInput(BaseModel):
    demand_ids: list[str] = Field(min_length=1, max_length=50)
    declaration: bool


def _application(a: Any) -> dict[str, Any]:
    return {"application_id": a["application_id"], "establishment_id": a["establishment_id"], "demand_ids": a["demand_ids"],
            "damages_paise": a["damages_paise"], "revised_paise": a["revised_paise"], "state": a["state"],
            "decision_note": a["decision_note"], "created_at": _iso(a["created_at"])}


def today() -> date:
    return date.today()


def _terms() -> dict[str, Any]:
    return section(baseline(), "vishwas")


ARREARS = re.compile(r"late on ₹([\d,]+)")


def _due(wage_month: str, due_day: int) -> date | None:
    """The day a wage month's contributions were due (the due day of the next month)."""
    if not re.fullmatch(r"\d{4}-\d{2}", wage_month or ""):
        return None
    y, m = int(wage_month[:4]), int(wage_month[5:7])
    return date(y + m // 12, m % 12 + 1, due_day)


def _defaults(d: dict[str, Any], bands: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The defaults a 14B demand is for, each with its wage month, days late and the amount paid late. An automatic demand
    records the amount in its working ("… days late on ₹4,175 …"); a damages order lists its defaults with the automatic
    damages at the band's yearly rate, from which the amount is worked back. None when it cannot be known."""
    working = d.get("working") or ""
    if working.startswith("["):
        out = []
        for x in json.loads(working):
            days, auto = int(x.get("days_late") or 0), int(x.get("auto_paise") or 0)
            if days <= 0 or auto <= 0:
                return None
            months = (days + 29) // 30
            rate = next(b["rate_bp_pa"] for b in bands if b["upto_months"] is None or months <= b["upto_months"])
            out.append({"wage_month": x.get("wage_month"), "days_late": days,
                        "arrears_paise": (auto * 365 * 10000 // (rate * days) + 50) // 100 * 100})
        return out or None
    found = ARREARS.search(working)
    if not found:
        return None
    return [{"wage_month": d.get("wage_month"), "days_late": int(d.get("days_late") or 0),
             "arrears_paise": int(found.group(1).replace(",", "")) * 100}]


def vishwas_terms(d: dict[str, Any], open_7q: set[str], terms: dict[str, Any], late: dict[str, Any], today: date) -> dict[str, Any]:
    """One 14B demand under VISHWAS, 2026: eligible or why not, and the damages recalculated for each default at the
    monthly rate for its length (arrears x rate x days x 12 / 365), never more than the damages levied."""
    why = []
    if not date.fromisoformat(terms["open_from"]) <= today <= date.fromisoformat(terms["open_until"]):
        why.append(f"{terms['scheme']} is open from {terms['open_from']} to {terms['open_until']}.")
    lines = _defaults(d, late["damages_14b_bands"])
    if lines is None:
        why.append("The amount paid late is not on record for this demand.")
        lines = []
    cutoff = date.fromisoformat(terms["defaults_before"])
    if any((_due(x["wage_month"] or "", late["due_day"]) or cutoff) >= cutoff for x in lines):
        why.append(f"Only defaults before {terms['defaults_before']} are covered.")
    if (d.get("trrn") or "-") in open_7q or any(x["wage_month"] in open_7q for x in lines):
        why.append("Pay the 7Q interest on this default first.")
    revised = 0
    for x in lines:
        months = x["days_late"] * 12 / 365
        rate = next(b["rate_bp_pm"] for b in terms["rate_bands"] if ("months_upto" in b and months <= b["months_upto"])
                    or ("months_below" in b and months < b["months_below"]) or not ({"months_upto", "months_below"} & b.keys()))
        x.update(months_of_default=round(months, 1), rate_pct_per_month=rate / 100,
                 revised_paise=x["arrears_paise"] * rate * x["days_late"] * 12 // (10000 * 365) // 100 * 100)
        revised += x["revised_paise"]
    first = lines[0] if lines else {}
    return {"demand_id": d["demand_id"], "eligible": not why, "reasons": why, "damages_paise": int(d["amount_paise"]),
            "defaults": lines, "arrears_paise": sum(x["arrears_paise"] for x in lines),
            "months_of_default": first.get("months_of_default", 0), "rate_pct_per_month": first.get("rate_pct_per_month", 0),
            "revised_paise": min(int(d["amount_paise"]), revised) if not why else None}


async def _assess(session: AsyncSession, establishment_id: str, demand_ids: list[str] | None = None) -> list[dict[str, Any]]:
    rows = (await session.execute(select(demands).where(demands.c.establishment_id == establishment_id, demands.c.kind == "DAMAGES_14B",
                                                        demands.c.state == "OPEN"))).mappings().all()
    open_7q: set[str] = set()                       # the TRRNs and wage months with 7Q interest still owed
    for r in (await session.execute(select(demands.c.trrn, demands.c.wage_month, demands.c.working).where(
            demands.c.establishment_id == establishment_id, demands.c.kind == "INTEREST_7Q", demands.c.state == "OPEN"))).all():
        open_7q |= {x for x in (r[0], r[1]) if x and x != "-"}
        if (r[2] or "").startswith("["):
            open_7q |= {x.get("wage_month") for x in json.loads(r[2]) if x.get("wage_month")}
    terms, late = _terms(), section(baseline(), "late_payment")
    return [vishwas_terms(dict(d), open_7q, terms, late, today()) for d in rows if demand_ids is None or d["demand_id"] in demand_ids]


@router.post("/api/v1/employers/me/vishwas-applications", status_code=201)
async def apply(body: VishwasInput, actor: Actor = Depends(require_stakeholder("employer.signatory")), session: AsyncSession = Depends(db)) -> dict:
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment selected")
    if not body.declaration:
        raise Problem(422, "/problems/validation", "Accept the declaration to apply")
    async with session.begin():
        rows = (await session.execute(select(demands).where(demands.c.demand_id.in_(body.demand_ids)))).mappings().all()
        if len(rows) != len(set(body.demand_ids)) or any(d["establishment_id"] != actor.establishment_id or d["kind"] != "DAMAGES_14B"
                                                         or d["state"] != "OPEN" for d in rows):
            raise Problem(422, "/problems/validation", "Choose open 14B damages demands of your establishment",
                          "7Q interest is not covered; a demand already settled cannot be included.")
        pending = (await session.execute(select(vishwas_applications.c.demand_ids).where(
            vishwas_applications.c.establishment_id == actor.establishment_id, vishwas_applications.c.state == "SUBMITTED"))).scalars().all()
        if any(d in ids for ids in pending for d in body.demand_ids):
            raise Problem(409, "/problems/already-applied", "A demand is already in an application under decision")
        assessed = await _assess(session, actor.establishment_id, list(body.demand_ids))
        refused = [a for a in assessed if not a["eligible"]]
        if refused:
            raise Problem(422, "/problems/not-eligible", f"Not eligible under {_terms()['scheme']}",
                          "; ".join(f"{a['demand_id']}: {' '.join(a['reasons'])}" for a in refused))
        damages = sum(int(d["amount_paise"]) for d in rows)
        row = {"application_id": f"VIS-{secrets.token_hex(4).upper()}", "establishment_id": actor.establishment_id, "demand_ids": list(body.demand_ids),
               "damages_paise": damages, "revised_paise": None, "state": "SUBMITTED", "submitted_by": actor.subject, "decision_note": None,
               "created_at": datetime.now(UTC)}
        await session.execute(insert(vishwas_applications).values(**row))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vishwas.applied",
                    target_type="establishment", target_id=actor.establishment_id, detail=f"{row['application_id']} {damages}")
    return envelope({**_application(row), "estimated_settlement_paise": sum(a["revised_paise"] for a in assessed), "assessment": assessed,
                     "note": f"{_terms()['scheme']}: on approval the recalculated damages are payable as one revised demand; the rest is waived. "
                             "You have undertaken not to pursue any further appeal on these damages."})


@router.get("/api/v1/employers/me/vishwas-applications")
async def my_applications(actor: Actor = Depends(require_stakeholder("employer.owner", "employer.signatory", "employer.operator")),
                          session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(vishwas_applications).where(vishwas_applications.c.establishment_id == (actor.establishment_id or ""))
                                  .order_by(vishwas_applications.c.created_at.desc()))).mappings().all()
    open_14b = (await session.execute(select(demands).where(demands.c.establishment_id == (actor.establishment_id or ""),
                                                            demands.c.kind == "DAMAGES_14B", demands.c.state == "OPEN"))).mappings().all()
    terms = _terms()
    return envelope({"applications": [_application(r) for r in rows], "open_14b_demands": [dict(d) for d in open_14b],
                     "assessment": await _assess(session, actor.establishment_id or ""),
                     "scheme": {k: terms[k] for k in ("scheme", "open_from", "open_until", "defaults_before", "rate_bands")}})


@router.get("/api/v1/office/compliance/vishwas-applications")
async def office_applications(actor: Actor = Depends(require_stakeholder("fo.apfc", "fo.da_compliance")), session: AsyncSession = Depends(db)) -> dict:
    office = await _office(session, actor)
    in_office = set((await session.execute(select(establishments.c.establishment_id).where(establishments.c.office_id == office))).scalars())
    rows = (await session.execute(select(vishwas_applications).order_by(vishwas_applications.c.created_at.desc()))).mappings().all()
    names = await _names(session)
    out = []
    for r in rows:
        if r["establishment_id"] in in_office:
            assessed = await _assess(session, r["establishment_id"], r["demand_ids"]) if r["state"] == "SUBMITTED" else []
            out.append({**_application(r), "legal_name": names.get(r["establishment_id"]), "assessment": assessed,
                        "proposed_revised_paise": sum(a["revised_paise"] or 0 for a in assessed) if assessed else r["revised_paise"]})
    return envelope(out)


class Decision(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5, max_length=500)


@router.post("/api/v1/office/compliance/vishwas-applications/{applicationId}/decisions")
async def decide(applicationId: str, body: Decision, actor: Actor = Depends(require_stakeholder("fo.apfc")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await _office(session, actor)
        a = (await session.execute(select(vishwas_applications).where(vishwas_applications.c.application_id == applicationId))).mappings().first()
        est_office = (await session.execute(select(establishments.c.office_id).where(
            establishments.c.establishment_id == (a["establishment_id"] if a else "")))).scalar_one_or_none()
        if not a or est_office != office:
            raise Problem(404, "/problems/not-found", "Application not found")
        if a["state"] != "SUBMITTED":
            raise Problem(409, "/problems/invalid-state", "Already decided", f"State: {a['state']}.")
        assessed = await _assess(session, a["establishment_id"], a["demand_ids"])
        revised = sum(x["revised_paise"] or 0 for x in assessed)
        if body.decision == "APPROVE" and (len(assessed) != len(a["demand_ids"]) or not all(x["eligible"] for x in assessed)):
            raise Problem(409, "/problems/not-eligible", "A demand is no longer eligible",
                          "; ".join(f"{x['demand_id']}: {' '.join(x['reasons'])}" for x in assessed if not x["eligible"]) or "A demand was settled meanwhile. Reject the application.")
        require_step_up(actor, "decide-vishwas", applicationId, None, revised if body.decision == "APPROVE" else a["damages_paise"])
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        if state == "APPROVED":
            still_open = (await session.execute(select(demands.c.demand_id).where(demands.c.demand_id.in_(a["demand_ids"]),
                                                                                  demands.c.state == "OPEN"))).scalars().all()
            if len(still_open) != len(a["demand_ids"]):
                raise Problem(409, "/problems/demand-settled", "A demand in the application was settled meanwhile", "Reject the application.")
            await add_event(session, producer=PRODUCER, event_type="DemandRaised.v1", aggregate_type="demand",
                            aggregate_id=applicationId, correlation_id=actor.correlation_id, payload={
                                "demand_id": f"DEM-{applicationId}", "establishment_id": a["establishment_id"], "demand_type": "DAMAGES_14B_VISHWAS",
                                "amount_paise": revised, "supersedes_demand_ids": a["demand_ids"],
                                "working": f"{_terms()['scheme']} {applicationId}: ₹{a['damages_paise'] // 100:,} damages recalculated — "
                                           + "; ".join(f"{x['demand_id']} {y['wage_month']}: ₹{y['arrears_paise'] // 100:,} x {y['rate_pct_per_month']:g}% "
                                                       f"x {y['months_of_default']:g} months" for x in assessed for y in x["defaults"]),
                                "rule_version": baseline()["rule_version"]})
        await session.execute(update(vishwas_applications).where(vishwas_applications.c.application_id == applicationId).values(
            state=state, revised_paise=revised if state == "APPROVED" else None, decided_by=actor.subject, decision_note=body.note))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"vishwas.{state.lower()}",
                    target_type="vishwas_application", target_id=applicationId, detail=body.note)
    return envelope(_application({**dict(a), "state": state, "revised_paise": revised if state == "APPROVED" else None, "decision_note": body.note}))
