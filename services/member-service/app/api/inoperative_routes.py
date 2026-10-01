"""Synthetic identity and inoperative-account checks (P2.12a). No external identity service is called."""
import hashlib
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.onboarding import _next_numbers, mask
from app.infra.db import sessions
from app.infra.tables import crowdsource_verifications, employments, members, office_staff
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit
from epfo_persistence.policy import rules_on, section

router = APIRouter()
ALLOT = require_stakeholder("csc_operator", "member")
MEMBER = require_stakeholder("member")
ACCOUNTS = require_stakeholder("fo.da_accounts")


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class Allotment(BaseModel):
    aadhaar: str = Field(pattern=r"^[0-9]{12}$")
    name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    gender: str = Field(pattern="^(MALE|FEMALE|TRANSGENDER)$")
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    face_auth_token: str


@router.post("/api/v1/members/uan-allotments", status_code=201)
async def allot_uan(body: Allotment, actor: Actor = Depends(ALLOT), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        if actor.stakeholder == "member":
            own = (await session.execute(select(members.c.uan).where(members.c.subject == actor.subject))).scalar_one_or_none()
            if own:
                raise Problem(409, "/problems/uan-exists", "A UAN already exists", f"Your UAN is {mask(own)}.")
            raise Problem(403, "/problems/member-not-linked", "No UAN is linked to this member login")
        if body.face_auth_token != "MOCK-FACE-MATCH":
            raise Problem(422, "/problems/face-auth-failed", "Face authentication failed", "The demonstration face token did not match.")
        reference = hashlib.sha256(f"demo-aadhaar:{body.aadhaar}".encode()).hexdigest()
        existing = (await session.execute(select(members.c.uan).where(members.c.aadhaar_ref == reference).limit(1))).scalar_one_or_none()
        if existing:
            raise Problem(409, "/problems/uan-exists", "A UAN already exists", f"Existing UAN: {mask(existing)}.")
        uan, _ = await _next_numbers(session)
        name = body.name.strip().upper()
        await session.execute(insert(members).values(
            member_id=f"DEMO{uan}", uan=uan, subject=None, name=name, date_of_birth=body.date_of_birth,
            gender=body.gender, mobile_masked=mask(body.mobile), email_masked="-", bank_ifsc="-",
            bank_account_last4="-", aadhaar_ref=reference,
            kyc={"aadhaar": "VERIFIED", "aadhaar_masked": mask(body.aadhaar), "pan": "NOT_SEEDED", "bank": "NOT_SEEDED"}))
        await add_event(session, producer="member-service", event_type="UanAllotted.v1", aggregate_type="member",
                        aggregate_id=uan, correlation_id=actor.correlation_id, payload={"uan": uan, "channel": "CSC"})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="uan.allotted",
                    target_type="member", target_id=uan, detail="CSC mock face authentication")
    return envelope({"uan": uan, "name": name,
                     "next_step": "Your employer links your member ID when you join; activate the UAN to log in."})


class Activation(BaseModel):
    uan: str = Field(pattern=r"^[0-9]{12}$")
    otp: str


@router.post("/api/v1/members/uan-activations")
async def activate_uan(body: Activation, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        own = (await session.execute(select(members).where(members.c.subject == actor.subject).with_for_update())).mappings().first()
        if not own or own["uan"] != body.uan:
            raise Problem(403, "/problems/not-your-uan", "This UAN does not belong to your login")
        if own["activated_at"]:
            raise Problem(409, "/problems/already-active", "This UAN is already active")
        if body.otp != "123456":
            raise Problem(422, "/problems/otp-failed", "OTP verification failed", "The demonstration OTP did not match.")
        now = datetime.now(UTC)
        await session.execute(update(members).where(members.c.member_id == own["member_id"]).values(activated_at=now))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="uan.activated",
                    target_type="member", target_id=body.uan, detail="Mock OTP")
    return envelope({"uan": body.uan, "activated_at": now.isoformat(), "demo": "Demo-only OTP: 123456",
                     "next_step": "You can now use your UAN to log in."})


