"""Registering new joinees and member KYC (Phase 2, slice 2).

* An employer registers a joinee with a (mock) Aadhaar check: a new UAN, or — when the joinee already has one —
  a new member ID under that UAN (checked against name and date of birth). MemberRegistered.v1 tells the ledger,
  the claims projection and the process engine.
* A member seeds PAN or a bank account; a MOCK verifier (NSDL / penny-drop) answers at once; the employer's
  authorised signatory then approves with DSC / e-sign. On approval the member's KYC changes and
  MemberKycUpdated.v1 goes out (a verified PAN, for example, changes the TDS rate on withdrawals).

Every verifier here is a labelled mock: no real Aadhaar, PAN or bank account is ever checked."""
import hashlib
import re
import secrets
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import employments, kyc_requests, members
from epfo_observability import Problem
from epfo_persistence import add_event

PRODUCER = "member-service"
PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def mock_uidai(aadhaar: str) -> dict[str, Any]:
    """MOCK UIDAI: 12 digits, not starting with 0 or 1; numbers ending 0000 fail (to show the failure path)."""
    ok = bool(re.fullmatch(r"[2-9][0-9]{11}", aadhaar)) and not aadhaar.endswith("0000")
    return {"verifier": "MOCK UIDAI", "verified": ok, "reason": None if ok else "Aadhaar not verified (mock)"}


def mock_nsdl(pan: str, name: str) -> dict[str, Any]:
    """MOCK NSDL: a well-formed individual PAN (4th letter P) verifies; a PAN ending Z returns another name."""
    if not PAN.fullmatch(pan) or pan[3] != "P":
        return {"verifier": "MOCK NSDL", "verified": False, "reason": "Not a valid individual PAN (mock)"}
    if pan.endswith("Z"):
        return {"verifier": "MOCK NSDL", "verified": False, "reason": "Name on PAN does not match the UAN record (mock)"}
    return {"verifier": "MOCK NSDL", "verified": True, "name_on_pan": name}


def mock_penny_drop(ifsc: str, account_number: str) -> dict[str, Any]:
    """MOCK penny-drop: synthetic accounts ending 0000 are treated as closed."""
    ok = bool(IFSC.fullmatch(ifsc)) and bool(re.fullmatch(r"[0-9]{9,18}", account_number)) and not account_number.endswith("0000")
    return {"verifier": "MOCK penny-drop", "verified": ok, "reason": None if ok else "Account could not be validated (mock)"}


def mask(value: str, keep: int = 4) -> str:
    return "*" * max(0, len(value) - keep) + value[-keep:]


RESERVED_UAN, RESERVED_LINK = "100000000900", 900


async def _next_numbers(session: AsyncSession) -> tuple[str, str]:
    # UANs …900 onwards and member IDs AL-0900 onwards are reserved for special synthetic cases (a deceased member).
    top_uan = (await session.execute(select(func.max(members.c.uan)).where(members.c.uan < RESERVED_UAN))).scalar_one()
    links = (await session.execute(select(employments.c.account_link_id))).scalars().all()
    top_link = max((n for x in links if x.startswith("AL-") and (n := int(x.split("-")[1])) < RESERVED_LINK), default=0)
    return str(int(top_uan) + 1), f"AL-{top_link + 1:04d}"


async def register(session: AsyncSession, *, establishment_id: str, establishment_name: str, name: str, date_of_birth: date,
                   gender: str, aadhaar: str, mobile: str, date_of_joining: date, existing_uan: str | None, actor_subject: str,
                   correlation_id: str | None) -> dict[str, Any]:
    check = mock_uidai(aadhaar)
    if not check["verified"]:
        raise Problem(422, "/problems/aadhaar-not-verified", "Aadhaar could not be verified", check["reason"])
    uan, link = await _next_numbers(session)
    if existing_uan:                                        # previous employment: a new member ID under the same UAN
        member = (await session.execute(select(members).where(members.c.uan == existing_uan))).mappings().first()
        if not member or member["name"] != name.upper() or member["date_of_birth"] != date_of_birth:
            raise Problem(422, "/problems/uan-mismatch", "The UAN does not match this person",
                          "Name and date of birth must match the UAN record (use Joint Declaration to correct them).")
        open_here = (await session.execute(select(employments.c.account_link_id).where(
            employments.c.member_id == member["member_id"], employments.c.establishment_id == establishment_id,
            employments.c.date_of_exit.is_(None)))).first()
        if open_here:
            raise Problem(409, "/problems/already-employed", "Already an active member here", f"Member ID {open_here[0]}.")
        member_id, uan, new_uan = member["member_id"], member["uan"], False
    else:
        duplicate = (await session.execute(select(members.c.uan).where(func.upper(members.c.name) == name.upper(),
                                                                        members.c.date_of_birth == date_of_birth))).first()
        if duplicate:
            raise Problem(409, "/problems/possible-duplicate", "This person may already have a UAN",
                          "A member with the same name and date of birth exists; register against the existing UAN.")
        member_id, new_uan = f"DEMO{uan}", True
        await session.execute(insert(members).values(
            member_id=member_id, uan=uan, subject=None, name=name.upper(), date_of_birth=date_of_birth, gender=gender,
            mobile_masked=mask(mobile), email_masked="-", bank_ifsc="-", bank_account_last4="-",
            kyc={"aadhaar": "VERIFIED", "pan": "NOT_SEEDED", "bank": "NOT_SEEDED", "aadhaar_masked": mask(aadhaar)},
            aadhaar_ref=hashlib.sha256(f"demo-aadhaar:{aadhaar}".encode()).hexdigest()))   # links UANs of the same person
    office = (await session.execute(select(employments.c.office_id).where(employments.c.establishment_id == establishment_id,
                                                                          employments.c.office_id.is_not(None)).limit(1))).scalar_one_or_none()
    await session.execute(insert(employments).values(
        account_link_id=link, member_id=member_id, establishment_id=establishment_id, establishment_name=establishment_name,
        date_of_joining=date_of_joining, registered_by=actor_subject, office_id=office))
    member = (await session.execute(select(members).where(members.c.member_id == member_id))).mappings().one()
    await add_event(session, producer=PRODUCER, event_type="MemberRegistered.v1", aggregate_type="member_account",
                    aggregate_id=link, correlation_id=correlation_id, payload={
                        "uan": uan, "account_link_id": link, "member_subject": member["subject"], "name": member["name"],
                        "date_of_birth": member["date_of_birth"].isoformat(), "gender": member["gender"],
                        "establishment_id": establishment_id, "date_of_joining": date_of_joining.isoformat(), "new_uan": new_uan,
                        "pan_verified": (member["kyc"] or {}).get("pan") == "VERIFIED"})
    from app.domain.primary import recompute
    await recompute(session, uan, correlation_id)      # after MemberRegistered.v1, so other services have the member ID first
    return {"uan": uan, "account_link_id": link, "new_uan": new_uan, "name": member["name"],
            "aadhaar": check["verifier"] + ": verified"}


