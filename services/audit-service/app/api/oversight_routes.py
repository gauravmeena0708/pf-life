"""Phase 2, slice 8e: oversight on the audit log. Illustrative.

* Security incidents: the security analyst records one; high or critical ones, and some categories whatever their
  severity, are reportable to CERT-In within 6 hours of detection (after CERT-In's directions of 2022, simplified);
  the report is a mock with an acknowledgement number.
* Concurrent audit: the zone's Concurrent Audit Cell downloads a day's functionality extract — the day's decisions
  and ledger movements from the audit log, each with red flags — raises alerts to an office, and the office's OIC
  replies within 3 days. P2.21b: claims settled automatically, with no officer in the loop, are checked after the event:
  a fixed share of them (one in AUTO_SAMPLE_ONE_IN, chosen from the claim number, so the sample cannot be steered
  and is the same on every download) is flagged AUTO_SETTLEMENT_SAMPLE for the auditor to look at."""
import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.infra.oversight_tables import concurrent_alerts, office_staff, security_incidents
from app.infra.tables import audit_log
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event

router = APIRouter()
PRODUCER = "audit-service"
SECURITY = require_stakeholder("ho.security")
AUDIT_CELL = require_stakeholder("zo.rpfc1_audit")
CATEGORIES = ("UNAUTHORISED_ACCESS", "DATA_BREACH", "MALWARE", "DENIAL_OF_SERVICE", "PHISHING", "IDENTITY_THEFT", "OTHER")
ALWAYS_REPORTABLE = {"DATA_BREACH", "UNAUTHORISED_ACCESS", "IDENTITY_THEFT"}          # illustrative
HIGH_VALUE_PAISE = 50_000_00                                                           # ₹5,00,000 (illustrative)
AUTO_SAMPLE_ONE_IN = 5                                                                 # illustrative
ZONE_OF = {"RO-DEMO-01": "ZO-DEMO-01", "RO-DEMO-02": "ZO-DEMO-01"}


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _posting(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(office_staff).where(office_staff.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(403, "/problems/no-posting", "You are not posted to an office")
    return dict(row)


# ── security incidents ──────────────────────────────────────────────────────────────────────────

class IncidentInput(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    category: str
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    detected_at: datetime
    description: str = Field(min_length=20, max_length=4000)
    affected_systems: list[str] = Field(default_factory=list, max_length=20)
    related_event_ids: list[str] = Field(default_factory=list, max_length=50)


def _incident(r: Any) -> dict[str, Any]:
    return {k: _iso(r[k]) for k in ("incident_id", "title", "category", "severity", "detected_at", "description",
                                    "affected_systems", "related_event_ids", "cert_in", "recorded_at")}


@router.post("/api/v1/security/incidents", status_code=201)
async def record_incident(body: IncidentInput, actor: Actor = Depends(SECURITY), session: AsyncSession = Depends(db)) -> dict:
    if body.category not in CATEGORIES:
        raise Problem(422, "/problems/validation", "Unknown category", "Choose one of: " + ", ".join(CATEGORIES))
    detected = body.detected_at if body.detected_at.tzinfo else body.detected_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if detected > now:
        raise Problem(422, "/problems/validation", "The detection time cannot be in the future")
    require_step_up(actor, "record-security-incident", f"{body.category}:{body.severity}")
    reportable = body.severity in ("HIGH", "CRITICAL") or body.category in ALWAYS_REPORTABLE
    due = detected + timedelta(hours=6)
    cert_in = {"required": reportable, "due_by": due.isoformat(),
               "reported_at": now.isoformat() if reportable else None, "late": reportable and now > due,
               "acknowledgement": f"CERTIN-MOCK-{secrets.token_hex(4).upper()}" if reportable else None}
    incident_id = f"INC-{secrets.token_hex(4).upper()}"
    async with session.begin():
        await session.execute(insert(security_incidents).values(
            incident_id=incident_id, title=body.title, category=body.category, severity=body.severity, detected_at=detected,
            description=body.description, affected_systems=body.affected_systems, related_event_ids=body.related_event_ids,
            cert_in=cert_in, recorded_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="SecurityIncidentRecorded.v1", aggregate_type="security_incident",
                        aggregate_id=incident_id, correlation_id=actor.correlation_id, payload={
                            "incident_id": incident_id, "category": body.category, "severity": body.severity,
                            "cert_in_reportable": reportable, "cert_in_late": bool(cert_in["late"])})
        row = (await session.execute(select(security_incidents).where(security_incidents.c.incident_id == incident_id))).mappings().one()
    return envelope({**_incident(row), "note": ("Reported to CERT-In (mock) within the 6-hour window." if reportable and not cert_in["late"]
                                                else "Reported to CERT-In (mock) after the 6-hour window: record the reason." if reportable
                                                else "Not reportable to CERT-In under the illustrative rules; kept on record.")})


@router.get("/api/v1/security/incidents")
async def list_incidents(actor: Actor = Depends(require_stakeholder("ho.security", "ho.audit")), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(security_incidents).order_by(security_incidents.c.recorded_at.desc()).limit(200))).mappings().all()
    return envelope([_incident(r) for r in rows])


# ── concurrent audit ────────────────────────────────────────────────────────────────────────────

def sampled(claim_id: str) -> bool:
    """Whether an automatically settled claim is in the post-audit sample: decided by the claim number alone."""
    return int(hashlib.sha256(claim_id.encode()).hexdigest()[:8], 16) % AUTO_SAMPLE_ONE_IN == 0


def flags_for(event_type: str, p: dict[str, Any]) -> tuple[list[str], str | None, int | None]:
    """Red flags a concurrent auditor looks at (illustrative), the reference and the amount."""
    flags: list[str] = []
    amount = p.get("amount_paise")
    if event_type == "ClaimDecisionRecorded.v1":
        ref = p.get("claim_id")
        if p.get("decision") in ("APPROVED", "AUTO_APPROVED") and (amount or 0) >= HIGH_VALUE_PAISE:
            flags.append("HIGH_VALUE_SETTLEMENT")
        if p.get("fund") == "EDLI":
            flags.append("EDLI_SANCTION")
        if p.get("decision") == "AUTO_APPROVED" and ref and sampled(ref):
            flags.append("AUTO_SETTLEMENT_SAMPLE")
        return flags, ref, amount
    if event_type == "ClaimStateChanged.v1":
        if p.get("to_state") in ("CORRECTION_PENDING", "REISSUE_APPROVED"):
            return ["BANK_ACCOUNT_CHANGED_AFTER_RETURN"], p.get("claim_id"), amount
        return [], None, None
    if event_type == "LedgerAdjusted.v1":
        kind = p.get("appendix_type")
        return (["PAST_ACCUMULATION_CREDIT"] if kind == "PAST_ACCUMULATION" else ["APPENDIX_E_ADJUSTMENT"]), p.get("adjustment_id"), \
            sum(int(x.get("amount_paise", 0)) for x in p.get("postings", []) if x.get("side") == "credit" and x.get("account_link_id"))
    if event_type == "LedgerReversed.v1":
        return ["JOURNAL_REVERSED"], p.get("reversal_journal_id") or p.get("journal_id"), None
    if event_type == "TransferPosted.v1":
        total = int(p.get("employee_paise", 0)) + int(p.get("employer_paise", 0))
        return (["AUTO_TRANSFER"] if str(p.get("transfer_id", "")).startswith("AUTO-") else []) + \
            (["HIGH_VALUE_TRANSFER"] if total >= HIGH_VALUE_PAISE else []), p.get("transfer_id"), total
    if event_type == "AccountDefrozen.v1":
        return ["ACCOUNT_DEFROZEN"], p.get("target_id"), None
    if event_type == "MemberChangeApproved.v1":
        changed = {x.get("parameter") for x in p.get("parameters", [])}
        return (["IDENTITY_CHANGED"] if changed & {"NAME", "DATE_OF_BIRTH"} else ["PROFILE_CHANGED"]), p.get("request_id"), None
    if event_type == "DemandStateChanged.v1" and p.get("state") in ("WAIVED", "KNOCKED_OFF"):
        return [f"DEMAND_{p['state']}"], p.get("demand_id"), amount
    return [], None, None


@router.get("/api/v1/audit/concurrent/extracts")
async def extract(day: date | None = Query(default=None), actor: Actor = Depends(require_stakeholder("zo.rpfc1_audit", "ho.audit")),
                  session: AsyncSession = Depends(db)) -> dict:
    day = day or datetime.now(UTC).date()
    start, end = day.isoformat(), (day + timedelta(days=1)).isoformat()
    rows = (await session.execute(select(audit_log).where(audit_log.c.occurred_at >= start, audit_log.c.occurred_at < end)
                                  .order_by(audit_log.c.seq))).mappings().all()
    items = []
    for r in rows:
        flags, ref, amount = flags_for(r["event_type"], r["payload"] or {})
        if flags:
            items.append({"event_id": r["event_id"], "occurred_at": r["occurred_at"], "event_type": r["event_type"],
                          "reference": ref, "amount_paise": amount, "office_id": (r["payload"] or {}).get("office_id"),
                          "flags": flags, "correlation_id": r["correlation_id"], "hash": r["hash"]})
    auto = [r for r in rows if r["event_type"] == "ClaimDecisionRecorded.v1" and (r["payload"] or {}).get("decision") == "AUTO_APPROVED"]
    counts: dict[str, int] = {}
    for i in items:
        for f in i["flags"]:
            counts[f] = counts.get(f, 0) + 1
    return envelope({"day": day.isoformat(), "items": items, "flag_counts": counts, "events_scanned": len(rows),
                     "auto_settlements": {"settled": len(auto), "sampled": counts.get("AUTO_SETTLEMENT_SAMPLE", 0),
                                          "one_in": AUTO_SAMPLE_ONE_IN},
                     "note": "Illustrative red flags drawn from the hash-chained audit log; the auditor decides what to raise."})


class AlertInput(BaseModel):
    office_id: str = Field(min_length=3, max_length=40)
    reference: str = Field(min_length=3, max_length=80)
    event_id: str | None = Field(default=None, max_length=36)
    flags: list[str] = Field(default_factory=list, max_length=10)
    finding: str = Field(min_length=10, max_length=4000)


def _alert(r: Any) -> dict[str, Any]:
    return {k: _iso(r[k]) for k in ("alert_id", "office_id", "zone_id", "reference", "event_id", "flags", "finding", "state",
                                    "due_by", "raised_at", "reply")}


@router.post("/api/v1/audit/concurrent/alerts", status_code=201)
async def raise_alert(body: AlertInput, actor: Actor = Depends(AUDIT_CELL), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        me = await _posting(session, actor)
        zone = ZONE_OF.get(body.office_id)
        if zone is None or zone != me["office_id"]:
            raise Problem(404, "/problems/not-found", "No such office in your zone")
        if body.event_id and not (await session.execute(select(audit_log.c.seq).where(audit_log.c.event_id == body.event_id))).first():
            raise Problem(422, "/problems/validation", "The audit event was not found")
        alert_id = f"CAA-{secrets.token_hex(4).upper()}"
        await session.execute(insert(concurrent_alerts).values(
            alert_id=alert_id, office_id=body.office_id, zone_id=zone, reference=body.reference, event_id=body.event_id,
            flags=body.flags, finding=body.finding, state="OPEN", due_by=datetime.now(UTC) + timedelta(days=3), raised_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="ConcurrentAuditAlertRaised.v1", aggregate_type="concurrent_alert",
                        aggregate_id=alert_id, correlation_id=actor.correlation_id, payload={
                            "alert_id": alert_id, "office_id": body.office_id, "reference": body.reference, "flags": body.flags})
        row = (await session.execute(select(concurrent_alerts).where(concurrent_alerts.c.alert_id == alert_id))).mappings().one()
    return envelope(_alert(row))


@router.get("/api/v1/audit/concurrent/alerts")
async def list_alerts(actor: Actor = Depends(require_stakeholder("zo.rpfc1_audit", "fo.oic")), session: AsyncSession = Depends(db)) -> dict:
    me = await _posting(session, actor)
    column = concurrent_alerts.c.zone_id if actor.stakeholder == "zo.rpfc1_audit" else concurrent_alerts.c.office_id
    rows = (await session.execute(select(concurrent_alerts).where(column == me["office_id"])
                                  .order_by(concurrent_alerts.c.raised_at.desc()))).mappings().all()
    now = datetime.now(UTC)
    return envelope([{**_alert(r), "overdue": r["state"] == "OPEN" and (r["due_by"] if r["due_by"].tzinfo else r["due_by"].replace(tzinfo=UTC)) < now}
                     for r in rows])


class ReplyInput(BaseModel):
    reply: str = Field(min_length=10, max_length=4000)
    action_taken: str = Field(min_length=5, max_length=1000)


@router.post("/api/v1/audit/concurrent/alerts/{alertId}/replies")
async def reply(alertId: str, body: ReplyInput, actor: Actor = Depends(require_stakeholder("fo.oic")), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        me = await _posting(session, actor)
        row = (await session.execute(select(concurrent_alerts).where(concurrent_alerts.c.alert_id == alertId,
                                                                     concurrent_alerts.c.office_id == me["office_id"]))).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Alert not found")
        if row["state"] != "OPEN":
            raise Problem(409, "/problems/invalid-state", "This alert has already been answered")
        now = datetime.now(UTC)
        due = row["due_by"] if row["due_by"].tzinfo else row["due_by"].replace(tzinfo=UTC)
        record = {"reply": body.reply, "action_taken": body.action_taken, "by": actor.subject, "at": now.isoformat(), "late": now > due}
        await session.execute(update(concurrent_alerts).where(concurrent_alerts.c.alert_id == alertId).values(state="REPLIED", reply=record))
        row = (await session.execute(select(concurrent_alerts).where(concurrent_alerts.c.alert_id == alertId))).mappings().one()
    return envelope(_alert(row))
