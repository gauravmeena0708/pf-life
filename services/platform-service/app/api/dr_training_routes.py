"""Illustrative ADC replication, failover drills and synthetic training login records (P2.12f)."""
import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db
from app.infra.tables import failover_drills, training_sandboxes
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
PRODUCER = "platform-service"
DATABASES = ("employer", "member", "contribution", "claim", "workflow", "grievance", "audit",
             "reporting", "intelligence", "pension", "platform", "compliance", "international", "payment")
SCENARIOS = {
    "FULL_SITE": (12, 28, 6, 18),
    "DATABASE": (4, 9, 2, 6),
    "APPLICATION_TIER": (3, 5, 4, 4),
}
STEP_NAMES = ("freeze writes", "promote replica", "switch DNS", "smoke test")
PERSONAS = frozenset(("member-a", "member-b", "emp-owner", "emp-preparer", "emp-signatory",
                      "do-caseworker", "ro-ss", "ro-ao", "ro-apfc", "ro-cashier"))
SIMULATION_NOTE = "Illustrative simulation only; no live replication or failover is performed."
SANDBOX_NOTE = "Synthetic data only; training logins are records, not real accounts."


@router.get("/api/v1/ndc/dr/replication-status")
async def replication_status(actor: Actor = Depends(require_stakeholder("tech.adc")),
                             session: AsyncSession = Depends(db)) -> dict:
    minute = datetime.now(UTC).replace(second=0, microsecond=0)
    rules = section(await rules_on(session, minute.date()), "dr_and_training")
    rpo = int(rules["rpo_minutes"])
    rows = []
    for name in DATABASES:
        lag = int.from_bytes(hashlib.sha256(f"{name}:{minute.isoformat()}".encode()).digest()[:8], "big") % 1201
        rows.append({"database": name, "lag_seconds": lag,
                     "status": "LAGGING" if lag > rpo * 60 else "IN_SYNC",
                     "last_applied_at": (minute - timedelta(seconds=lag)).isoformat()})
    return envelope({"databases": rows, "overall_status": "LAGGING" if any(r["status"] == "LAGGING" for r in rows) else "IN_SYNC",
                     "rpo_minutes": rpo, "simulated": True, "note": SIMULATION_NOTE})


class DrillInput(BaseModel):
    scenario: str
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/api/v1/ndc/dr/failover-drills", status_code=201)
async def record_drill(body: DrillInput, actor: Actor = Depends(require_stakeholder("tech.adc")),
                       session: AsyncSession = Depends(db)) -> dict:
    if body.scenario not in SCENARIOS:
        raise Problem(422, "/problems/validation", "Unknown failover scenario", ", ".join(SCENARIOS))
    require_step_up(actor, "run-failover-drill", body.scenario)
    steps = [{"step": name, "duration_minutes": duration}
             for name, duration in zip(STEP_NAMES, SCENARIOS[body.scenario])]
    rto = sum(step["duration_minutes"] for step in steps)
    drill_id = f"FDR-{secrets.token_hex(4).upper()}"
    async with session.begin():
        rules = section(await rules_on(session, datetime.now(UTC).date()), "dr_and_training")
        target = int(rules["rto_minutes"])
        within_target = rto <= target
        await session.execute(insert(failover_drills).values(
            drill_id=drill_id, scenario=body.scenario, notes=body.notes, steps=steps,
            rto_minutes=rto, target_minutes=target, within_target=within_target, recorded_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="FailoverDrillRecorded.v1", aggregate_type="failover_drill",
                        aggregate_id=drill_id, correlation_id=actor.correlation_id,
                        payload={"drill_id": drill_id, "scenario": body.scenario, "rto_minutes": rto,
                                 "within_target": within_target})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="dr.failover_drill", target_type="failover_drill", target_id=drill_id, detail=body.scenario)
    return envelope({"drill_id": drill_id, "scenario": body.scenario, "notes": body.notes, "steps": steps,
                     "rto_minutes": rto, "target_minutes": target, "within_target": within_target,
                     "simulated": True, "note": SIMULATION_NOTE})


class SandboxInput(BaseModel):
    course: str = Field(min_length=5, max_length=200)
    trainees: int
    personas: list[str]
    starts_on: date


@router.post("/api/v1/training/sandboxes", status_code=201)
async def create_sandbox(body: SandboxInput,
                         actor: Actor = Depends(require_stakeholder("train.pdnasa", "train.zti", "zo.zti")),
                         session: AsyncSession = Depends(db)) -> dict:
    if not 1 <= body.trainees <= 60:
        raise Problem(422, "/problems/validation", "Trainees must be between 1 and 60")
    if not body.personas or any(persona not in PERSONAS for persona in body.personas):
        raise Problem(422, "/problems/validation", "Unknown or missing training persona",
                      "Choose one or more of: " + ", ".join(sorted(PERSONAS)))
    sandbox_id = f"SBX-{secrets.token_hex(4).upper()}"
    logins = [{"username": f"trainee-{sandbox_id[4:].lower()}-{n}",
               "persona": body.personas[(n - 1) % len(body.personas)]} for n in range(1, body.trainees + 1)]
    async with session.begin():
        rules = section(await rules_on(session, body.starts_on), "dr_and_training")
        expires_on = body.starts_on + timedelta(days=int(rules["sandbox_days"]))
        await session.execute(insert(training_sandboxes).values(
            sandbox_id=sandbox_id, course=body.course, trainees=body.trainees, personas=body.personas,
            training_logins=logins, starts_on=body.starts_on, expires_on=expires_on, created_by=actor.subject))
        await add_event(session, producer=PRODUCER, event_type="TrainingSandboxCreated.v1", aggregate_type="training_sandbox",
                        aggregate_id=sandbox_id, correlation_id=actor.correlation_id,
                        payload={"sandbox_id": sandbox_id, "course": body.course, "trainees": body.trainees,
                                 "expires_on": expires_on.isoformat()})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="training.sandbox_create", target_type="training_sandbox", target_id=sandbox_id,
                    detail=body.course)
    return envelope({"sandbox_id": sandbox_id, "course": body.course, "trainees": body.trainees,
                     "personas": body.personas, "training_logins": logins, "starts_on": body.starts_on.isoformat(),
                     "expires_on": expires_on.isoformat(), "simulated": True, "note": SANDBOX_NOTE})
