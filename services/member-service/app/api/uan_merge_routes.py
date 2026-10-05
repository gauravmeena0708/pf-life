"""Office UAN merge routes (P2.19)."""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import employments, member_applications, members, uan_merges
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
MERGE_OFFICER = require_stakeholder("fo.ao", "fo.apfc")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class UanMergeInput(BaseModel):
    active_uan: str = Field(min_length=1, max_length=32)
    duplicate_uan: str = Field(min_length=1, max_length=32)
    note: str = Field(min_length=1, max_length=1000)


async def _notify(session: AsyncSession, subject: str, template: str, reference_id: str) -> None:
    await add_event(session, producer="member-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=reference_id, correlation_id=str(uuid4()), payload={
                        "recipient_subject": subject, "template": template, "reference_id": reference_id,
                        "params": {"reason": f"UAN merge processed (reference {reference_id})"}
                    })


@router.post("/api/v1/office/uan-merges", status_code=status.HTTP_201_CREATED)
async def create_uan_merge(body: UanMergeInput, actor: Actor = Depends(MERGE_OFFICER),
                           session: AsyncSession = Depends(db)) -> dict:
    if body.active_uan == body.duplicate_uan:
        raise Problem(422, "/problems/invalid-uan", "Active and duplicate UAN must differ")

    async with session.begin():
        active = (await session.execute(select(members).where(members.c.uan == body.active_uan))).mappings().first()
        if not active:
            raise Problem(422, "/problems/not-found", f"Active UAN {body.active_uan} not found")

        dup = (await session.execute(select(members).where(members.c.uan == body.duplicate_uan))).mappings().first()
        if not dup:
            raise Problem(422, "/problems/not-found", f"Duplicate UAN {body.duplicate_uan} not found")

        # Identity matching: name (case/space-insensitive), date_of_birth, gender, aadhaar_ref where both have one
        norm_active_name = " ".join(active["name"].strip().split()).casefold()
        norm_dup_name = " ".join(dup["name"].strip().split()).casefold()
        if norm_active_name != norm_dup_name:
            raise Problem(422, "/problems/identity-mismatch", "Name does not match between active and duplicate UAN")

        if active["date_of_birth"] != dup["date_of_birth"]:
            raise Problem(422, "/problems/identity-mismatch", "Date of birth does not match between active and duplicate UAN")

        if active["gender"] != dup["gender"]:
            raise Problem(422, "/problems/identity-mismatch", "Gender does not match between active and duplicate UAN")

        if active.get("aadhaar_ref") and dup.get("aadhaar_ref") and active["aadhaar_ref"] != dup["aadhaar_ref"]:
            raise Problem(422, "/problems/identity-mismatch", "Aadhaar reference does not match between active and duplicate UAN")

        # Conflict checks (409)
        if dup["account_state"] == "MERGED" or dup.get("merged_into"):
            raise Problem(409, "/problems/already-merged", f"Duplicate UAN {body.duplicate_uan} is already merged")

        if active["account_state"] == "MERGED":
            raise Problem(409, "/problems/already-merged", f"Active UAN {body.active_uan} is already merged")

        ongoing_claim = (await session.execute(
            select(member_applications).where(
                member_applications.c.uan == body.duplicate_uan,
                member_applications.c.terminal.is_(False)
            )
        )).first()
        if ongoing_claim:
            raise Problem(409, "/problems/claim-in-progress", f"Duplicate UAN {body.duplicate_uan} has an application in progress")

        dup_links = (await session.execute(
            select(employments.c.account_link_id).where(employments.c.member_id == dup["member_id"])
        )).scalars().all()

        now = datetime.now(UTC)
        merge_id = f"MERGE-{uuid4().hex[:12].upper()}"

        # Link duplicate's member IDs / employments to active member
        await session.execute(
            update(employments).where(employments.c.member_id == dup["member_id"]).values(member_id=active["member_id"])
        )

        # Mark duplicate MERGED
        await session.execute(
            update(members).where(members.c.uan == body.duplicate_uan).values(
                account_state="MERGED",
                merged_into=body.active_uan,
                merged_at=now,
                merged_by=actor.subject,
                account_state_updated_at=now
            )
        )

        # Record merge
        await session.execute(
            insert(uan_merges).values(
                merge_id=merge_id,
                active_uan=body.active_uan,
                duplicate_uan=body.duplicate_uan,
                account_link_ids=list(dup_links),
                note=body.note,
                merged_by=actor.subject,
                merged_at=now
            )
        )

        # Audit
        await audit(
            session,
            actor_subject=actor.subject,
            actor_stakeholder=actor.stakeholder,
            action="member.uan_merged",
            target_type="member",
            target_id=body.duplicate_uan,
            detail=f"Merged duplicate UAN {body.duplicate_uan} into active UAN {body.active_uan}. Note: {body.note}"
        )

        # Notify the member
        if active.get("subject"):
            await _notify(session, active["subject"], "OFFICE_NOTICE", merge_id)
        if dup.get("subject") and dup["subject"] != active.get("subject"):
            await _notify(session, dup["subject"], "OFFICE_NOTICE", merge_id)

        # Emit UanMerged.v1
        await add_event(
            session,
            producer="member-service",
            event_type="UanMerged.v1",
            aggregate_type="member",
            aggregate_id=body.active_uan,
            payload={
                "active_uan": body.active_uan,
                "duplicate_uan": body.duplicate_uan,
                "account_link_ids": list(dup_links),
                "merged_at": now.isoformat(),
            }
        )

    return envelope({
        "merge_id": merge_id,
        "active_uan": body.active_uan,
        "duplicate_uan": body.duplicate_uan,
        "account_link_ids": list(dup_links),
        "note": body.note,
        "merged_by": actor.subject,
        "merged_at": now.isoformat(),
    })


@router.get("/api/v1/office/uan-merges")
async def list_uan_merges(actor: Actor = Depends(MERGE_OFFICER), session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(uan_merges).order_by(uan_merges.c.merged_at.desc()))).mappings().all()
    return envelope([{
        "merge_id": r["merge_id"],
        "active_uan": r["active_uan"],
        "duplicate_uan": r["duplicate_uan"],
        "account_link_ids": r["account_link_ids"],
        "note": r["note"],
        "merged_by": r["merged_by"],
        "merged_at": r["merged_at"].isoformat() if hasattr(r["merged_at"], "isoformat") else str(r["merged_at"]),
    } for r in rows])
