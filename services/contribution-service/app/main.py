"""contribution-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, routes
from app.config import settings
from app.infra.db import database_ready
from app.infra.db import engine
from app.infra.messaging import handle_employer_verified, handle_payment_confirmed, handle_payment_returned
from epfo_persistence import Consumer, OutboxRelay
from epfo_observability import health_router, install


def create_app() -> FastAPI:
    routes.ruleset()  # Freeze and load the illustrative rule version at service startup.
    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("DISABLE_MESSAGING") != "1":
            relay = OutboxRelay(engine(), settings.rabbitmq_url)
            consumers = [
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.payments",
                         ["payment-simulator.PaymentConfirmed.v1", "payment-simulator.PaymentReturned.v1"], _payment_router),
                Consumer(engine(), settings.rabbitmq_url, "contribution-service.employers",
                         ["employer-service.EmployerVerified.v1"], handle_employer_verified),
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
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


async def _payment_router(session, event):
    if event.get("event_type") == "PaymentConfirmed.v1":
        await handle_payment_confirmed(session, event)
    elif event.get("event_type") == "PaymentReturned.v1":
        await handle_payment_returned(session, event)


app = create_app()
