"""Member and office views of the two Form 13 legs."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope

router = APIRouter()
MEMBER = require_stakeholder("member")
OFFICE = require_stakeholder("fo.da_accounts", "fo.ao")


def present(row) -> dict:
    detail = row["detail"] if isinstance(row["detail"], dict) else json.loads(row["detail"] or "{}")
    trust = detail.get("trust_name") or "the trust"
    pf_labels = {"COMPLETED": "Completed", "SENT_TO_TRUST": f"Sent to {trust}",
                 "AWAITING_TRUST": f"Waiting for the PF from {trust}",
                 "ANNEXURE_K_RECEIVED": "Annexure K received from the trust"}
    eps_labels = {"WAITING_FOR_PF": "Waiting for the PF transfer to complete", "COMPLETED": "Completed"}
    return {"transfer_id": row["transfer_id"], "direction": row["direction"],
            "from_account_link_id": row["from_account_link_id"], "to_account_link_id": row["to_account_link_id"],
            "pf_leg": {"state": row["pf_leg"], "label": pf_labels[row["pf_leg"]], "detail": detail},
            "eps_leg": {"state": row["eps_leg"], "label": eps_labels[row["eps_leg"]],
                        "detail": {"service_months": detail.get("service_months"),
                                   "breaks_months": detail.get("eps_breaks_months")}}}


@router.get("/api/v1/members/me/transfer-legs")
async def member_legs(actor: Actor = Depends(MEMBER)):
    async with sessions()() as session:
        rows = (await session.execute(text("""SELECT l.* FROM transfer_legs l WHERE EXISTS
            (SELECT 1 FROM establishment_members m WHERE m.uan=l.uan AND m.member_subject=:s)
            ORDER BY l.updated_at DESC"""), {"s": actor.subject})).mappings().all()
    return envelope({"transfers": [present(r) for r in rows]})


@router.get("/api/v1/office/transfers/{transferId}/legs")
async def office_legs(transferId: str, actor: Actor = Depends(OFFICE)):
    async with sessions()() as session:
        row = (await session.execute(text("SELECT * FROM transfer_legs WHERE transfer_id=:t"),
                                     {"t": transferId})).mappings().first()
    if not row:
        raise Problem(404, "/problems/not-found", "Transfer not found")
    return envelope(present(row))
