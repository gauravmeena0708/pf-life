"""P2.21b: what EPFO learns without being told by the family — a death from the civil registry — and what it hands the
member without being asked — documents in DigiLocker. Mock integrations, illustrative rules.

* Death feed. The Civil Registration System (mock) sends each registered death, signed. A record is matched to a member
  by the Aadhaar reference (else by name and date of birth, when exactly one member fits); the member's open member IDs
  are closed with the reason "death while in service" (marked by the civil registry) and the death is announced
  (MemberDeathRecorded.v1): claim-service records it and offers the nominees their claims filled in; pension-service
  stops a pension in payment and lets the family apply for the family pension. A repeated record is ignored; one that
  matches nobody, or more than one person, is kept for the office to look at.
* DigiLocker. The UAN card is issued when a UAN is allotted (or when the member asks), the PPO when it is dispatched.
  A worker pushes them to DigiLocker (mock) and retries while it is down."""
import hashlib
import hmac
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.exits import record_exit
from app.infra.tables import death_registrations, digilocker_documents, employments, members
from epfo_persistence import add_event

PRODUCER = "member-service"
ISSUER = "in.gov.epfindia.demo"                 # the mock issuer ID EPFO pushes under
RETRY_MINUTES = (1, 5, 15, 60)                  # illustrative; FAILED after the last
DOC_TITLES = {"UAN_CARD": "e-UAN card", "PPO": "e-PPO (pension payment order)"}


def crs_signature(registration_no: str, date_of_death: str, name: str) -> str:
    return hmac.new(settings.crs_secret.encode(), f"{registration_no}|{date_of_death}|{name}".encode(), hashlib.sha256).hexdigest()


async def announce_death(session: AsyncSession, uan: str, day: date, source: str, registration_no: str | None,
                         correlation_id: str | None) -> None:
    await add_event(session, producer=PRODUCER, event_type="MemberDeathRecorded.v1", aggregate_type="member", aggregate_id=uan,
                    correlation_id=correlation_id, payload={"uan": uan, "date_of_death": day.isoformat(), "source": source,
                                                            "registration_no": registration_no})


async def _match(session: AsyncSession, aadhaar_ref: str | None, name: str, date_of_birth: date) -> tuple[list[dict[str, Any]], str | None]:
    """The member records of one person: by the Aadhaar reference (all UANs of the person), else by name and date of birth
    when they point at a single person."""
    if aadhaar_ref:
        rows = (await session.execute(select(members).where(members.c.aadhaar_ref == aadhaar_ref))).mappings().all()
        if rows:
            return [dict(r) for r in rows], "AADHAAR"
    rows = (await session.execute(select(members).where(func.upper(members.c.name) == name.strip().upper(),
                                                        members.c.date_of_birth == date_of_birth))).mappings().all()
    people = {r["aadhaar_ref"] or r["uan"] for r in rows}
    return [dict(r) for r in rows], ("NAME_AND_DOB" if len(people) == 1 else None) if rows else None


async def record_registered_death(session: AsyncSession, *, registration_no: str, name: str, date_of_birth: date,
                                  date_of_death: date, aadhaar_ref: str | None, correlation_id: str | None) -> dict[str, Any]:
    prior = (await session.execute(select(death_registrations).where(death_registrations.c.registration_no == registration_no))).mappings().first()
    if prior:
        return {**dict(prior), "repeated": True}
    found, matched_by = await _match(session, aadhaar_ref, name, date_of_birth)
    outcome, uan, closed = "NOT_A_MEMBER", None, []
    if found and not matched_by:
        outcome = "AMBIGUOUS"
    elif found:
        uan = sorted(found, key=lambda m: m["uan"])[0]["uan"]
        for member in found:
            jobs = (await session.execute(select(employments).where(employments.c.member_id == member["member_id"],
                                                                    employments.c.date_of_exit.is_(None),
                                                                    employments.c.date_of_joining <= date_of_death))).mappings().all()
            for job in jobs:
                await record_exit(session, dict(job), date_of_death, "DEATH_IN_SERVICE", "CIVIL_REGISTRY", correlation_id)
                closed.append(job["account_link_id"])
        already = (await session.execute(select(employments.c.account_link_id).where(
            employments.c.member_id.in_([m["member_id"] for m in found]), employments.c.exit_reason == "DEATH_IN_SERVICE",
            employments.c.account_link_id.notin_(closed)))).first()
        outcome = "ALREADY_RECORDED" if already and not closed else "RECORDED"
        if outcome == "RECORDED":
            for member in found:
                await announce_death(session, member["uan"], date_of_death, "CIVIL_REGISTRY", registration_no, correlation_id)
    row = {"registration_no": registration_no, "name": name.strip().upper(), "date_of_birth": date_of_birth, "date_of_death": date_of_death,
           "aadhaar_ref": aadhaar_ref, "matched_uan": uan, "matched_by": matched_by, "outcome": outcome, "exits_marked": closed}
    await session.execute(insert(death_registrations).values(**row))
    return {**row, "repeated": False}


