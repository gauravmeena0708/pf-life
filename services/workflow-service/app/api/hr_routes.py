"""Phase 2, slice 8e: staff postings and the zonal fraud-risk committee's case list. Illustrative.

* HR (ho.hr, anywhere) or an office's administration (fo.admin, within its own office) posts an officer to an
  office with a role. The posting drives jurisdiction: this service's queues use it at once, and
  StaffPostingChanged.v1 updates the copy every other service keeps.
* The zone's fraud-risk committee sees the cases of its offices that point to a possible fraud: accounts frozen or
  under a freeze process, and claims that carry an advisory risk signal."""
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, posting
from app.infra.tables import cases, office_staff, offices
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
PRODUCER = "workflow-service"
OFFICE_ROLES = ("fo.", "zo.", "do.")


class PostingInput(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    stakeholder: str = Field(min_length=3, max_length=60)
    office_id: str = Field(min_length=3, max_length=40)
    reason: str = Field(min_length=10, max_length=1000)


@router.post("/api/v1/hrm/postings")
async def post_staff(body: PostingInput, actor: Actor = Depends(require_stakeholder("ho.hr", "fo.admin")),
                     session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        target = (await session.execute(select(office_staff).where(office_staff.c.username == body.username))).mappings().first()
        if not target:
            raise Problem(404, "/problems/not-found", "No officer with this user name is on the rolls")
        office = (await session.execute(select(offices).where(offices.c.office_id == body.office_id))).mappings().first()
        if not office and not body.office_id.startswith("ZO-"):
            raise Problem(422, "/problems/validation", "Unknown office")
        if not body.stakeholder.startswith(OFFICE_ROLES):
            raise Problem(422, "/problems/validation", "Only office roles are posted here")
        if actor.stakeholder == "fo.admin":                      # an office's administration posts within its own office
            mine = await posting(session, actor)
            if not mine or mine["office_id"] != body.office_id or target["office_id"] != body.office_id or not body.stakeholder.startswith("fo."):
                raise Problem(403, "/problems/outside-your-office", "Office administration posts staff within its own office only")
        if (target["stakeholder"], target["office_id"]) == (body.stakeholder, body.office_id):
            raise Problem(409, "/problems/unchanged", "The officer already holds this posting")
        require_step_up(actor, "post-staff", body.username)
        await session.execute(update(office_staff).where(office_staff.c.subject == target["subject"]).values(
            stakeholder=body.stakeholder, office_id=body.office_id))
        await session.execute(update(cases).where(cases.c.assignee_subject == target["subject"], cases.c.state != "CLOSED",
                                                  cases.c.office_id != body.office_id).values(assignee_subject=None))
        await add_event(session, producer=PRODUCER, event_type="StaffPostingChanged.v1", aggregate_type="staff_posting",
                        aggregate_id=target["subject"], correlation_id=actor.correlation_id, payload={
                            "subject": target["subject"], "username": body.username, "stakeholder": body.stakeholder,
                            "office_id": body.office_id, "previous_stakeholder": target["stakeholder"],
                            "previous_office_id": target["office_id"]})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="hrm.posting",
                    target_type="officer", target_id=body.username,
                    detail=f"{target['stakeholder']}@{target['office_id']} → {body.stakeholder}@{body.office_id}: {body.reason}")
    return envelope({"username": body.username, "stakeholder": body.stakeholder, "office_id": body.office_id,
                     "previous": {"stakeholder": target["stakeholder"], "office_id": target["office_id"]},
                     "note": "Work in progress assigned to the officer in another office was released to that office's queue."})


def _case(c: Any, names: dict[str, str]) -> dict[str, Any]:
    reason = ("Advisory risk signal on the claim" if c["advisory_signal_id"] else
              "Account frozen / freeze in progress" if c["process"] in ("member_freeze", "establishment_freeze") else "")
    return {"case_id": c["case_id"], "kind": c["kind"], "process": c["process"], "office_id": c["office_id"],
            "office": names.get(c["office_id"]), "subject_ref": c["subject_ref"], "claim_id": c["claim_id"], "state": c["state"],
            "advisory_signal_id": c["advisory_signal_id"], "why": reason,
            "opened_at": c["created_at"].isoformat() if c["created_at"] else None}


@router.get("/api/v1/zo/fraud-risk/cases")
async def fraud_risk_cases(actor: Actor = Depends(require_stakeholder("zo.fraud_committee")), session: AsyncSession = Depends(db)) -> dict:
    mine = await posting(session, actor)
    if not mine:
        raise Problem(403, "/problems/no-posting", "You are not posted to a zone")
    zone_offices = {o["office_id"]: o["name"] for o in (await session.execute(select(offices).where(
        offices.c.zone_id == mine["office_id"]))).mappings().all()}
    rows = (await session.execute(select(cases).where(cases.c.office_id.in_(list(zone_offices) or ["-"]), or_(
        cases.c.advisory_signal_id.is_not(None), cases.c.process.in_(("member_freeze", "establishment_freeze"))))
        .order_by(cases.c.created_at.desc()).limit(200))).mappings().all()
    return envelope({"zone_id": mine["office_id"], "cases": [_case(r, zone_offices) for r in rows],
                     "note": "Illustrative selection: claims with an advisory risk signal and account freezes in the zone's offices."})
