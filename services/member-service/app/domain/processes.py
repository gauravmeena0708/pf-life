"""member-service owns the freeze and Joint Declaration contracts; the engine in workflow-service runs the
processes (ADR-0005). On each ProcessTransitioned.v1 this service does what the contract promises:

* member_freeze       records the account state and publishes AccountFrozen.v1 / AccountDefrozen.v1;
* joint_declaration   tells the member at each step, and on APPROVED applies the correction, keeps the history
                      and publishes MemberChangeApproved.v1 (so, for example, ECR name checks use the new name)."""
from datetime import date
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import member_changes, members
from epfo_persistence import add_event

CORE_FIELDS = {"NAME": "name", "DATE_OF_BIRTH": "date_of_birth", "GENDER": "gender"}
JD_NOTICES = {"EMPLOYER_ATTESTED": "JD_EMPLOYER_ATTESTED", "RETURNED_BY_EMPLOYER": "JD_RETURNED_BY_EMPLOYER",
              "REJECTED_BY_EMPLOYER": "JD_REJECTED_BY_EMPLOYER", "APPROVED": "JD_APPROVED", "REJECTED": "JD_REJECTED"}


async def on_process_transitioned(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["process"] == "member_freeze":
        await _freeze(session, event)
    elif p["process"] == "joint_declaration":
        await _joint_declaration(session, event)


async def _freeze(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["to_state"] not in ("FROZEN", "ACTIVE"):
        return
    uan, data = p["subject_ref"], p.get("data") or {}
    await session.execute(update(members).where(members.c.uan == uan).values(account_state=p["to_state"]))
    if p["to_state"] == "FROZEN":
        await add_event(session, producer="member-service", event_type="AccountFrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "category": data.get("category", ""),
                            "order_ref": data.get("order_ref", "")})
    else:
        await add_event(session, producer="member-service", event_type="AccountDefrozen.v1", aggregate_type="account",
                        aggregate_id=uan, correlation_id=event["correlation_id"], payload={
                            "target_type": "member", "target_id": uan, "order_ref": p["instance_id"]})


async def _joint_declaration(session: AsyncSession, event: dict[str, Any]) -> None:
    p, data = event["payload"], event["payload"].get("data") or {}
    member = (await session.execute(select(members).where(members.c.uan == p["subject_ref"]))).mappings().first()
    if not member:
        return
    template = JD_NOTICES.get(p["to_state"])
    if template:
        await add_event(session, producer="member-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=p["instance_id"], correlation_id=event["correlation_id"], payload={
                            "recipient_subject": member["subject"], "template": template, "reference_id": p["instance_id"],
                            "params": {"parameter": data.get("parameter", "").replace("_", " ").lower(), "reason": data.get("reason") or data.get("note")}})
    if p["to_state"] != "APPROVED":
        return
    if (await session.execute(select(member_changes.c.id).where(member_changes.c.request_id == p["instance_id"]))).first():
        return                                                          # already applied
    parameter, value = data["parameter"], data["corrected_value"].strip()
    column = CORE_FIELDS.get(parameter)
    if column == "date_of_birth":
        old, new = member["date_of_birth"].isoformat(), date.fromisoformat(value)
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(date_of_birth=new))
    elif column:
        old, new = member[column], value.upper()                     # names and gender are stored in capitals
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values({column: new}))
    else:
        extra = dict(member["profile_extra"] or {})
        old, new = extra.get(parameter.lower()), value
        extra[parameter.lower()] = value
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(profile_extra=extra))
    await session.execute(insert(member_changes).values(request_id=p["instance_id"], member_id=member["member_id"],
                                                        parameter=parameter, old_value=str(old) if old is not None else None,
                                                        new_value=str(new), approved_by=p.get("actor_subject", "")))
    await add_event(session, producer="member-service", event_type="MemberChangeApproved.v1", aggregate_type="member_change_request",
                    aggregate_id=p["instance_id"], correlation_id=event["correlation_id"], payload={
                        "request_id": p["instance_id"], "uan": p["subject_ref"],
                        "parameters": [{"parameter": parameter, "value": str(new)}], "approver_subject": p.get("actor_subject", "")})
