"""contribution-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, ledger_routes, returns_routes, routes, statement_routes, trust_routes
from app.config import settings
from app.infra.db import database_ready
from app.infra.db import engine
from app.infra.claims_ledger import on_claim_decision, on_claim_paid, on_tax_deducted
from app.infra.transfers import on_member_exit, on_member_registered, on_process_transitioned as on_transfer_step
from app.infra.messaging import handle_employer_verified, handle_member_change, handle_payment_confirmed, handle_payment_returned
from epfo_persistence import Consumer, OutboxRelay
from epfo_persistence.policy import on_policy_published
from epfo_observability import health_router, install


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("DISABLE_MESSAGING") != "1":
            relay = OutboxRelay(engine(), settings.rabbitmq_url)
            consumers = [
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.payments",
                         ["payment-simulator.PaymentConfirmed.v1", "payment-simulator.PaymentReturned.v1",
                          "compliance-service.DemandRaised.v1"], _payment_router),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.employers",
                         ["employer-service.EmployerVerified.v1"], handle_employer_verified),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.claims",
                         ["claim-service.ClaimDecisionRecorded.v1", "claim-service.TaxDeducted.v1",
                          "claim-service.AutoTransferConfirmed.v1"], _claims_router),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.policy",
                         ["platform-service.PolicyPublished.v1"], on_policy_published),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.members",
                         ["member-service.MemberChangeApproved.v1", "member-service.MemberExitMarked.v1",
                          "member-service.MemberRegistered.v1", "member-service.MemberInternationalStatusChanged.v1"], _members_router),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.processes",
                         ["workflow-service.ProcessTransitioned.v1"], on_transfer_step),
            ]
            relay.start()
            for consumer in consumers: consumer.start()
            app.state.messaging = (relay, consumers)
        yield
        if getattr(app.state, "messaging", None):
            relay, consumers = app.state.messaging
            await relay.stop()
            for consumer in consumers: await consumer.stop()

    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
    install(app, settings.service_name)
    epfo_auth.configure(audience=settings.service_name,
                        jwks=epfo_auth.JwksCache(settings.gateway_jwks_url))
    app.include_router(health_router(database_ready))
    app.include_router(routes.router)
    app.include_router(returns_routes.router)
    app.include_router(ledger_routes.router)
    app.include_router(statement_routes.router)
    app.include_router(trust_routes.router)
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


async def _payment_router(session, event):
    if event.get("event_type") == "PaymentConfirmed.v1" and event["payload"].get("purpose") == "CLAIM_SETTLEMENT":
        await on_claim_paid(session, event)
    elif event.get("event_type") == "PaymentConfirmed.v1" and event["payload"].get("purpose") == "DEMAND":
        from app.infra.demands import on_demand_paid
        await on_demand_paid(session, event)
    elif event.get("event_type") == "DemandRaised.v1":
        from app.infra.demands import on_demand_raised
        await on_demand_raised(session, event)
    elif event.get("event_type") == "PaymentConfirmed.v1":
        await handle_payment_confirmed(session, event)
    elif event.get("event_type") == "PaymentReturned.v1":
        await handle_payment_returned(session, event)


app = create_app()


async def _claims_router(session, event):
    if event.get("event_type") == "TaxDeducted.v1":
        await on_tax_deducted(session, event)
    elif event.get("event_type") == "AutoTransferConfirmed.v1":
        from app.infra.transfers import on_auto_transfer
        await on_auto_transfer(session, event)
    else:
        await on_claim_decision(session, event)


async def _members_router(session, event):
    if event.get("event_type") == "MemberExitMarked.v1":
        await on_member_exit(session, event)
    elif event.get("event_type") == "MemberInternationalStatusChanged.v1":      # P2.9a: full wages from the next return
        from sqlalchemy import text
        await session.execute(text("UPDATE establishment_members SET international_worker=:iw WHERE uan=:u"),
                              {"iw": bool(event["payload"]["international_worker"]), "u": event["payload"]["uan"]})
    elif event.get("event_type") == "MemberRegistered.v1":
        await on_member_registered(session, event)
    else:
        await handle_member_change(session, event)
