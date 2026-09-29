"""Phase 2, slice 5c: ANNEXURE K FILE and ANNEXURE K RECO — the inter-office transfer statements of Form 13 transfers,
outward from the office of the previous member ID and inward to the office of the new one, reconciled with the
transfer and the member records. (The amount against the VDR receipt is reconciled in contribution-service.)"""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import db, staff_office
from app.infra.tables import accounts, annexure_k_files
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()
DA = require_stakeholder("fo.da_accounts")


def _view(a: dict[str, Any], office: str) -> dict[str, Any]:
    direction = "OUTWARD" if a["from_office_id"] == office else "INWARD"
    if a["from_office_id"] == a["to_office_id"]:
        direction = "WITHIN_OFFICE"
    return {"annexure_id": a["annexure_id"], "uan": a["uan"], "direction": direction, "from_member_id": a["from_account_link_id"],
            "from_office_id": a["from_office_id"], "to_member_id": a["to_account_link_id"], "to_office_id": a["to_office_id"],
            "employee_paise": a["employee_paise"], "employer_paise": a["employer_paise"], "amount_paise": a["employee_paise"] + a["employer_paise"],
            "reco_status": a["reco_status"], "reco": a["reco"],
            "created_at": a["created_at"].isoformat() if hasattr(a["created_at"], "isoformat") else a["created_at"]}


@router.get("/api/v1/office/annexure-k-files")
async def annexure_files(direction: str | None = Query(default=None, pattern="^(INWARD|OUTWARD)$"), actor: Actor = Depends(DA),
                         session: AsyncSession = Depends(db)) -> dict:
    office = await staff_office(session, actor)
    q = select(annexure_k_files).order_by(annexure_k_files.c.created_at.desc())
    q = q.where(annexure_k_files.c.to_office_id == office if direction == "INWARD" else annexure_k_files.c.from_office_id == office
                if direction == "OUTWARD" else or_(annexure_k_files.c.to_office_id == office, annexure_k_files.c.from_office_id == office))
    rows = (await session.execute(q)).mappings().all()
    return envelope({"office_id": office, "direction": direction or "ALL", "files": [_view(dict(r), office) for r in rows]})


class Reco(BaseModel):
    declared_uan: str = Field(pattern=r"^[0-9]{12}$")
    declared_amount_paise: int = Field(ge=0)
    note: str = Field(default="", max_length=500)


@router.post("/api/v1/office/annexure-k-files/{annexureId}/reconciliations")
async def reconcile(annexureId: str, body: Reco, actor: Actor = Depends(DA), session: AsyncSession = Depends(db)) -> dict:
    """The figures on the Annexure K received from the other office are matched with the posted transfer and the
    member records: the same UAN, the same amount, and nothing left behind on the previous member ID."""
    async with session.begin():
        office = await staff_office(session, actor)
        a = (await session.execute(select(annexure_k_files).where(annexure_k_files.c.annexure_id == annexureId))).mappings().first()
        if not a or office not in (a["from_office_id"], a["to_office_id"]):
            raise Problem(404, "/problems/not-found", "Annexure K not found")
        if a["reco_status"] == "MATCHED":
            raise Problem(409, "/problems/already-reconciled", "This Annexure K is already reconciled")
        require_step_up(actor, "reconcile-annexure-k", annexureId)
        members = {r["account_link_id"]: dict(r) for r in (await session.execute(select(accounts).where(
            accounts.c.account_link_id.in_((a["from_account_link_id"], a["to_account_link_id"]))))).mappings().all()}
        frm, to = members.get(a["from_account_link_id"]), members.get(a["to_account_link_id"])
        checks = {"uan_matches": body.declared_uan == a["uan"],
                  "amount_matches": body.declared_amount_paise == a["employee_paise"] + a["employer_paise"],
                  "same_member_on_both_ids": bool(frm and to and frm["uan"] == to["uan"] == a["uan"]),
                  "nothing_left_on_previous_id": bool(frm) and frm["employee_paise"] + frm["employer_paise"] == 0}
        status = "MATCHED" if all(checks.values()) else "MISMATCH"
        reco = {"checks": checks, "declared_amount_paise": body.declared_amount_paise, "declared_uan": body.declared_uan, "note": body.note,
                "by_role": actor.stakeholder, "at": datetime.now(UTC).isoformat()}
        await session.execute(update(annexure_k_files).where(annexure_k_files.c.annexure_id == annexureId).values(reco_status=status, reco=reco))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder, action="annexure_k.reconciled",
                    target_type="annexure_k", target_id=annexureId, detail=status)
    return envelope(_view({**dict(a), "reco_status": status, "reco": reco}, office))
