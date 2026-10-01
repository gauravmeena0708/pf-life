"""Trust Annexure K submission and office receipt reconciliation (illustrative)."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import PRODUCER, db, staff_office
from app.infra.tables import accounts, annexure_k_requests, exempted_establishments
from epfo_auth import Actor, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit, find_response, request_hash, store_response

router = APIRouter()
TRUST = require_stakeholder("exempted.trust")
DA = require_stakeholder("fo.da_accounts")


def _view(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in row.items()}


async def _trust(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    rows = (await session.execute(select(exempted_establishments))).mappings().all()
    match = next((dict(r) for r in rows if r["status"] == "ACTIVE" and
                  any(u.get("subject") == actor.subject for u in r["trust_users"])), None)
    if not match:
        raise Problem(403, "/problems/forbidden", "No active exempted establishment is mapped to this trust user")
    return match


@router.get("/api/v1/exempted/me/annexure-k-requests")
async def requests(actor: Actor = Depends(TRUST), session: AsyncSession = Depends(db)) -> dict:
    trust = await _trust(session, actor)
    rows = (await session.execute(select(annexure_k_requests).where(
        annexure_k_requests.c.establishment_id == trust["establishment_id"],
        annexure_k_requests.c.trust_id == trust["trust_id"]).order_by(
            annexure_k_requests.c.created_at.desc()))).mappings().all()
    return envelope({"requests": [_view(dict(r)) for r in rows]})


class Submission(BaseModel):
    annexure_id: str
    employee_paise: int = Field(ge=0)
    employer_paise: int = Field(ge=0)
    service_from: date
    service_to: date
    breaks_months: int = Field(ge=0)
    interest_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def service_dates(self):
        if self.service_to < self.service_from:
            raise ValueError("service_to must be on or after service_from")
        return self


@router.post("/api/v1/exempted/me/annexure-k-submissions", status_code=201)
async def submit(body: Submission, request: Request, actor: Actor = Depends(TRUST),
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 session: AsyncSession = Depends(db)) -> dict:
    if not idempotency_key:
        raise Problem(400, "/problems/idempotency-key-required", "Idempotency-Key header is required")
    operation, h = f"POST {request.url.path}", request_hash(body.model_dump(mode="json"))
    async with session.begin():
        if cached := await find_response(session, actor.subject, operation, idempotency_key, h):
            return envelope(cached.body)
        trust = await _trust(session, actor)
        row = (await session.execute(select(annexure_k_requests).where(
            annexure_k_requests.c.annexure_id == body.annexure_id).with_for_update())).mappings().first()
        if not row or row["establishment_id"] != trust["establishment_id"] or row["trust_id"] != trust["trust_id"]:
            raise Problem(404, "/problems/not-found", "Annexure K request not found")
        if row["state"] != "REQUESTED":
            raise Problem(409, "/problems/invalid-state", "This Annexure K request is no longer awaiting submission")
        values = body.model_dump(exclude={"annexure_id"})
        await session.execute(update(annexure_k_requests).where(
            annexure_k_requests.c.annexure_id == body.annexure_id).values(**values, state="SUBMITTED"))
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="trust_annexure_k.submitted", target_type="annexure_k", target_id=body.annexure_id,
                    detail=str(body.employee_paise + body.employer_paise))
        result = _view({**dict(row), **values, "state": "SUBMITTED"})
        await store_response(session, actor.subject, operation, idempotency_key, h, 201, result)
    return envelope(result)


@router.get("/api/v1/office/exempted/annexure-k")
async def office_annexure_k(state: str = "SUBMITTED", actor: Actor = Depends(DA), session: AsyncSession = Depends(db)) -> dict:
    """The trusts' Annexure K for transfers into this office's member IDs, by state (SUBMITTED / MISMATCH await reconciling)."""
    async with session.begin():
        office = await staff_office(session, actor)
        rows = (await session.execute(select(annexure_k_requests).join(
            accounts, accounts.c.account_link_id == annexure_k_requests.c.to_account_link_id).where(
            accounts.c.office_id == office, annexure_k_requests.c.state == state))).mappings().all()
    items = []
    for r in rows:
        item = _view(dict(r))
        item["submitted_total_paise"] = int(r["employee_paise"] or 0) + int(r["employer_paise"] or 0)
        items.append(item)
    return envelope({"office_id": office, "state": state, "annexure_k": items})


class Reconciliation(BaseModel):
    receipt_ref: str = Field(min_length=1, max_length=100)
    received_paise: int = Field(ge=0)


@router.post("/api/v1/office/exempted/annexure-k/{annexureId}/reconciliations")
async def reconcile(annexureId: str, body: Reconciliation, actor: Actor = Depends(DA),
                    session: AsyncSession = Depends(db)) -> dict:
    async with session.begin():
        office = await staff_office(session, actor)
        row = (await session.execute(select(annexure_k_requests).where(
            annexure_k_requests.c.annexure_id == annexureId).with_for_update())).mappings().first()
        destination = (await session.execute(select(accounts.c.office_id).where(
            accounts.c.account_link_id == row["to_account_link_id"]))).scalar_one_or_none() if row else None
        if not row or destination != office:
            raise Problem(404, "/problems/not-found", "Annexure K request not found")
        if row["state"] not in ("SUBMITTED", "MISMATCH"):
            raise Problem(409, "/problems/invalid-state", "This Annexure K is not awaiting reconciliation")
        total = int(row["employee_paise"]) + int(row["employer_paise"])
        require_step_up(actor, "reconcile-trust-annexure-k", annexureId, None, total)
        difference = body.received_paise - total
        state = "MATCHED" if difference == 0 else "MISMATCH"
        await session.execute(update(annexure_k_requests).where(
            annexure_k_requests.c.annexure_id == annexureId).values(
                state=state, receipt_ref=body.receipt_ref, received_paise=body.received_paise,
                difference_paise=difference))
        if state == "MATCHED":
            await add_event(session, producer=PRODUCER, event_type="TrustAnnexureKReconciled.v1",
                            aggregate_type="annexure_k", aggregate_id=annexureId, correlation_id=actor.correlation_id,
                            payload={k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in {
                                "annexure_id": annexureId, "transfer_id": row["transfer_id"],
                                "to_account_link_id": row["to_account_link_id"], "employee_paise": int(row["employee_paise"]),
                                "employer_paise": int(row["employer_paise"]), "service_from": row["service_from"],
                                "service_to": row["service_to"], "breaks_months": row["breaks_months"]}.items()})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="trust_annexure_k.reconciled", target_type="annexure_k", target_id=annexureId,
                    detail=f"{state} {difference}")
    return envelope(_view({**dict(row), "state": state, "receipt_ref": body.receipt_ref,
                           "received_paise": body.received_paise, "difference_paise": difference}))
