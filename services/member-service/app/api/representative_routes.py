"""P2.24: Authorised representatives API routes."""
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.representatives import RELATIONS, SCOPES, resolve_representative_subject
from app.infra.db import sessions
from app.infra.tables import members, representatives
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
MEMBER = require_stakeholder("member")
REPRESENTATIVE = require_stakeholder("member.representative")
GATEWAY = require_stakeholder("system.gateway")
PRODUCER = "member-service"


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


async def _member(session: AsyncSession, subject: str) -> dict[str, Any]:
    row = (await session.execute(select(members).where(members.c.subject == subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Member not found")
    return dict(row)


async def _notify(session: AsyncSession, subject: str, template: str, reference_id: str, correlation_id: str) -> None:
    await add_event(
        session,
        producer=PRODUCER,
        event_type="NotificationRequested.v1",
        aggregate_type="notification",
        aggregate_id=reference_id,
        correlation_id=correlation_id,
        payload={"recipient_subject": subject, "template": template, "reference_id": reference_id, "params": {}},
    )


class GrantRepresentativeInput(BaseModel):
    representative_subject: str | None = None
    representative_username: str | None = None
    relation: str
    scopes: list[str] = Field(min_length=1)
    valid_until: date


@router.get("/api/v1/members/me/representatives")
async def list_my_representatives(
    actor: Actor = Depends(MEMBER),
    session: AsyncSession = Depends(db),
) -> dict:
    rows = (
        await session.execute(
            select(representatives)
            .where(representatives.c.member_subject == actor.subject)
            .order_by(representatives.c.created_at.desc())
        )
    ).mappings().all()
    return envelope([
        {
            "grant_id": r["grant_id"],
            "representative_subject": r["representative_subject"],
            "relation": r["relation"],
            "scopes": r["scopes"],
            "valid_until": r["valid_until"].isoformat(),
            "state": r["state"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
        }
        for r in rows
    ])


@router.post("/api/v1/members/me/representatives", status_code=status.HTTP_201_CREATED)
async def grant_representative(
    body: GrantRepresentativeInput,
    actor: Actor = Depends(MEMBER),
    session: AsyncSession = Depends(db),
) -> dict:
    async with session.begin():
        member = await _member(session, actor.subject)
        relation = body.relation.strip().upper()
        if relation not in RELATIONS:
            raise Problem(400, "/problems/invalid-representative", "Invalid relation", f"Invalid relation: {body.relation}. Must be one of {', '.join(RELATIONS)}.")

        rep_subject = resolve_representative_subject(body.representative_subject, body.representative_username)
        if not rep_subject:
            raise Problem(400, "/problems/invalid-representative", "Missing representative", "Representative subject or valid username is required.")

        if rep_subject == actor.subject:
            raise Problem(400, "/problems/invalid-representative", "Self-representation not allowed", "A member cannot appoint themselves as their own representative.")

        invalid_scopes = [s for s in body.scopes if s not in SCOPES]
        if invalid_scopes:
            raise Problem(400, "/problems/invalid-representative", "Invalid scope", f"Invalid scope(s): {', '.join(invalid_scopes)}. Allowed scopes: {', '.join(SCOPES)}.")

        today = datetime.now(UTC).date()
        if body.valid_until <= today:
            raise Problem(400, "/problems/invalid-representative", "Invalid valid_until date", "valid_until must be in the future.")
        try:
            anniversary = today.replace(year=today.year + 1)
        except ValueError:
            anniversary = today.replace(year=today.year + 1, day=28)
        if body.valid_until > anniversary:
            raise Problem(400, "/problems/invalid-representative", "Invalid valid_until date", "valid_until cannot exceed 1 year.")

        grant_id = f"REP-{secrets.token_hex(6).upper()}"
        await session.execute(
            insert(representatives).values(
                grant_id=grant_id,
                member_subject=actor.subject,
                uan=member["uan"],
                representative_subject=rep_subject,
                relation=relation,
                scopes=body.scopes,
                valid_until=body.valid_until,
                state="ACTIVE",
            )
        )
        await audit(
            session,
            actor_subject=actor.subject,
            actor_stakeholder=actor.stakeholder,
            action="representative.granted",
            target_type="representative_grant",
            target_id=grant_id,
            detail=f"Representative {rep_subject} granted {relation} with scopes {','.join(body.scopes)}",
        )
        await _notify(session, actor.subject, "REPRESENTATIVE_GRANTED", grant_id, actor.correlation_id)
        row = (await session.execute(select(representatives).where(representatives.c.grant_id == grant_id))).mappings().one()

    return envelope({
        "grant_id": row["grant_id"],
        "representative_subject": row["representative_subject"],
        "relation": row["relation"],
        "scopes": row["scopes"],
        "valid_until": row["valid_until"].isoformat(),
        "state": row["state"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    })


@router.post("/api/v1/members/me/representatives/{grant_id}/revocations")
async def revoke_representative(
    grant_id: str,
    actor: Actor = Depends(MEMBER),
    session: AsyncSession = Depends(db),
) -> dict:
    async with session.begin():
        row = (
            await session.execute(
                select(representatives).where(
                    representatives.c.grant_id == grant_id,
                    representatives.c.member_subject == actor.subject,
                )
            )
        ).mappings().first()
        if not row:
            raise Problem(404, "/problems/not-found", "Representative grant not found")

        now = datetime.now(UTC)
        if row["state"] == "ACTIVE":
            await session.execute(
                update(representatives)
                .where(representatives.c.grant_id == grant_id)
                .values(state="REVOKED", revoked_at=now)
            )
            await audit(
                session,
                actor_subject=actor.subject,
                actor_stakeholder=actor.stakeholder,
                action="representative.revoked",
                target_type="representative_grant",
                target_id=grant_id,
                detail=f"Representative grant {grant_id} revoked",
            )
            await _notify(session, actor.subject, "REPRESENTATIVE_REVOKED", grant_id, actor.correlation_id)
            revoked_at = now.isoformat()
        else:
            revoked_at = row["revoked_at"].isoformat() if row["revoked_at"] else None

    return envelope({
        "grant_id": grant_id,
        "representative_subject": row["representative_subject"],
        "state": "REVOKED",
        "revoked_at": revoked_at,
    })


@router.get("/api/v1/representatives/me/members")
async def list_my_acting_members(
    actor: Actor = Depends(REPRESENTATIVE),
    session: AsyncSession = Depends(db),
) -> dict:
    today = datetime.now(UTC).date()
    rows = (
        await session.execute(
            select(representatives, members.c.name.label("member_name"))
            .join(members, members.c.subject == representatives.c.member_subject)
            .where(
                representatives.c.representative_subject == actor.subject,
                representatives.c.state == "ACTIVE",
                representatives.c.valid_until >= today,
            )
            .order_by(representatives.c.created_at.desc())
        )
    ).mappings().all()

    return envelope([
        {
            "grant_id": r["grant_id"],
            "member_subject": r["member_subject"],
            "member_name": r["member_name"],
            "relation": r["relation"],
            "scopes": r["scopes"],
            "valid_until": r["valid_until"].isoformat(),
        }
        for r in rows
    ])


@router.get("/internal/representatives/{subject}/grants", include_in_schema=False)
async def internal_representative_grants(
    subject: str,
    actor: Actor = Depends(GATEWAY),
    session: AsyncSession = Depends(db),
) -> dict:
    today = datetime.now(UTC).date()
    rows = (
        await session.execute(
            select(representatives)
            .where(
                representatives.c.representative_subject == subject,
                representatives.c.state == "ACTIVE",
                representatives.c.valid_until >= today,
            )
            .order_by(representatives.c.created_at.desc())
        )
    ).mappings().all()

    return envelope({
        "subject": subject,
        "grants": [
            {
                "grant_id": r["grant_id"],
                "member_subject": r["member_subject"],
                "relation": r["relation"],
                "scopes": r["scopes"],
                "valid_until": r["valid_until"].isoformat(),
                "state": r["state"],
            }
            for r in rows
        ],
    })
