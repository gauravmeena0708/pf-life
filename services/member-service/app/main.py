"""member-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, onboarding_routes, routes
from app.config import settings
from app.domain.notifications import handle_notification_requested
from app.domain.exits import on_contribution_posted, on_transfer_posted
from app.domain.processes import on_process_transitioned
from app.infra.db import database_ready, engine
from epfo_observability import health_router, install
from epfo_persistence import Consumer, OutboxRelay


@asynccontextmanager
async def lifespan(app: FastAPI):
    relay = None
    consumer = None
    if os.environ.get("DISABLE_MESSAGING") != "1":
        relay = OutboxRelay(engine(), settings.rabbitmq_url)
        consumer = Consumer(engine(), settings.rabbitmq_url, "member-service.notifications",
                            ["*.NotificationRequested.v1"], handle_notification_requested)
        processes = Consumer(engine(), settings.rabbitmq_url, "member-service.processes",
                             ["workflow-service.ProcessTransitioned.v1", "contribution-service.ContributionPosted.v1",
                              "contribution-service.TransferPosted.v1"], _route)
        relay.start()
        consumer.start()
        processes.start()
    yield
    if relay:
        await relay.stop()
    if consumer:
        await consumer.stop()
        await processes.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
    install(app, settings.service_name)
    epfo_auth.configure(audience=settings.service_name,
                        jwks=epfo_auth.JwksCache(settings.gateway_jwks_url))
    app.include_router(health_router(database_ready))
    app.include_router(routes.router)
    app.include_router(onboarding_routes.router)
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


app = create_app()


async def _route(session, event):
    handler = {"ProcessTransitioned.v1": on_process_transitioned, "ContributionPosted.v1": on_contribution_posted,
               "TransferPosted.v1": on_transfer_posted}.get(event["event_type"])
    if handler:
        await handler(session, event)
