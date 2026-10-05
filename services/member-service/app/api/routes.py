"""Member profile, employment and notification routes (Journey B)."""
import secrets
from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import sessions
from app.domain.exits import month_after, open_applications, record_exit, self_exit_problems, track
from app.infra.tables import (contact_history, employments, member_applications, members, notifications,
                              notification_preferences, notification_deliveries, notification_delivery_attempts,
                              office_staff, recovery_requests, security_reports)
from epfo_persistence.policy import rules_on, section
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


async def _member(session: AsyncSession, subject: str) -> dict[str, Any]:
    row = (await session.execute(select(members).where(members.c.subject == subject))).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Member not found")
    if row["account_state"] == "MERGED" and row.get("merged_into"):
        active = (await session.execute(select(members).where(members.c.uan == row["merged_into"]))).mappings().first()
        if active:
            return dict(active)
    return dict(row)


def _employment(row: Any) -> dict[str, Any]:
    return {"account_link_id": row["account_link_id"], "establishment_name": row["establishment_name"],
            "date_of_joining": row["date_of_joining"].isoformat(),
            "date_of_exit": row["date_of_exit"].isoformat() if row["date_of_exit"] else None,
            "exit_marked_by": row["exit_marked_by"], "last_contribution_month": row["last_contribution_month"],
            "transferred_to": row["transferred_to"],
            "status": "TRANSFERRED" if row["transferred_to"] else "EXITED" if row["date_of_exit"] else "ACTIVE"}


@router.get("/api/v1/members/me")
async def get_me(actor: Actor = Depends(require_stakeholder("member")), session: AsyncSession = Depends(db)) -> dict:
    member = await _member(session, actor.subject)
    links = (await session.execute(select(employments.c.account_link_id).where(
        employments.c.member_id == member["member_id"]).order_by(employments.c.date_of_joining.desc()))).scalars().all()
    return envelope({"member_id": member["member_id"], "uan": member["uan"], "name": member["name"],
                     "date_of_birth": member["date_of_birth"].isoformat(), "gender": member["gender"],
                     "mobile_masked": member["mobile_masked"], "email_masked": member["email_masked"],
                     "bank": {"ifsc": member["bank_ifsc"], "account_last4": member["bank_account_last4"]},
                     "kyc": member["kyc"], "account_link_ids": links, "account_state": member["account_state"],
                     "profile_extra": member["profile_extra"] or {},
                     "international_worker": bool(member["international"]),
                     "nationality": (member["international"] or {}).get("nationality")})


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
    passport_ok = bool(member["international"] and kyc.get("passport") == "VERIFIED" and
                       kyc.get("passport_expiry") and date.fromisoformat(kyc["passport_expiry"]) > datetime.now(UTC).date())
    pending = [name for name in ("aadhaar", "pan", "bank") if kyc.get(name) != "VERIFIED" and
               not (name == "aadhaar" and passport_ok)]
    next_step = ("No further identity action is needed." if not pending else
                 f"Complete verification for {', '.join(pending)} in your member account.")
    return envelope({"kyc": kyc, "level": "PARTIAL" if pending else "FULL", "next_step": next_step})


