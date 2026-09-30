"""payment-simulator: the MOCK bank for challan payments (Journey A6). Never moves real money."""
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import and_, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.bank import sign, verify
from app.infra.db import sessions
from app.infra.tables import bank_nonces, payables, payment_intents
from epfo_auth import Actor, require_actor, require_grant, require_step_up, require_stakeholder
from epfo_observability import Problem, envelope, get_logger
from epfo_persistence import add_event, audit, find_response, request_hash, store_response

router = APIRouter()
log = get_logger("payment-simulator")
PRODUCER = "payment-simulator"


async def db() -> AsyncSession:
    async with sessions()() as session:
        yield session


class PaymentIntent(BaseModel):
    channel: str = "NET_BANKING"
    demo_scenario: str = "SUCCESS"  # SUCCESS | RETURN | STUCK (never answered: the office rejects it) — a demo switch


@router.post("/api/v1/employers/me/challans/{trrn}/payment-intents", status_code=202)
async def create_payment_intent(trrn: str, body: PaymentIntent, request: Request,
                                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                                actor: Actor = Depends(require_stakeholder("employer.signatory")),
                                session: AsyncSession = Depends(db)) -> Any:
    if not idempotency_key:
        raise Problem(400, "/problems/idempotency-key-required", "Idempotency-Key header is required",
                      "Send a unique Idempotency-Key so a retried payment is never charged twice.")
    if body.channel == "BANK_COUNTER":
        raise Problem(501, "/problems/planned", "Bank-counter (cash) payment is not available",
                      "Whether cash / counter payment is still permitted is unconfirmed (docs/endpoint-catalogue.md, status ?).")
    if body.channel != "NET_BANKING" or body.demo_scenario not in ("SUCCESS", "RETURN", "STUCK"):
        raise Problem(422, "/problems/validation", "Unsupported channel or scenario")
    require_grant(actor, "payment.initiate")
    operation, h = f"POST /employers/me/challans/{trrn}/payment-intents", request_hash(body.model_dump())
    async with session.begin():
        cached = await find_response(session, actor.subject, operation, idempotency_key, h)
        if cached:
            return envelope(cached.body)
        payable = (await session.execute(select(payables).where(payables.c.trrn == trrn))).mappings().first()
        if not payable or payable["establishment_id"] != actor.establishment_id:
            raise Problem(404, "/problems/not-found", "Challan not found",
                          "If the return was submitted just now, wait a few seconds and try again.")
        require_step_up(actor, "pay-challan", trrn, None, payable["total_paise"])
        if payable["status"] == "CANCELLED":
            raise Problem(409, "/problems/challan-cancelled", "This challan is cancelled", "It can no longer be paid.")
        if payable["status"] in ("PENDING", "PAID"):
            raise Problem(409, "/problems/already-paid", f"This challan is already {payable['status'].lower()}",
                          "Check the challan status; a second payment is not needed.")
        payment_id = f"PAY-{secrets.token_hex(6).upper()}"
        await session.execute(insert(payment_intents).values(
            payment_id=payment_id, trrn=trrn, amount_paise=payable["total_paise"], channel=body.channel,
            scenario=body.demo_scenario, status="PENDING", created_by=actor.subject))
        await session.execute(update(payables).where(payables.c.trrn == trrn).values(status="PENDING"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="payment.initiated", target_type="challan", target_id=trrn, detail=payment_id)
        result = {"payment_id": payment_id, "trrn": trrn, "amount_paise": payable["total_paise"], "status": "PENDING",
                  "mock": True, "next_step": "The mock bank confirms in a few seconds; the challan then shows PAID."}
        await store_response(session, actor.subject, operation, idempotency_key, h, 202, result)
    return envelope(result)


# ── Mock bank callbacks (signed, replay-protected, idempotent) ─────────────────────────────────

async def apply_bank_callback(session: AsyncSession, kind: str, body: bytes, timestamp: str, nonce: str,
                              signature: str) -> dict[str, Any]:
    reason = verify(settings.mock_bank_hmac_secret, timestamp, nonce, body, signature)
    if reason:
        raise Problem(401, "/problems/bad-signature", "Bank callback rejected", reason)
    if (await session.execute(select(bank_nonces).where(bank_nonces.c.nonce == nonce))).first():
        raise Problem(409, "/problems/replayed-callback", "Bank callback rejected", "This nonce was already used.")
    await session.execute(insert(bank_nonces).values(nonce=nonce))
    data = json.loads(body)
    intent = (await session.execute(select(payment_intents).where(
        payment_intents.c.payment_id == data["payment_id"]))).mappings().first()
    if not intent:
        raise Problem(404, "/problems/not-found", "Unknown payment")
    target = "CONFIRMED" if kind == "confirmation" else "RETURNED"
    if intent["status"] != "PENDING":  # duplicate delivery of an already-applied result: same answer, no side effect
        return {"payment_id": intent["payment_id"], "status": intent["status"], "duplicate": True}
    now = datetime.now(UTC)
    await session.execute(update(payment_intents).where(payment_intents.c.payment_id == intent["payment_id"]).values(
        status=target, settled_at=now, bank_reference=data.get("bank_reference")))
    challan = intent["purpose"] == "CHALLAN"
    if challan:
        await session.execute(update(payables).where(payables.c.trrn == intent["trrn"]).values(
            status="PAID" if target == "CONFIRMED" else "FAILED"))
    reference = {"purpose": intent["purpose"], "reference_type": "trrn" if challan else "claim"}
    reference_id = intent["trrn"] if challan else intent["reference_id"]
    if target == "CONFIRMED":
        await add_event(session, producer=PRODUCER, event_type="PaymentConfirmed.v1", aggregate_type="payment",
                        aggregate_id=intent["payment_id"], payload={
                            "payment_id": intent["payment_id"], **reference, "reference_id": reference_id,
                            "amount_paise": intent["amount_paise"], "mock": True})
    else:
        await add_event(session, producer=PRODUCER, event_type="PaymentReturned.v1", aggregate_type="payment",
                        aggregate_id=intent["payment_id"], payload={
                            "payment_id": intent["payment_id"], **reference, "reference": reference_id,
                            "return_reason": data.get("return_reason", "MOCK_RETURN"), "mock": True})
    return {"payment_id": intent["payment_id"], "status": target, "duplicate": False}


async def _callback(kind: str, request: Request, session: AsyncSession) -> dict:
    body = await request.body()
    h = request.headers
    async with session.begin():
        result = await apply_bank_callback(session, kind, body, h.get("x-bank-timestamp", ""), h.get("x-bank-nonce", ""),
                                           h.get("x-bank-signature", ""))
    return envelope(result)


@router.post("/api/v1/integrations/mock-bank/payment-confirmations")
async def bank_confirmation(request: Request, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    return await _callback("confirmation", request, session)


@router.post("/api/v1/integrations/mock-bank/payment-returns")
async def bank_return(request: Request, actor: Actor = Depends(require_actor), session: AsyncSession = Depends(db)) -> dict:
    return await _callback("return", request, session)


async def process_due_payments() -> int:
    """The mock bank: settles PENDING intents after the configured delay, through the same signed path
    a real bank callback would use. Runs from a poller, so it survives restarts."""
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.mock_bank_delay_seconds)
    async with sessions()() as session:
        due = (await session.execute(select(payment_intents).where(and_(
            payment_intents.c.status == "PENDING", payment_intents.c.scenario != "STUCK", payment_intents.c.created_at <= cutoff)).limit(20))).mappings().all()
    done = 0
    for intent in due:
        kind = "return" if intent["scenario"] == "RETURN" else "confirmation"
        body = json.dumps({"payment_id": intent["payment_id"], "bank_reference": f"MOCKBANK-{secrets.token_hex(4).upper()}",
                           "return_reason": "MOCK_ACCOUNT_CLOSED" if kind == "return" else None}).encode()
        ts, nonce = str(int(time.time())), secrets.token_hex(16)
        async with sessions()() as session:
            try:
                async with session.begin():
                    await apply_bank_callback(session, kind, body, ts, nonce, sign(settings.mock_bank_hmac_secret, ts, nonce, body))
                done += 1
            except Problem as p:
                log.warning("mock_bank_callback_rejected", payment_id=intent["payment_id"], reason=p.detail)
    return done


# ── Event handlers: challans from submitted returns, claim settlements from payment instructions ──

async def on_ecr_submitted(session: AsyncSession, event: dict) -> None:
    p = event["payload"]
    if not (await session.execute(select(payables.c.trrn).where(payables.c.trrn == p["trrn"]))).first():
        await session.execute(insert(payables).values(
            trrn=p["trrn"], establishment_id=p["establishment_id"], filing_id=p["filing_id"],
            total_paise=p["total_paise"], status="DUE"))


async def on_payment_instructed(session: AsyncSession, event: dict) -> None:
    """A claim settlement instructed by claim-service; the mock bank settles it like a challan payment."""
    p = event["payload"]
    if (await session.execute(select(payment_intents.c.payment_id).where(
            payment_intents.c.payment_id == p["payment_id"]))).first():
        return
    await session.execute(insert(payment_intents).values(
        payment_id=p["payment_id"], purpose="CLAIM_SETTLEMENT", reference_id=p["claim_id"],
        amount_paise=p["amount_paise"], channel="NEFT", scenario=p.get("demo_scenario", "SUCCESS"),
        status="PENDING", created_by="claim-service"))


async def on_challan_generated(session: AsyncSession, event: dict) -> None:
    """A direct challan (administrative charges, 14B / 7Q) becomes payable like a return's challan."""
    p = event["payload"]
    if not (await session.execute(select(payables.c.trrn).where(payables.c.trrn == p["trrn"]))).first():
        await session.execute(insert(payables).values(trrn=p["trrn"], establishment_id=p["establishment_id"], filing_id=p["reference_id"],
                                                      total_paise=p["total_paise"], status="DUE"))


async def on_challan_status(session: AsyncSession, event: dict) -> None:
    """Cancelled / rejected: the challan is no longer payable. Payment rejected by the office: a payment stuck at
    the bank is dropped and the challan can be paid again."""
    p = event["payload"]
    if p["status"] in ("CANCELLED", "REJECTED"):
        await session.execute(update(payables).where(payables.c.trrn == p["trrn"]).values(status="CANCELLED"))
    elif p["status"] == "SETTLED_OFFLINE":                          # paid by cheque / DD, allocated by the office
        await session.execute(update(payables).where(payables.c.trrn == p["trrn"]).values(status="PAID"))
    elif p["status"] == "PAYMENT_REJECTED":
        await session.execute(update(payment_intents).where(payment_intents.c.trrn == p["trrn"], payment_intents.c.status == "PENDING")
                              .values(status="REJECTED"))
        await session.execute(update(payables).where(payables.c.trrn == p["trrn"]).values(status="FAILED"))


async def dispatch(session: AsyncSession, event: dict) -> None:
    handler = {"ECRSubmitted.v1": on_ecr_submitted, "PaymentInstructed.v1": on_payment_instructed,
               "ChallanGenerated.v1": on_challan_generated, "ChallanStatusChanged.v1": on_challan_status}.get(event["event_type"])
    if handler:
        await handler(session, event)
