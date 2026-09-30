"""e-Nomination (Form 2) and Know your UAN (Phase 2, slice 8b). Illustrative rules, not the EPF Scheme's text:

* e-Nomination needs a verified Aadhaar; it is signed with a mock Aadhaar e-sign (the step-up) and replaces the
  previous nomination, which is kept. Shares add up to 100%. A member who has a family may nominate only family
  members (EPF Scheme para 61, simplified); a married member has a family. A minor nominee needs a guardian.
  NominationRegistered.v1 tells claim-service, whose death claims pay the nominees on record.
* Know your UAN: name, date of birth and the mobile's last four digits, with a mock OTP sent to that mobile."""
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.infra.tables import employments, members, nominations
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
MEMBER = require_stakeholder("member")
PRODUCER = "member-service"
RELATIONS = ["SPOUSE", "SON", "DAUGHTER", "FATHER", "MOTHER", "BROTHER", "SISTER", "OTHER"]
FAMILY = {"SPOUSE", "SON", "DAUGHTER", "FATHER", "MOTHER"}          # illustrative
MAX_NOMINEES = 10


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class Nominee(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    relation: str
    date_of_birth: date
    share_bp: int = Field(gt=0, le=10_000)
    guardian_name: str | None = Field(default=None, max_length=120)


class NominationInput(BaseModel):
    has_family: bool
    nominees: list[Nominee] = Field(min_length=1, max_length=MAX_NOMINEES)


def age_on(born: date, day: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def nomination_problems(member: dict[str, Any], body: NominationInput, today: date) -> list[str]:
    """Why this nomination cannot be signed (empty: it can)."""
    problems = []
    if (member["kyc"] or {}).get("aadhaar") != "VERIFIED":
        problems.append("e-Nomination needs a verified Aadhaar on your UAN; ask your employer to approve your Aadhaar KYC first.")
    married = str((member["profile_extra"] or {}).get("marital_status", "")).upper() == "MARRIED"
    if married and not body.has_family:
        problems.append("Your profile says you are married, so you have a family; declare it.")
    total = sum(n.share_bp for n in body.nominees)
    if total != 10_000:
        problems.append(f"The shares add up to {total / 100:g}%; they must add up to 100%.")
    names = [n.name.strip().upper() for n in body.nominees]
    if len(set(names)) != len(names):
        problems.append("Each nominee can appear only once.")
    for n in body.nominees:
        if n.relation not in RELATIONS:
            problems.append(f"{n.name}: relation must be one of {', '.join(RELATIONS)}.")
        elif body.has_family and n.relation not in FAMILY:
            problems.append(f"{n.name}: a member with a family can nominate only family members ({', '.join(sorted(FAMILY))}).")
        if n.date_of_birth > today:
            problems.append(f"{n.name}: the date of birth cannot be in the future.")
        elif age_on(n.date_of_birth, today) < 18 and not (n.guardian_name or "").strip():
            problems.append(f"{n.name} is a minor: give a guardian's name.")
    return problems


def _nominee_view(n: dict[str, Any], today: date) -> dict[str, Any]:
    minor = age_on(date.fromisoformat(n["date_of_birth"]), today) < 18
    return {"name": n["name"], "relation": n["relation"], "date_of_birth": n["date_of_birth"], "share_bp": n["share_bp"],
            "minor": minor, "guardian_name": n.get("guardian_name") if minor else None}


def _view(row: dict[str, Any], today: date) -> dict[str, Any]:
    return {"nomination_id": row["nomination_id"], "state": row["state"], "has_family": row["has_family"],
            "signed_with": row["signed_with"], "signed_at": row["signed_at"].isoformat() if row["signed_at"] else None,
            "nominees": [_nominee_view(n, today) for n in row["nominees"]]}


async def _me(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    row = (await session.execute(select(members).where(members.c.subject == actor.subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Member not found")
    return dict(row)


@router.get("/api/v1/members/me/nominations")
async def my_nominations(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    m = await _me(session, actor)
    rows = (await session.execute(select(nominations).where(nominations.c.member_id == m["member_id"])
                                  .order_by(nominations.c.signed_at.desc()))).mappings().all()
    today = date.today()
    current = next((r for r in rows if r["state"] == "CURRENT"), None)
    return envelope({"uan": m["uan"], "current": _view(dict(current), today) if current else None,
                     "history": [_view(dict(r), today) for r in rows if r["state"] != "CURRENT"],
                     "aadhaar_verified": (m["kyc"] or {}).get("aadhaar") == "VERIFIED",
                     "relations": RELATIONS, "family_relations": sorted(FAMILY),
                     "note": "Illustrative rules: shares add up to 100%; a member with a family nominates family members only; "
                             "a minor nominee needs a guardian. Signed with a mock Aadhaar e-sign."})


@router.post("/api/v1/members/me/nominations", status_code=201)
async def nominate(body: NominationInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    today = date.today()
    async with session.begin():
        m = await _me(session, actor)
        problems = nomination_problems(m, body, today)
        if problems:
            raise Problem(422, "/problems/nomination-invalid", "This nomination cannot be signed", " ".join(problems), errors=problems)
        require_step_up(actor, "e-nominate", m["uan"])                  # the mock Aadhaar e-sign
        await session.execute(update(nominations).where(nominations.c.member_id == m["member_id"], nominations.c.state == "CURRENT")
                              .values(state="SUPERSEDED"))
        nomination_id = f"NOM-{secrets.token_hex(4).upper()}"
        stored = [{"name": n.name.strip().upper(), "relation": n.relation, "date_of_birth": n.date_of_birth.isoformat(),
                   "share_bp": n.share_bp, "guardian_name": (n.guardian_name or "").strip().upper() or None} for n in body.nominees]
        await session.execute(insert(nominations).values(nomination_id=nomination_id, member_id=m["member_id"], uan=m["uan"],
                                                         has_family=body.has_family, nominees=stored, state="CURRENT",
                                                         signed_with="MOCK_AADHAAR_ESIGN"))
        await add_event(session, producer=PRODUCER, event_type="NominationRegistered.v1", aggregate_type="member",
                        aggregate_id=m["uan"], correlation_id=actor.correlation_id, payload={
                            "nomination_id": nomination_id, "uan": m["uan"], "signed_with": "MOCK_AADHAAR_ESIGN",
                            "nominees": [{k: v for k, v in _nominee_view(n, today).items() if k != "date_of_birth"} for n in stored]})
        await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=nomination_id, correlation_id=actor.correlation_id, payload={
                            "recipient_subject": actor.subject, "template": "NOMINATION_REGISTERED", "reference_id": nomination_id,
                            "params": {"count": len(stored)}})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.e_nomination",
                    target_type="member", target_id=m["uan"], detail=f"{len(stored)} nominee(s)")
        row = (await session.execute(select(nominations).where(nominations.c.nomination_id == nomination_id))).mappings().one()
    return envelope(_view(dict(row), today))


class UanLookup(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    date_of_birth: date
    mobile_last4: str = Field(pattern=r"^[0-9]{4}$")
    otp: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/api/v1/members/uan-lookups")
async def know_your_uan(body: UanLookup, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """MOCK OTP: any six digits other than 000000 count as the code sent to the mobile."""
    if body.otp == "000000":
        raise Problem(422, "/problems/otp-invalid", "The one-time code is not correct", "Enter the code sent to the mobile (mock: any six digits except 000000).")
    async with session.begin():
        rows = (await session.execute(select(members).where(
            func.upper(members.c.name) == body.name.strip().upper(), members.c.date_of_birth == body.date_of_birth,
            members.c.mobile_masked.like(f"%{body.mobile_last4}")))).mappings().all()
        found = []
        for r in rows:
            jobs = (await session.execute(select(employments).where(employments.c.member_id == r["member_id"])
                                          .order_by(employments.c.date_of_joining.desc()))).mappings().all()
            latest = jobs[0] if jobs else None
            found.append({"uan": r["uan"], "aadhaar_verified": (r["kyc"] or {}).get("aadhaar") == "VERIFIED",
                          "latest_establishment": latest["establishment_name"] if latest else None,
                          "status": "ACTIVE" if latest and not latest["date_of_exit"] else "EXITED" if latest else "NO_SERVICE"})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.uan_lookup",
                    target_type="uan_lookup", target_id=f"******{body.mobile_last4}", detail=f"{len(found)} found")
    return envelope({"found": found, "sent_to": f"******{body.mobile_last4} (mock SMS)",
                     "note": "Matched on name, date of birth and the mobile number; the UAN is also sent by SMS (mock)."
                     if found else "No UAN matches these details. Check the spelling of the name as on Aadhaar."})