class IdentityEvidence(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    date_of_birth: date
    gender: Literal["MALE", "FEMALE", "TRANSGENDER"]


@router.post("/api/v1/members/me/identity-checks")
async def identity_check(body: IdentityEvidence, actor: Actor = Depends(require_stakeholder("member")),
                         session: AsyncSession = Depends(db)) -> dict:
    """Compare the mock e-KYC identity with the member record before a claim is filed."""
    member = await _member(session, actor.subject)
    # Joint Declaration SOP: core identity corrections use the existing major-change process.
    mismatches = [field for field, matches in (
        ("NAME", " ".join(body.name.upper().split()) == " ".join(member["name"].upper().split())),
        ("DATE_OF_BIRTH", body.date_of_birth == member["date_of_birth"]),
        ("GENDER", body.gender == member["gender"])) if not matches]
    return envelope({"mismatched_fields": mismatches, "claim_ready": not mismatches,
                     "correction_path": "/members/me/joint-declarations" if mismatches else None,
                     "next_step": "Submit a Joint Declaration for each differing field before claiming." if mismatches
                     else "Identity matches the member record."})


@router.get("/api/v1/members/me/notifications")
async def list_notifications(actor: Actor = Depends(require_stakeholder("member")),
                             session: AsyncSession = Depends(db)) -> dict:
    await _member(session, actor.subject)
    rows = (await session.execute(select(notifications).where(
        notifications.c.recipient_subject == actor.subject).order_by(
        notifications.c.created_at.desc(), notifications.c.id.desc()).limit(50))).mappings().all()
    ids = [row["id"] for row in rows]
    deliveries = (await session.execute(select(notification_deliveries).where(
        notification_deliveries.c.notification_id.in_(ids)))).mappings().all() if ids else []
    by_notice = {id: [] for id in ids}
    for delivery in deliveries:
        by_notice[delivery["notification_id"]].append({key: delivery[key] for key in
            ("channel", "state", "attempts", "destination_masked", "updated_at", "reason")})
        by_notice[delivery["notification_id"]][-1]["updated_at"] = delivery["updated_at"].isoformat()
    return envelope([{"id": row["id"], "template": row["template"], "reference_id": row["reference_id"],
                      "title": row["title"], "body": row["body"],
                      "deliveries": by_notice[row["id"]],
                      "created_at": row["created_at"].isoformat(),
                      "read_at": row["read_at"].isoformat() if row["read_at"] else None} for row in rows])


class PreferenceInput(BaseModel):
    sms: bool
    email: bool
    language: Literal["en", "hi"]


async def _preference_response(session: AsyncSession, subject: str) -> dict:
    row = (await session.execute(select(notification_preferences).where(
        notification_preferences.c.subject == subject))).mappings().first()
    rules = section(await rules_on(session, datetime.now(UTC).date()), "notifications")
    from app.domain.notifications import TEMPLATES, HI_TEMPLATES
    titles = HI_TEMPLATES if row and row["language"] == "hi" else TEMPLATES
    return {"sms": row["sms"] if row else True, "email": row["email"] if row else True,
            "language": row["language"] if row else "en",
            "updated_at": row["updated_at"].isoformat() if row else None,
            "essential_sms_titles": [titles[key][0] for key in rules["essential_templates"]],
            "essential_sms_notice": "Essential messages still go by SMS."}


@router.get("/api/v1/members/me/notification-preferences")
async def get_notification_preferences(actor: Actor = Depends(require_stakeholder("member")),
                                       session: AsyncSession = Depends(db)) -> dict:
    await _member(session, actor.subject)
    return envelope(await _preference_response(session, actor.subject))


@router.put("/api/v1/members/me/notification-preferences")
async def put_notification_preferences(body: PreferenceInput, actor: Actor = Depends(require_stakeholder("member")),
                                       session: AsyncSession = Depends(db)) -> dict:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    async with session.begin():
        await _member(session, actor.subject)
        insert_pref = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
        statement = insert_pref(notification_preferences).values(subject=actor.subject, **body.model_dump(),
                                                                  updated_at=datetime.now(UTC))
        await session.execute(statement.on_conflict_do_update(index_elements=[notification_preferences.c.subject],
            set_={key: statement.excluded[key] for key in ("sms", "email", "language", "updated_at")}))
        return envelope(await _preference_response(session, actor.subject))


OFFICE_NOTIFICATIONS = require_stakeholder("fo.pro", "ho.is")


@router.get("/api/v1/office/notification-deliveries")
async def office_notification_deliveries(state: str | None = None, actor: Actor = Depends(OFFICE_NOTIFICATIONS),
                                         session: AsyncSession = Depends(db)) -> dict:
    query = select(notification_deliveries, notifications.c.template).join(
        notifications, notifications.c.id == notification_deliveries.c.notification_id)
    if actor.stakeholder == "fo.pro":
        office = (await session.execute(select(office_staff.c.office_id).where(
            office_staff.c.subject == actor.subject, office_staff.c.stakeholder == "fo.pro"))).scalar_one_or_none()
        if not office:
            raise Problem(403, "/problems/no-office", "No office assignment")
        query = query.where(notification_deliveries.c.office_id == office)
    if state:
        query = query.where(notification_deliveries.c.state == state)
    rows = (await session.execute(query.order_by(notification_deliveries.c.created_at.desc()).limit(100))).mappings().all()
    ids = [row["delivery_id"] for row in rows]
    attempts = (await session.execute(select(notification_delivery_attempts).where(
        notification_delivery_attempts.c.delivery_id.in_(ids)).order_by(
        notification_delivery_attempts.c.attempt))).mappings().all() if ids else []
    return envelope([{**dict(row), "attempts_evidence": [dict(a) for a in attempts if a["delivery_id"] == row["delivery_id"]]}
                     for row in rows])


@router.post("/api/v1/office/notification-deliveries/{delivery_id}/retries")
async def retry_notification_delivery(delivery_id: str, actor: Actor = Depends(require_stakeholder("fo.pro")),
                                      session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = (await session.execute(select(office_staff.c.office_id).where(
            office_staff.c.subject == actor.subject, office_staff.c.stakeholder == "fo.pro"))).scalar_one_or_none()
        row = (await session.execute(select(notification_deliveries).where(
            notification_deliveries.c.delivery_id == delivery_id))).mappings().first()
        if not office or not row or row["office_id"] != office:
            raise Problem(404, "/problems/not-found", "Delivery not found")
        if row["state"] != "FAILED":
            raise Problem(409, "/problems/invalid-state", "Only failed deliveries can be sent again")
        note = f"Sent again by {actor.subject}"
        now = datetime.now(UTC)
        await session.execute(update(notification_deliveries).where(
            notification_deliveries.c.delivery_id == delivery_id).values(
            state="QUEUED", reason=note, next_attempt_at=now, last_error=None, updated_at=now))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="notification.delivery_retry", target_type="notification_delivery",
                    target_id=delivery_id, detail=note)
    return envelope({"delivery_id": delivery_id, "state": "QUEUED", "attempts": row["attempts"], "reason": note})


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
                      "status": "EXITED" if row["date_of_exit"] else "ACTIVE", "location": row["location"]} for row in rows])


