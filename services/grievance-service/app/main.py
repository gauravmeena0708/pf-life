"""grievance-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, oversight_routes, public_routes, routes
from app.config import settings
from app.infra.db import database_ready, engine
from epfo_observability import health_router, install
from epfo_persistence import Consumer, OutboxRelay
from epfo_persistence.policy import on_policy_published


@asynccontextmanager
async def lifespan(app: FastAPI):
    workers = []
    if os.environ.get("DISABLE_MESSAGING") != "1":
        workers = [OutboxRelay(engine(), settings.rabbitmq_url),
                   Consumer(engine(), settings.rabbitmq_url, "grievance-service.policy",
                            ["platform-service.PolicyPublished.v1", "workflow-service.StaffPostingChanged.v1"], _dispatch)]
        for w in workers:
            w.start()
    yield
    for w in workers:
        await w.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
    install(app, settings.service_name)
    epfo_auth.configure(audience=settings.service_name,
                        jwks=epfo_auth.JwksCache(settings.gateway_jwks_url))
    app.include_router(health_router(database_ready))
    app.include_router(routes.router)
    app.include_router(public_routes.router)
    app.include_router(oversight_routes.router)
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


app = create_app()


async def _dispatch(session, event):
    if event["event_type"] == "StaffPostingChanged.v1":                 # HR re-posted an officer (P2.8e)
        from app.infra.tables import office_staff
        from epfo_persistence.postings import apply_posting
        await apply_posting(session, event, office_staff)
    else:
        await on_policy_published(session, event)
