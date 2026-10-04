"""Payroll provider authorisation routes (P2.22)."""
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import _establishment_of, _new_id, _now, _revoke, db
from app.infra.tables import grants, payroll_providers
from epfo_auth import Actor, require_grant, require_stakeholder, require_step_up
from epfo_observability import Problem, envelope
from epfo_persistence import add_event, audit

router = APIRouter()
OWNER = require_stakeholder("employer.owner")


def _owner_manage_grant(actor: Actor) -> str:
    held = actor.claims.get("grants") or []
    return "operators.manage" if "operators.manage" in held else "establishment.manage"


class AuthoriseProviderRequest(BaseModel):
    provider_id: str


class PayrollRevocation(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.get("/api/v1/employers/me/payroll-providers")
async def list_payroll_providers(
    actor: Actor = Depends(OWNER),
    session: AsyncSession = Depends(db),
) -> dict[str, Any]:
    est_id = _establishment_of(actor)
    providers = (
        await session.execute(select(payroll_providers).order_by(payroll_providers.c.provider_id))
    ).mappings().all()
    available = [{"provider_id": p["provider_id"], "name": p["name"]} for p in providers]

    auth_rows = (
        await session.execute(
            select(grants, payroll_providers.c.provider_id)
            .outerjoin(payroll_providers, grants.c.subject == payroll_providers.c.subject)
            .where(and_(grants.c.establishment_id == est_id, grants.c.kind == "PAYROLL"))
            .order_by(grants.c.created_at)
        )
    ).mappings().all()

    authorised = [
        {
            "grant_id": r["grant_id"],
            "provider_id": r["provider_id"] or "",
            "name": r["username"],
            "scopes": r["grants"],
            "status": r["status"],
            "granted_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in auth_rows
    ]

    return envelope({"available": available, "authorised": authorised})


@router.post("/api/v1/employers/me/payroll-providers/authorisations", status_code=201)
async def authorise_payroll_provider(
    body: AuthoriseProviderRequest,
    actor: Actor = Depends(OWNER),
    session: AsyncSession = Depends(db),
) -> dict[str, Any]:
    est_id = _establishment_of(actor)
    manage_grant = _owner_manage_grant(actor)
    require_grant(actor, manage_grant)
    require_step_up(actor, "authorise-payroll-provider", body.provider_id)

    grant_id = _new_id("GR")
    now = _now()
    async with session.begin():
        provider = (
            await session.execute(
                select(payroll_providers).where(payroll_providers.c.provider_id == body.provider_id)
            )
        ).mappings().first()
        if not provider:
            raise Problem(404, "/problems/not-found", "Payroll provider not found")

        active = (
            await session.execute(
                select(grants.c.grant_id).where(
                    and_(
                        grants.c.establishment_id == est_id,
                        grants.c.subject == provider["subject"],
                        grants.c.kind == "PAYROLL",
                        grants.c.status == "ACTIVE",
                    )
                )
            )
        ).first()
        if active:
            raise Problem(
                409,
                "/problems/already-authorised",
                f"{provider['name']} is already authorised for this establishment",
                "Revoke the existing authorisation first.",
            )

        await session.execute(
            grants.insert().values(
                grant_id=grant_id,
                establishment_id=est_id,
                subject=provider["subject"],
                username=provider["name"],
                kind="PAYROLL",
                grants=["payroll.submit"],
                status="ACTIVE",
                granted_by=actor.subject,
                created_at=now,
            )
        )
        await add_event(
            session,
            producer="employer-service",
            event_type="PayrollProviderAuthorised.v1",
            aggregate_type="establishment",
            aggregate_id=est_id,
            payload={
                "establishment_id": est_id,
                "provider_subject": provider["subject"],
                "grant_id": grant_id,
                "scopes": ["payroll.submit"],
            },
        )
        await audit(
            session,
            actor_subject=actor.subject,
            actor_stakeholder=actor.stakeholder,
            action="payroll_provider.authorised",
            target_type="grant",
            target_id=grant_id,
            detail=provider["provider_id"],
        )

    return envelope(
        {
            "grant_id": grant_id,
            "provider_id": provider["provider_id"],
            "name": provider["name"],
            "scopes": ["payroll.submit"],
            "status": "ACTIVE",
            "granted_at": now.isoformat(),
        }
    )


@router.post("/api/v1/employers/me/payroll-providers/authorisations/{grantId}/revocations")
async def revoke_payroll_provider(
    grantId: str,
    body: PayrollRevocation,
    actor: Actor = Depends(OWNER),
    session: AsyncSession = Depends(db),
) -> dict[str, Any]:
    manage_grant = _owner_manage_grant(actor)
    res = await _revoke(
        session=session,
        actor=actor,
        kind="PAYROLL",
        grant_id=grantId,
        reason=body.reason,
        manage_grant=manage_grant,
        step_action="revoke-payroll-provider",
        event_type="PayrollProviderRevoked.v1",
        subject_field="provider_subject",
    )
    provider = (
        await session.execute(
            select(payroll_providers).where(
                payroll_providers.c.subject == res["data"]["revocation"]["subject"]
            )
        )
    ).mappings().first()
    if provider:
        res["data"]["provider_id"] = provider["provider_id"]
        res["data"]["name"] = provider["name"]
    res["data"]["scopes"] = res["data"]["grants"]
    res["data"]["granted_at"] = res["data"]["created_at"]
    return res