async def current_establishment(session: AsyncSession, member_id: str) -> str | None:
    return (await session.execute(select(employments.c.establishment_id).where(
        employments.c.member_id == member_id, employments.c.date_of_exit.is_(None))
        .order_by(employments.c.date_of_joining.desc()).limit(1))).scalar_one_or_none()


async def seed_kyc(session: AsyncSession, member: dict[str, Any], kyc_type: str, fields: dict[str, str], source: str,
                   submitted_by: str, establishment_id: str | None = None) -> dict[str, Any]:
    """Create a KYC request after the mock verifier's check; it waits for the employer's approval."""
    establishment_id = establishment_id or await current_establishment(session, member["member_id"])
    if not establishment_id:
        raise Problem(409, "/problems/no-current-employer", "No current employer to approve the KYC",
                      "KYC is approved by the present employer; with none, the field office approves it (not in this demonstration).")
    pending = (await session.execute(select(kyc_requests.c.request_id).where(
        kyc_requests.c.member_id == member["member_id"], kyc_requests.c.kyc_type == kyc_type,
        kyc_requests.c.state == "PENDING_EMPLOYER"))).first()
    if pending:
        raise Problem(409, "/problems/kyc-pending", f"A {kyc_type} KYC request is already waiting for approval", f"Request {pending[0]}.")
    if kyc_type == "PAN":
        pan = fields["number"].upper()
        check, masked, details = mock_nsdl(pan, member["name"]), mask(pan), {"name_on_document": member["name"]}
    elif kyc_type == "BANK":
        check = mock_penny_drop(fields["ifsc"].upper(), fields["account_number"])
        masked, details = mask(fields["account_number"]), {"ifsc": fields["ifsc"].upper(), "account_last4": fields["account_number"][-4:]}
    else:
        raise Problem(422, "/problems/validation", "Unsupported KYC type", "PAN or BANK.")
    request = {"request_id": f"KYC-{secrets.token_hex(4).upper()}", "member_id": member["member_id"], "uan": member["uan"],
               "kyc_type": kyc_type, "masked_value": masked, "details": details, "source": source,
               "state": "PENDING_EMPLOYER" if check["verified"] else "FAILED_VERIFICATION", "verification": check,
               "establishment_id": establishment_id, "submitted_by": submitted_by}
    await session.execute(insert(kyc_requests).values(**request))
    return request


async def decide_kyc(session: AsyncSession, request: dict[str, Any], approve: bool, note: str, actor_subject: str,
                     correlation_id: str | None) -> dict[str, Any]:
    now = datetime.now(UTC)
    state = "APPROVED" if approve else "REJECTED"
    await session.execute(update(kyc_requests).where(kyc_requests.c.request_id == request["request_id"]).values(
        state=state, decided_by=actor_subject, decision_note=note, decided_at=now))
    member = (await session.execute(select(members).where(members.c.member_id == request["member_id"]))).mappings().one()
    if approve:
        kyc = dict(member["kyc"] or {})
        values: dict[str, Any] = {}
        if request["kyc_type"] == "PAN":
            kyc.update(pan="VERIFIED", pan_masked=request["masked_value"])
        else:
            kyc["bank"] = "VERIFIED"
            values = {"bank_ifsc": request["details"]["ifsc"], "bank_account_last4": request["details"]["account_last4"]}
        await session.execute(update(members).where(members.c.member_id == member["member_id"]).values(kyc=kyc, **values))
        await add_event(session, producer=PRODUCER, event_type="MemberKycUpdated.v1", aggregate_type="member",
                        aggregate_id=member["uan"], correlation_id=correlation_id, payload={
                            "uan": member["uan"], "kyc_type": request["kyc_type"], "status": "VERIFIED",
                            "pan_verified": kyc.get("pan") == "VERIFIED",
                            "bank_ifsc": values.get("bank_ifsc", member["bank_ifsc"]),
                            "bank_account_last4": values.get("bank_account_last4", member["bank_account_last4"])})
    if member["subject"]:
        await add_event(session, producer=PRODUCER, event_type="NotificationRequested.v1", aggregate_type="notification",
                        aggregate_id=request["request_id"], correlation_id=correlation_id, payload={
                            "recipient_subject": member["subject"], "template": "KYC_APPROVED" if approve else "KYC_REJECTED",
                            "reference_id": request["request_id"], "params": {"parameter": request["kyc_type"], "reason": note}})
    return {**request, "state": state, "decision_note": note}