class CrowdsourceVerification(BaseModel):
    co_worker_uans: list[str] = Field(min_length=1)
    note: str = Field(min_length=2, max_length=1000)


def _overlap(a_start: date, a_end: date | None, b_start: date, b_end: date | None) -> bool:
    return a_start <= (b_end or date.max) and b_start <= (a_end or date.max)


@router.post("/api/v1/office/accounts/{accountLinkId}/crowdsource-verifications", status_code=201)
async def verify_holder(accountLinkId: str, body: CrowdsourceVerification, actor: Actor = Depends(ACCOUNTS),
                        session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = (await session.execute(select(office_staff.c.office_id).where(
            office_staff.c.subject == actor.subject, office_staff.c.stakeholder == actor.stakeholder))).scalar_one_or_none()
        target = (await session.execute(select(employments, members.c.uan).join(
            members, members.c.member_id == employments.c.member_id).where(
            employments.c.account_link_id == accountLinkId).with_for_update())).mappings().first()
        if not target or not office or target["office_id"] != office:
            raise Problem(404, "/problems/not-found", "No account in your office with that member ID")
        if (await session.execute(select(crowdsource_verifications.c.account_link_id).where(
                crowdsource_verifications.c.account_link_id == accountLinkId))).first():
            raise Problem(409, "/problems/already-verified", "This member ID is already verified")
        rules = section(await rules_on(session, datetime.now(UTC).date()), "inoperative_accounts")
        required = rules["co_workers_required"]
        last = target["last_contribution_month"]
        threshold = datetime.now(UTC).date()
        threshold_month = threshold.year * 12 + threshold.month - rules["months_without_credit"]
        last_month = int(last[:4]) * 12 + int(last[5:7]) if last else None
        if last_month is None or last_month > threshold_month:
            raise Problem(422, "/problems/not-inoperative", "This member ID is not confirmed inoperative",
                          "A recorded last contribution month at least the configured number of months old is required.")
        proposed = list(dict.fromkeys(body.co_worker_uans))
        invalid = [u for u in proposed if len(u) != 12 or not u.isdigit() or u == target["uan"]]
        candidates = (await session.execute(select(members.c.uan, employments.c.date_of_joining,
                                                   employments.c.date_of_exit).join(
            employments, employments.c.member_id == members.c.member_id).where(
            members.c.uan.in_([u for u in proposed if u not in invalid]),
            employments.c.establishment_id == target["establishment_id"]))).all()
        qualified = {u for u, joined, exited in candidates if _overlap(target["date_of_joining"], target["date_of_exit"], joined, exited)}
        invalid += [u for u in proposed if u not in invalid and u not in qualified]
        if invalid or len(qualified) < required:
            raise Problem(422, "/problems/co-workers-not-qualified", "Co-worker verification requirements were not met",
                          f"Requires {required} distinct qualifying co-workers; {len(qualified)} qualified. Did not qualify: {', '.join(invalid) or 'none'}.",
                          fields=invalid)
        await session.execute(insert(crowdsource_verifications).values(
            account_link_id=accountLinkId, uan=target["uan"], co_worker_uans=sorted(qualified),
            note=body.note.strip(), verified_by=actor.subject, verified_by_office=office))
        await add_event(session, producer="member-service", event_type="InoperativeAccountVerified.v1",
                        aggregate_type="member_account", aggregate_id=accountLinkId, correlation_id=actor.correlation_id,
                        payload={"account_link_id": accountLinkId, "uan": target["uan"],
                                 "co_workers": len(qualified), "verified_by_office": office})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="inoperative_account.crowdsource_verified", target_type="member_account",
                    target_id=accountLinkId, detail=f"{len(qualified)} co-workers; office {office}")
    return envelope({"account_link_id": accountLinkId, "uan": target["uan"],
                     "co_workers": len(qualified), "verified_by_office": office})
