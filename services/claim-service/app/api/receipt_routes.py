"""Phase 2, slice 28h: claim receipt and public verification."""
import base64
from datetime import date
import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, load_claim
from app.config import settings
from app.infra.tables import accounts, claims
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence.policy import rules_on

router = APIRouter()


def receipt_code(claim_id: str, amount_paise: int | str, filed_on_iso: str, secret: str | None = None) -> str:
    """Pure function generating the 10-character uppercase base32 receipt verification code."""
    key = secret if secret is not None else settings.receipt_secret
    message = f"{claim_id}|{amount_paise}|{filed_on_iso}"
    mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(mac).decode("ascii").rstrip("=").upper()[:10]


def _filed_on_iso(created_at: Any) -> str:
    if hasattr(created_at, "date"):
        return created_at.date().isoformat()
    if isinstance(created_at, str):
        return created_at[:10]
    if created_at:
        return str(created_at)[:10]
    return date.today().isoformat()


@router.get("/api/v1/members/me/claims/{claim_id}/receipt")
async def get_receipt(claim_id: str, actor: Actor = Depends(require_stakeholder("member")),
                      session: AsyncSession = Depends(db)) -> dict:
    claim = await load_claim(session, claim_id, member=actor.subject)
    if claim["state"] == "AWAITING_CONFIRMATION":
        raise Problem(404, "/problems/not-found", "Receipt is not available until the claim is confirmed")

    rules = await rules_on(session, date.today())
    claim_label = (rules.get("claims", {}).get("types", {}).get(claim["claim_type"], {}).get("label")
                   or (claim.get("evaluation") or {}).get("label")
                   or claim["claim_type"])

    account = (await session.execute(
        select(accounts).where(accounts.c.account_link_id == claim["account_link_id"])
    )).mappings().first()

    uan = account["uan"] if account and account.get("uan") else (claim.get("death_of_uan") or "")
    uan_masked = f"********{uan[-4:]}" if uan and len(uan) >= 4 else (f"********{uan}" if uan else None)
    member_name = account.get("member_name") if account else None
    employer = account.get("establishment_name") if (account and "establishment_name" in account) else None

    filed_on = _filed_on_iso(claim.get("created_at"))
    code = receipt_code(claim["claim_id"], claim["amount_paise"], filed_on)
    verify_path = f"/public/receipts/verify?claim={claim['claim_id']}&code={code}"

    return envelope({
        "claim_id": claim["claim_id"],
        "form_type": claim["form_type"],
        "claim_label": claim_label,
        "amount_paise": claim["amount_paise"],
        "filed_on": filed_on,
        "state": claim["state"],
        "member_name": member_name,
        "uan_masked": uan_masked,
        "employer": employer,
        "code": code,
        "verify_path": verify_path,
    })


class ReceiptVerificationLookup(BaseModel):
    challenge_id: str
    answer: int
    claim_id: str = Field(pattern=r"^CLM-[0-9A-F]{8}$")
    code: str = Field(pattern=r"^[A-Z2-7]{10}$")


@router.post("/api/v1/public/receipts/verifications")
async def verify_receipt(body: ReceiptVerificationLookup,
                         actor: Actor = Depends(require_stakeholder("public")),
                         session: AsyncSession = Depends(db)) -> dict:
    row = (await session.execute(select(claims).where(claims.c.claim_id == body.claim_id))).mappings().first()
    known = bool(row) and row["state"] != "AWAITING_CONFIRMATION"
    # the same work whether or not the claim exists, so the answer's timing does not tell either
    filed_on = _filed_on_iso(row.get("created_at")) if known else date.today().isoformat()
    expected_code = receipt_code(body.claim_id, row["amount_paise"] if known else 0, filed_on)
    if not (hmac.compare_digest(body.code, expected_code) and known):
        return envelope({"genuine": False})

    return envelope({
        "genuine": True,
        "claim_id": row["claim_id"],
        "form_type": row["form_type"],
        "amount_paise": row["amount_paise"],
        "filed_on": filed_on,
        "state": row["state"],
    })