# ── security self-service and reviewed account recovery (Journey D) ─────────────────────────────

class ContactInput(BaseModel):
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    email: str = Field(pattern=r"^[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,10}$")


class SecurityReportInput(BaseModel):
    kind: str                                              # NOT_ME | SUSPICIOUS_MESSAGE | OTHER
    description: str = Field(min_length=10, max_length=2000)


class RecoveryInput(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class RecoveryDecisionInput(BaseModel):
    decision: str                                          # APPROVE | REJECT
    note: str = Field(min_length=10, max_length=2000)


def mask_mobile(mobile: str) -> str:
    return "******" + mobile[-4:]


def mask_email(email: str) -> str:
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}"


async def _notify(session: AsyncSession, subject: str, template: str, reference_id: str, correlation_id: str) -> None:
    await add_event(session, producer="member-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=reference_id, correlation_id=correlation_id, payload={
                        "recipient_subject": subject, "template": template, "reference_id": reference_id, "params": {}})


@router.patch("/api/v1/members/me/contact-details")
async def change_contact(body: ContactInput, actor: Actor = Depends(require_stakeholder("member")),
                         session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        member = await _member(session, actor.subject)
        require_step_up(actor, "change-contact", member["member_id"])
        mobile, email = mask_mobile(body.mobile), mask_email(body.email)     # the raw values are not stored
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(
            mobile_masked=mobile, email_masked=email))
        await session.execute(insert(contact_history).values(member_id=member["member_id"], mobile_masked=mobile,
                                                             email_masked=email, source="MEMBER_CHANGE", verified=False))
        await _notify(session, actor.subject, "CONTACT_DETAILS_CHANGED", member["member_id"], actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.contact_change",
                    target_type="member", target_id=member["member_id"])
    return envelope({"mobile_masked": mobile, "email_masked": email,
                     "notice": "If you did not make this change, report it from your security page straight away."})


@router.post("/api/v1/members/me/security-reports", status_code=201)
async def security_report(body: SecurityReportInput, actor: Actor = Depends(require_stakeholder("member")),
                          session: AsyncSession = Depends(db)) -> dict:
    if body.kind not in ("NOT_ME", "SUSPICIOUS_MESSAGE", "OTHER"):
        raise Problem(422, "/problems/validation", "kind must be NOT_ME, SUSPICIOUS_MESSAGE or OTHER")
    async with session.begin():
        await _member(session, actor.subject)
        report_id = f"SEC-{secrets.token_hex(4).upper()}"
        await session.execute(insert(security_reports).values(report_id=report_id, subject=actor.subject, kind=body.kind,
                                                              description=body.description))
    return envelope({"report_id": report_id, "next_step": "The security team will review it. If you think someone "
                     "has your password, also ask for account recovery."})


