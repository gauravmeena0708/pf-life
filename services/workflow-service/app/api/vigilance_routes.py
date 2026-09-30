"""Phase 2, slice 10a: vigilance cases. Illustrative, after the CVC's pattern for complaints and preliminary inquiries.

* The CAIU (ho.caiu) refers a risk signal it has reviewed as confirmed, a member's security report, or a complaint.
  The case gets a Vigilance Complaint Number (VCN).
* The CVO (ho.cvo) assigns a preliminary inquiry (PI) to the zone of the office where the matter arose, due in the
  rule set's `vigilance.pi_days`; or closes a referral with no substance.
* Zonal vigilance (zo.vigilance) sees only the cases assigned to its zone and reports the findings; a report after the
  due date is marked late. The CVO then decides (an outcome from the rule set) or returns the case for more inquiry.
* Restricted: only the CVO and the assigned zone read a case; every read is written to the audit log; the complainant
  is masked for everyone but the CVO; events carry identifiers only, so nothing reaches reporting or the assistant."""
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, posting
from app.infra.tables import offices, vigilance_actions, vigilance_cases, vigilance_signals
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
PRODUCER = "workflow-service"
READERS = require_stakeholder("ho.cvo", "zo.vigilance")
ASSIGNABLE, FINAL = ("PI_ASSIGNED", "PI_REPORTED", "CLOSED", "ACTION_ORDERED"), ("CLOSED", "ACTION_ORDERED")


class Evidence(BaseModel):
    kind: Literal["RISK_SIGNAL", "CLAIM", "AUDIT_EVENT", "OFFICE_CASE", "DOCUMENT"]
    ref: str = Field(min_length=3, max_length=80)


