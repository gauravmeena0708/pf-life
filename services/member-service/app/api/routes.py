"""Member profile, employment and notification routes (Journey B)."""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import employments, members, notifications
from epfo_auth import Actor, require_grant, require_stakeholder
from epfo_observability import Problem, envelope

router = APIRouter()


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


async def _member(session: AsyncSession, subject: str) -> dict[str, Any]:
    row = (await session.execute(select(members).where(members.c.subject == subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Member not found")
    return dict(row)


def _employment(row: Any) -> dict[str, Any]:
    return {"account_link_id": row["account_link_id"], "establishment_name": row["establishment_name"],
            "date_of_joining": row["date_of_joining"].isoformat(),
            "date_of_exit": row["date_of_exit"].isoformat() if row["date_of_exit"] else None,
            "status": "EXITED" if row["date_of_exit"] else "ACTIVE"}


@router.get("/api/v1/members/me")
async def get_me(actor: Actor = Depends(require_stakeholder("member")), session: AsyncSession = Depends(db)) -> dict:
    member = await _member(session, actor.subject)
    links = (await session.execute(select(employments.c.account_link_id).where(
        employments.c.member_id == member["member_id"]).order_by(employments.c.date_of_joining.desc()))).scalars().all()
    return envelope({"member_id": member["member_id"], "uan": member["uan"], "name": member["name"],
                     "date_of_birth": member["date_of_birth"].isoformat(), "gender": member["gender"],
                     "mobile_masked": member["mobile_masked"], "email_masked": member["email_masked"],
                     "bank": {"ifsc": member["bank_ifsc"], "account_last4": member["bank_account_last4"]},
                     "kyc": member["kyc"], "account_link_ids": links})


@router.get("/api/v1/members/me/employment-history")
async def employment_history(actor: Actor = Depends(require_stakeholder("member")),
                             session: AsyncSession = Depends(db)) -> dict:
    member = await _member(session, actor.subject)
    rows = (await session.execute(select(employments).where(
        employments.c.member_id == member["member_id"]).order_by(employments.c.date_of_joining.desc()))).mappings().all()
    return envelope([_employment(row) for row in rows])


@router.get("/api/v1/members/me/identity-assurance")
async def identity_assurance(actor: Actor = Depends(require_stakeholder("member")),
                             session: AsyncSession = Depends(db)) -> dict:
    member = await _member(session, actor.subject)
    kyc = member["kyc"]
    pending = [name for name in ("aadhaar", "pan", "bank") if kyc.get(name) != "VERIFIED"]
    next_step = ("No further identity action is needed." if not pending else
                 f"Complete verification for {', '.join(pending)} in your member account.")
    return envelope({"kyc": kyc, "level": "PARTIAL" if pending else "FULL", "next_step": next_step})


@router.get("/api/v1/members/me/notifications")
async def list_notifications(actor: Actor = Depends(require_stakeholder("member")),
                             session: AsyncSession = Depends(db)) -> dict:
    await _member(session, actor.subject)
    rows = (await session.execute(select(notifications).where(
        notifications.c.recipient_subject == actor.subject).order_by(
        notifications.c.created_at.desc(), notifications.c.id.desc()).limit(50))).mappings().all()
    return envelope([{"id": row["id"], "template": row["template"], "reference_id": row["reference_id"],
                      "title": row["title"], "body": row["body"],
                      "created_at": row["created_at"].isoformat(),
                      "read_at": row["read_at"].isoformat() if row["read_at"] else None} for row in rows])


@router.get("/api/v1/employers/me/members")
async def employer_members(actor: Actor = Depends(require_stakeholder(
        "employer.owner", "employer.operator", "employer.signatory")),
        session: AsyncSession = Depends(db)) -> dict:
    if not any(grant in (actor.claims.get("grants") or []) for grant in ("ecr.prepare", "members.manage")):
        require_grant(actor, "ecr.prepare")
    if not actor.establishment_id:
        raise Problem(403, "/problems/no-establishment", "No establishment selected")
    rows = (await session.execute(select(members.c.uan, members.c.name, employments).join(
        employments, employments.c.member_id == members.c.member_id).where(
        employments.c.establishment_id == actor.establishment_id).order_by(members.c.name))).mappings().all()
    return envelope([{"uan": row["uan"], "name": row["name"], "account_link_id": row["account_link_id"],
                      "date_of_joining": row["date_of_joining"].isoformat(),
                      "date_of_exit": row["date_of_exit"].isoformat() if row["date_of_exit"] else None,
                      "status": "EXITED" if row["date_of_exit"] else "ACTIVE"} for row in rows])