@router.post("/api/v1/members/me/account-recovery-requests", status_code=201)
async def request_recovery(body: RecoveryInput, actor: Actor = Depends(require_stakeholder("member")),
                           session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        member = await _member(session, actor.subject)
        require_step_up(actor, "request-recovery", member["member_id"])
        pending = (await session.execute(select(recovery_requests.c.request_id).where(
            recovery_requests.c.subject == actor.subject, recovery_requests.c.state == "PENDING_REVIEW"))).first()
        if pending:
            raise Problem(409, "/problems/recovery-pending", "A recovery request is already waiting for review",
                          request_id=pending[0])
        verified = (await session.execute(select(contact_history).where(
            contact_history.c.member_id == member["member_id"], contact_history.c.verified.is_(True))
            .order_by(contact_history.c.id.desc()).limit(1))).mappings().first()
        if not verified:
            raise Problem(409, "/problems/no-verified-contact", "There are no verified contact details to restore",
                          "Visit your regional office with identity proof.")
        request_id = f"REC-{secrets.token_hex(4).upper()}"
        await session.execute(insert(recovery_requests).values(
            request_id=request_id, member_id=member["member_id"], subject=actor.subject, reason=body.reason,
            state="PENDING_REVIEW", restore_to={"mobile_masked": verified["mobile_masked"],
                                                "email_masked": verified["email_masked"]}))
    return envelope({"request_id": request_id, "state": "PENDING_REVIEW",
                     "next_step": "A security analyst will review the request. Nothing changes until then."})


@router.get("/api/v1/security/account-recovery-requests")
async def recovery_queue(actor: Actor = Depends(require_stakeholder("ho.security")),
                         session: AsyncSession = Depends(db)) -> dict:
    rows = (await session.execute(select(recovery_requests, members.c.mobile_masked, members.c.email_masked).join(
        members, members.c.member_id == recovery_requests.c.member_id).order_by(recovery_requests.c.created_at.desc()))).mappings().all()
    return envelope([{"request_id": r["request_id"], "member_id": r["member_id"], "reason": r["reason"], "state": r["state"],
                      "current": {"mobile_masked": r["mobile_masked"], "email_masked": r["email_masked"]},
                      "restore_to": r["restore_to"], "decision_note": r["decision_note"],
                      "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows])


@router.post("/api/v1/security/account-recovery-requests/{request_id}/decisions")
async def decide_recovery(request_id: str, body: RecoveryDecisionInput,
                          actor: Actor = Depends(require_stakeholder("ho.security")),
                          session: AsyncSession = Depends(db)) -> dict:
    if body.decision not in ("APPROVE", "REJECT"):
        raise Problem(422, "/problems/validation", "decision must be APPROVE or REJECT")
    async with session.begin():
        r = (await session.execute(select(recovery_requests).where(recovery_requests.c.request_id == request_id))).mappings().first()
        if not r:
            raise Problem(404, "/problems/not-found", "Recovery request not found")
        require_step_up(actor, "decide-recovery", request_id)
        if r["state"] != "PENDING_REVIEW":
            raise Problem(409, "/problems/already-decided", "This request was already decided", f"State: {r['state']}.")
        if r["subject"] == actor.subject:
            raise Problem(403, "/problems/separation-of-duties", "You cannot decide your own recovery request")
        state = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        await session.execute(update(recovery_requests).where(recovery_requests.c.request_id == request_id).values(
            state=state, reviewer_subject=actor.subject, decision_note=body.note, decided_at=datetime.now(UTC)))
        if state == "APPROVED":
            restore = r["restore_to"]
            await session.execute(update(members).where(members.c.member_id == r["member_id"]).values(
                mobile_masked=restore["mobile_masked"], email_masked=restore["email_masked"]))
            await session.execute(insert(contact_history).values(member_id=r["member_id"], source="RECOVERY", verified=True,
                                                                 mobile_masked=restore["mobile_masked"],
                                                                 email_masked=restore["email_masked"]))
        await _notify(session, r["subject"], f"ACCOUNT_RECOVERY_{state}", request_id, actor.correlation_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action=f"recovery.{state.lower()}",
                    target_type="recovery_request", target_id=request_id)
    return envelope({"request_id": request_id, "state": state,
                     "next_step": "Revoke the member's other sessions from the sessions page if the account was used by someone else."
                     if state == "APPROVED" else "The member's details are unchanged."})


# ── Phase 2, slice 1: Mark Exit, applications, service history ──────────────────────────────────

MEMBER = require_stakeholder("member")


class ExitInput(BaseModel):
    account_link_id: str = Field(min_length=1, max_length=40)
    date_of_exit: date
    reason: str = Field(default="CESSATION", pattern="^(CESSATION|SUPERANNUATION|RETIREMENT)$")


async def _own_jobs(session: AsyncSession, member: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (await session.execute(select(employments).where(employments.c.member_id == member["member_id"])
                                  .order_by(employments.c.date_of_joining.desc()))).mappings().all()
    return [dict(r) for r in rows]


@router.post("/api/v1/members/me/exits")
async def mark_exit(body: ExitInput, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """Manage › Mark Exit: the member marks the date of exit the employer has not marked (Aadhaar OTP → step-up)."""
    async with session.begin():
        member = await _member(session, actor.subject)
        job = next((j for j in await _own_jobs(session, member) if j["account_link_id"] == body.account_link_id), None)
        if not job:
            raise Problem(404, "/problems/not-found", "Member ID not found")
        ongoing = await open_applications(session, member["uan"])
        if ongoing:
            raise Problem(409, "/problems/process-ongoing", "Another process is already ongoing",
                          "Please wait for it to complete before submitting a new Mark Exit request.",
                          processes=[{"process": a["title"], "application_id": a["application_id"], "state": a["state"],
                                      "since": a["submitted_at"].isoformat()} for a in ongoing])
        problems = self_exit_problems(job, body.date_of_exit, datetime.now(UTC).date())
        if problems:
            raise Problem(422, "/problems/exit-not-allowed", "The exit cannot be marked", " ".join(problems), problems=problems)
        require_step_up(actor, "mark-exit", body.account_link_id)
        await record_exit(session, job, body.date_of_exit, body.reason, "MEMBER", actor.correlation_id)
        application_id = f"EXIT-{body.account_link_id}"
        await track(session, application_id, member["uan"], "mark_exit", "Mark Exit", "RECORDED", True, body.account_link_id)
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="member.exit_marked",
                    target_type="member_account", target_id=body.account_link_id, detail=body.date_of_exit.isoformat())
        job = (await session.execute(select(employments).where(employments.c.account_link_id == body.account_link_id))).mappings().one()
    return envelope({**_employment(job), "application_id": application_id,
                     "note": "The date of exit cannot be edited by you once marked; after a settlement it cannot be changed at all."})


@router.get("/api/v1/members/me/applications")
async def my_applications(status: str | None = None, actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    member = await _member(session, actor.subject)
    q = select(member_applications).where(member_applications.c.uan == member["uan"]).order_by(member_applications.c.updated_at.desc())
    if status == "pending":
        q = q.where(member_applications.c.terminal.is_(False))
    elif status == "processed":
        q = q.where(member_applications.c.terminal.is_(True))
    rows = (await session.execute(q)).mappings().all()
    return envelope([{"application_id": r["application_id"], "process": r["process"], "title": r["title"], "state": r["state"],
                      "pending": not r["terminal"], "account_link_id": r["account_link_id"],
                      "submitted_at": r["submitted_at"].isoformat(), "updated_at": r["updated_at"].isoformat()} for r in rows])


def _months(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month + (1 if end.day >= start.day else 0))


@router.get("/api/v1/members/me/service-history")
async def service_history(actor: Actor = Depends(MEMBER), session: AsyncSession = Depends(db)) -> dict:
    """Service per member ID: joining, exit, last contribution, months of service, and whether it was transferred."""
    member = await _member(session, actor.subject)
    today = datetime.now(UTC).date()
    out = []
    from app.domain.primary import aadhaar_set
    linked = [u for u in await aadhaar_set(session, member["uan"]) if u["uan"] != member["uan"]]
    for j in await _own_jobs(session, member):
        end = j["date_of_exit"] or today
        out.append({**_employment(j), "service_months": _months(j["date_of_joining"], end),
                    "primary": j["account_link_id"] == member["primary_account_link_id"],
                    "mark_exit_allowed": bool(not j["date_of_exit"] and j["last_contribution_month"]
                                              and today >= month_after(j["last_contribution_month"], 3)),
                    "transfer_status": ("Transferred to " + j["transferred_to"]) if j["transferred_to"] else
                                       ("Not transferred" if j["date_of_exit"] else "Current member ID")})
    return envelope({"uan": member["uan"], "member_ids": out, "primary_member_id": member["primary_account_link_id"],
                     "aadhaar_set_uans": sorted(u["uan"] for u in linked),
                     "note": "Claims and transfers are made against the primary member ID (P): the latest member ID that has "
                             "received contributions. Transfer the others to it (Form 13).",
                     "total_service_months": sum(x["service_months"] for x in out)})