class Complainant(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact: str | None = Field(default=None, max_length=120)


class ReferralInput(BaseModel):
    source: str = Field(max_length=30)
    source_ref: str | None = Field(default=None, max_length=80)
    subject_type: Literal["MEMBER", "ESTABLISHMENT", "OFFICIAL"]
    subject_ref: str = Field(min_length=3, max_length=80)
    office_id: str = Field(min_length=3, max_length=40)
    allegation: str = Field(min_length=20, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    complainant: Complainant | None = None


class DecisionInput(BaseModel):
    decision: str = Field(max_length=40)
    note: str = Field(min_length=10, max_length=2000)


class FindingsInput(BaseModel):
    finding: Literal["SUBSTANTIATED", "PARTLY_SUBSTANTIATED", "NOT_SUBSTANTIATED"]
    report: str = Field(min_length=50, max_length=8000)
    recommendation: str = Field(min_length=10, max_length=2000)
    evidence_examined: list[str] = Field(default_factory=list, max_length=50)


def _view(c: dict[str, Any], actor: Actor, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    out = {k: c[k] for k in ("case_id", "vcn", "source", "source_ref", "subject_type", "subject_ref", "office_id", "zone_id",
                             "allegation", "evidence", "state", "findings", "outcome")}
    out["pi_due"] = c["pi_due"].isoformat() if c["pi_due"] else None
    out["opened_at"] = c["created_at"].isoformat() if c["created_at"] else None
    # The complainant's identity is for the CVO alone (CVC practice: protect the complainant).
    out["complainant"] = c["complainant"] if actor.stakeholder == "ho.cvo" else ({"masked": True} if c["complainant"] else None)
    out["overdue"] = bool(c["pi_due"] and c["state"] == "PI_ASSIGNED" and date.today() > c["pi_due"])
    if history is not None:
        out["history"] = [{"actor": h["actor_stakeholder"], "action": h["action"], "note": h["note"],
                           "at": h["at"].isoformat() if h["at"] else None} for h in history]
    return out


async def _zone(session: AsyncSession, actor: Actor) -> str | None:
    return None if actor.stakeholder == "ho.cvo" else (await posting(session, actor))["office_id"]


async def _case(session: AsyncSession, case_id: str, actor: Actor, lock: bool = False) -> dict[str, Any]:
    q = select(vigilance_cases).where(vigilance_cases.c.case_id == case_id)
    if lock and session.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    c = (await session.execute(q)).mappings().first()
    zone = await _zone(session, actor)
    if not c or (zone is not None and (c["zone_id"] != zone or c["state"] not in ASSIGNABLE)):
        raise Problem(404, "/problems/not-found", "No such vigilance case")      # never reveal another zone's case
    return dict(c)


async def _act(session: AsyncSession, case_id: str, actor: Actor, action: str, note: str | None) -> None:
    await session.execute(insert(vigilance_actions).values(case_id=case_id, actor_stakeholder=actor.stakeholder, action=action, note=note))


@router.post("/api/v1/vigilance/referrals", status_code=201)
async def refer(body: ReferralInput, actor: Actor = Depends(require_stakeholder("ho.caiu")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        rules = section(await rules_on(session, date.today()), "vigilance")
        if body.source not in rules["sources"]:
            raise Problem(422, "/problems/validation", "Unknown referral source", f"One of: {', '.join(rules['sources'])}.")
        if body.source in ("CAIU_SIGNAL", "MEMBER_REPORT") and not body.source_ref:
            raise Problem(422, "/problems/validation", "Give the signal or report this referral comes from")
        evidence = [e.model_dump() for e in body.evidence]
        if body.source == "CAIU_SIGNAL":
            signal = (await session.execute(select(vigilance_signals).where(vigilance_signals.c.signal_id == body.source_ref))).mappings().first()
            if not signal or signal["outcome"] != "CONFIRMED":
                raise Problem(409, "/problems/signal-not-confirmed", "Only a risk signal the CAIU has reviewed as confirmed can be referred",
                              "Review the signal first; a benign signal or one needing more evidence stays with the CAIU.")
            if not any(e["kind"] == "RISK_SIGNAL" and e["ref"] == body.source_ref for e in evidence):
                evidence.insert(0, {"kind": "RISK_SIGNAL", "ref": body.source_ref})
        if body.source_ref and (await session.execute(select(vigilance_cases.c.vcn).where(
                vigilance_cases.c.source == body.source, vigilance_cases.c.source_ref == body.source_ref))).first():
            raise Problem(409, "/problems/already-referred", "This has already been referred to vigilance")
        office = (await session.execute(select(offices).where(offices.c.office_id == body.office_id))).mappings().first()
        if not office:
            raise Problem(422, "/problems/validation", "Unknown office")
        count = (await session.execute(select(func.count()).select_from(vigilance_cases))).scalar_one()
        case_id, vcn = f"VC-{secrets.token_hex(4).upper()}", f"VIG/{date.today().year}/{count + 1:04d}"
        await session.execute(insert(vigilance_cases).values(
            case_id=case_id, vcn=vcn, source=body.source, source_ref=body.source_ref, subject_type=body.subject_type,
            subject_ref=body.subject_ref, office_id=body.office_id, allegation=body.allegation, evidence=evidence,
            complainant=body.complainant.model_dump() if body.complainant else None, state="REFERRED", referred_by=actor.subject))
        await _act(session, case_id, actor, "REFERRED", None)
        await add_event(session, producer=PRODUCER, event_type="VigilanceCaseOpened.v1", aggregate_type="vigilance_case",
                        aggregate_id=case_id, correlation_id=actor.correlation_id, payload={
                            "case_id": case_id, "vcn": vcn, "source": body.source, "subject_type": body.subject_type,
                            "office_id": body.office_id})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vigilance.referral",
                    target_type="vigilance_case", target_id=case_id, detail=vcn)
    return envelope({"case_id": case_id, "vcn": vcn, "state": "REFERRED",
                     "next_step": "The Chief Vigilance Officer decides whether a preliminary inquiry is needed."})


@router.get("/api/v1/vigilance/cases")
async def list_cases(actor: Actor = Depends(READERS), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        zone = await _zone(session, actor)
        q = select(vigilance_cases).order_by(vigilance_cases.c.created_at.desc()).limit(200)
        if zone is not None:
            q = q.where(vigilance_cases.c.zone_id == zone, vigilance_cases.c.state.in_(ASSIGNABLE))
        rows = (await session.execute(q)).mappings().all()
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vigilance.cases.list",
                    target_type="vigilance_case", target_id=zone or "ALL", detail=f"{len(rows)} cases")
    items = [{k: v for k, v in _view(dict(r), actor).items() if k not in ("allegation", "evidence", "findings")} for r in rows]
    return envelope({"zone_id": zone, "cases": items, "restricted": True,
                     "note": "Restricted: every read of a vigilance case is recorded in the audit log."})


@router.get("/api/v1/vigilance/cases/{case_id}")
async def get_case(case_id: str, actor: Actor = Depends(READERS), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _case(session, case_id, actor)
        history = (await session.execute(select(vigilance_actions).where(vigilance_actions.c.case_id == case_id)
                                         .order_by(vigilance_actions.c.id))).mappings().all()
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vigilance.case.read",
                    target_type="vigilance_case", target_id=case_id, detail=c["vcn"])
    return envelope(_view(c, actor, [dict(h) for h in history]))


@router.post("/api/v1/vigilance/cases/{case_id}/decisions")
async def decide(case_id: str, body: DecisionInput, actor: Actor = Depends(require_stakeholder("ho.cvo")),
                 session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        rules = section(await rules_on(session, date.today()), "vigilance")
        c = await _case(session, case_id, actor, lock=True)
        allowed = {"REFERRED": ("ASSIGN_INQUIRY", "CLOSED_NO_SUBSTANCE"),
                   "PI_REPORTED": ("RETURN_FOR_INQUIRY", *rules["outcomes"])}.get(c["state"], ())
        if body.decision not in allowed:
            raise Problem(409, "/problems/invalid-decision", "This decision is not open for the case now",
                          f"The case is {c['state']}; open decisions: {', '.join(allowed) or 'none — waiting for the inquiry report'}.")
        require_step_up(actor, "decide-vigilance-case", case_id)
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if body.decision in ("ASSIGN_INQUIRY", "RETURN_FOR_INQUIRY"):
            zone = c["zone_id"] or (await session.execute(select(offices.c.zone_id).where(offices.c.office_id == c["office_id"]))).scalar_one()
            if not zone:
                raise Problem(409, "/problems/no-zone", "The office has no zone to assign the inquiry to")
            values.update(state="PI_ASSIGNED", zone_id=zone, pi_due=date.today() + timedelta(days=int(rules["pi_days"])),
                          **({"findings": None} if body.decision == "RETURN_FOR_INQUIRY" else {}))
        else:
            values.update(state="CLOSED" if body.decision == "CLOSED_NO_SUBSTANCE" else "ACTION_ORDERED", outcome=body.decision)
        await session.execute(update(vigilance_cases).where(vigilance_cases.c.case_id == case_id).values(**values))
        await _act(session, case_id, actor, body.decision, body.note)
        state, zone = values["state"], values.get("zone_id", c["zone_id"])
        await add_event(session, producer=PRODUCER, event_type="VigilanceDecisionRecorded.v1", aggregate_type="vigilance_case",
                        aggregate_id=case_id, correlation_id=actor.correlation_id, payload={
                            "case_id": case_id, "vcn": c["vcn"], "decision": body.decision, "state": state, "zone_id": zone})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vigilance.decision",
                    target_type="vigilance_case", target_id=case_id, detail=f"{c['vcn']}: {body.decision}")
    return envelope({"case_id": case_id, "vcn": c["vcn"], "decision": body.decision, "state": state, "zone_id": zone,
                     "pi_due": values["pi_due"].isoformat() if values.get("pi_due") else (c["pi_due"].isoformat() if c["pi_due"] else None)})


@router.post("/api/v1/vigilance/cases/{case_id}/findings")
async def findings(case_id: str, body: FindingsInput, actor: Actor = Depends(require_stakeholder("zo.vigilance")),
                   session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        c = await _case(session, case_id, actor, lock=True)
        if c["state"] != "PI_ASSIGNED":
            raise Problem(409, "/problems/invalid-state", "Findings can be reported only while the inquiry is open",
                          f"The case is {c['state']}.")
        require_step_up(actor, "report-vigilance-findings", case_id)
        late = bool(c["pi_due"] and date.today() > c["pi_due"])
        report = {**body.model_dump(), "late": late, "reported_at": datetime.now(UTC).isoformat()}
        await session.execute(update(vigilance_cases).where(vigilance_cases.c.case_id == case_id).values(
            state="PI_REPORTED", findings=report, updated_at=datetime.now(UTC)))
        await _act(session, case_id, actor, "FINDINGS_REPORTED", f"{body.finding.replace('_', ' ').capitalize()}{' (late)' if late else ''}")
        await add_event(session, producer=PRODUCER, event_type="VigilanceFindingsRecorded.v1", aggregate_type="vigilance_case",
                        aggregate_id=case_id, correlation_id=actor.correlation_id, payload={
                            "case_id": case_id, "vcn": c["vcn"], "zone_id": c["zone_id"], "finding": body.finding, "late": late})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="vigilance.findings",
                    target_type="vigilance_case", target_id=case_id, detail=f"{c['vcn']}: {body.finding}")
    return envelope({"case_id": case_id, "vcn": c["vcn"], "state": "PI_REPORTED", "late": late,
                     "next_step": "The Chief Vigilance Officer decides on the findings."})