# ── DigiLocker ──────────────────────────────────────────────────────────────────────────────────

async def queue_document(session: AsyncSession, uan: str, doc_type: str, reference: str) -> dict[str, Any]:
    """Queue a document for DigiLocker once (by its reference); returns the row."""
    row = (await session.execute(select(digilocker_documents).where(digilocker_documents.c.reference == reference))).mappings().first()
    if row:
        return dict(row)
    now = datetime.now(UTC)
    values = {"doc_id": f"DL-{secrets.token_hex(5).upper()}", "uan": uan, "doc_type": doc_type, "reference": reference,
              "title": f"{DOC_TITLES[doc_type]} — {reference if doc_type == 'PPO' else 'UAN ending ' + uan[-4:]}",
              "state": "QUEUED", "attempts": 0, "next_attempt_at": now, "created_at": now, "updated_at": now}
    await session.execute(insert(digilocker_documents).values(**values))
    return values


async def on_ppo_issued(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p.get("pension_type", "MEMBER") not in ("MEMBER", "DISABLED"):
        return                      # a family pension's PPO belongs to the widow / child, who has no member record here
    if (await session.execute(select(members.c.uan).where(members.c.uan == p["uan"]))).first():
        await queue_document(session, p["uan"], "PPO", p["ppo_id"])


async def digilocker_transport(payload: dict[str, Any]) -> httpx.Response:
    path = "/mock-digilocker/documents"
    signature = hmac.new(settings.mock_gateway_secret.encode(), path.encode(), hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=3) as client:
        return await client.post(settings.mock_integrations_url.rstrip("/") + path, json=payload, headers={"X-Signature": signature})


async def push_documents_due(session: AsyncSession, now: datetime, transport=digilocker_transport) -> None:
    rows = (await session.execute(select(digilocker_documents).where(digilocker_documents.c.state == "QUEUED",
                                                                     digilocker_documents.c.next_attempt_at <= now)
                                  .order_by(digilocker_documents.c.created_at).limit(20)
                                  .with_for_update(skip_locked=True))).mappings().all()
    for row in rows:
        attempt = row["attempts"] + 1
        reference = row["reference"] if row["doc_type"] == "PPO" else row["doc_id"]     # never the full UAN outside EPFO
        payload = {"issuer_id": ISSUER, "doc_type": row["doc_type"], "reference": reference, "title": row["title"],
                   "uan_masked": "*" * 8 + row["uan"][-4:]}
        values: dict[str, Any] = {"attempts": attempt, "updated_at": now}
        try:
            response = await transport(payload)
            body = response.json()
            if 200 <= response.status_code < 300:
                values |= {"state": "ISSUED", "uri": body.get("uri"), "last_error": None, "next_attempt_at": None}
            elif 400 <= response.status_code < 500:
                values |= {"state": "FAILED", "last_error": str(body.get("status") or body.get("title") or response.status_code)[:300],
                           "next_attempt_at": None}
            else:
                raise httpx.HTTPError(str(body.get("title") or response.status_code))
        except (httpx.HTTPError, OSError, ValueError) as exc:
            if attempt > len(RETRY_MINUTES):
                values |= {"state": "FAILED", "last_error": f"DigiLocker unavailable after {attempt} attempts", "next_attempt_at": None}
            else:
                values |= {"last_error": str(exc)[:300] or "DigiLocker unavailable",
                           "next_attempt_at": now + timedelta(minutes=RETRY_MINUTES[attempt - 1])}
        await session.execute(update(digilocker_documents).where(digilocker_documents.c.doc_id == row["doc_id"]).values(**values))


def document_view(r: Any) -> dict[str, Any]:
    return {"doc_id": r["doc_id"], "doc_type": r["doc_type"], "title": r["title"], "state": r["state"], "uri": r["uri"],
            "attempts": r["attempts"], "last_error": r["last_error"],
            "issued_at": r["updated_at"].isoformat() if r["state"] == "ISSUED" and r["updated_at"] else None}
