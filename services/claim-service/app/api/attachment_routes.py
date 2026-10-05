"""Phase 2, slice 19: Attachment / garnishee orders under EPF Act s.10.

Under Section 10 of the Employees' Provident Funds and Miscellaneous Provisions Act, 1952 (EPF Act s.10):
The amount standing to the credit of any member in the Fund, nominee amount, pension, and EDLI benefits
are immune from attachment under any decree or order of any court in respect of any debt or liability
incurred by the member. Maintenance orders are NOT exempt in the POC (refused citing s.10).
The sole exception is an order under the EPF Act itself (e.g. EPFO's own recovery).
Payments are never diverted.
"""
import secrets
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, staff_office
from app.infra.tables import accounts, attachment_orders, claims
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
PRODUCER = "claim-service"
OFFICE_OFFICER = require_stakeholder("fo.da_accounts", "fo.ss", "fo.ao", "fo.apfc", "fo.oic", "fo.legal", "fo.recovery_officer")

S10_REFUSAL_REASON = (
    "Refused under Section 10 of the Employees' Provident Funds and Miscellaneous Provisions Act, 1952 (EPF Act s.10): "
    "provident fund accumulations, nominee amounts, pension, and EDLI benefits are immune from attachment "
    "under any decree or order of any court in respect of any debt or liability incurred by the member, "
    "including maintenance orders."
)


class AttachmentOrderInput(BaseModel):
    order_number: str = Field(min_length=3, max_length=100)
    court_name: str = Field(min_length=3, max_length=200)
    order_date: date
    order_type: str = Field(pattern="^(COURT_DECREE|MAINTENANCE_ORDER|COMMERCIAL_DEBT|EPF_ACT_RECOVERY|OTHER)$")
    amount_paise: int = Field(gt=0)
    target_uan: str = Field(pattern=r"^[0-9]{12}$")
    claim_id: str | None = None
    debtor_name: str | None = None
    note: str | None = None


@router.post("/api/v1/office/attachment-orders", status_code=201)
async def record_attachment_order(body: AttachmentOrderInput,
                                  actor: Actor = Depends(OFFICE_OFFICER),
                                  session: AsyncSession = Depends(db)) -> dict:
    """Record a received attachment or garnishee order against a member's claim or balance.

    EPF Act s.10: returns refusal with s.10 reason, exception only for orders under EPF Act itself.
    """
    async with session.begin():
        office = await staff_office(session, actor)
        order_id = f"ATT-ORD-{secrets.token_hex(4).upper()}"

        # EPF Act s.10: only orders under the EPF Act itself are exempt from refusal
        if body.order_type == "EPF_ACT_RECOVERY":
            status = "ACCEPTED"
            refusal_reason = None
        else:
            # EPF Act s.10: maintenance orders and court decrees are NOT exempt; refuse citing s.10
            status = "REFUSED"
            refusal_reason = S10_REFUSAL_REASON

        values = {
            "order_id": order_id,
            "order_number": body.order_number,
            "court_name": body.court_name,
            "order_date": body.order_date,
            "order_type": body.order_type,
            "amount_paise": body.amount_paise,
            "target_uan": body.target_uan,
            "claim_id": body.claim_id,
            "debtor_name": body.debtor_name,
            "status": status,
            "refusal_reason": refusal_reason,
            "office_id": office,
            "recorded_by": actor.subject,
            "created_at": datetime.now(UTC),
        }
        await session.execute(insert(attachment_orders).values(**values))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="attachment_order.record", target_type="attachment_order", target_id=order_id,
                    detail=f"{body.order_type} {status} {body.order_number}")

        # Payments are never diverted (EPF Act s.10)
        result = {
            "order_id": order_id,
            "order_number": body.order_number,
            "court_name": body.court_name,
            "order_date": body.order_date.isoformat(),
            "order_type": body.order_type,
            "amount_paise": body.amount_paise,
            "target_uan": body.target_uan,
            "claim_id": body.claim_id,
            "debtor_name": body.debtor_name,
            "status": status,
            "refusal_reason": refusal_reason,
            "section": "EPF Act s.10",
            "payments_diverted": False,
            "office_id": office,
            "recorded_by": actor.subject,
            "created_at": values["created_at"].isoformat(),
        }
    return envelope(result)


@router.get("/api/v1/office/attachment-orders")
async def list_attachment_orders(actor: Actor = Depends(OFFICE_OFFICER),
                                 session: AsyncSession = Depends(db)) -> dict:
    """List attachment orders recorded in this office."""
    office = await staff_office(session, actor)
    rows = (await session.execute(
        select(attachment_orders).where(attachment_orders.c.office_id == office)
        .order_by(attachment_orders.c.created_at.desc())
    )).mappings().all()
    return envelope([{
        "order_id": r["order_id"],
        "order_number": r["order_number"],
        "court_name": r["court_name"],
        "order_date": r["order_date"].isoformat() if r["order_date"] else None,
        "order_type": r["order_type"],
        "amount_paise": r["amount_paise"],
        "target_uan": r["target_uan"],
        "claim_id": r["claim_id"],
        "debtor_name": r["debtor_name"],
        "status": r["status"],
        "refusal_reason": r["refusal_reason"],
        "section": "EPF Act s.10",
        "payments_diverted": False,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows])


@router.get("/api/v1/office/attachment-orders/{order_id}")
async def get_attachment_order(order_id: str,
                               actor: Actor = Depends(OFFICE_OFFICER),
                               session: AsyncSession = Depends(db)) -> dict:
    """Get single attachment order details."""
    office = await staff_office(session, actor)
    row = (await session.execute(
        select(attachment_orders).where(attachment_orders.c.order_id == order_id,
                                        attachment_orders.c.office_id == office)
    )).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Attachment order not found")
    return envelope({
        "order_id": row["order_id"],
        "order_number": row["order_number"],
        "court_name": row["court_name"],
        "order_date": row["order_date"].isoformat() if row["order_date"] else None,
        "order_type": row["order_type"],
        "amount_paise": row["amount_paise"],
        "target_uan": row["target_uan"],
        "claim_id": row["claim_id"],
        "debtor_name": row["debtor_name"],
        "status": row["status"],
        "refusal_reason": row["refusal_reason"],
        "section": "EPF Act s.10",
        "payments_diverted": False,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    })
