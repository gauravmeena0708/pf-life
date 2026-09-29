"""claim-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, lifecycle_routes, routes
from app.config import settings
from app.infra.db import database_ready, engine
from app.infra.messaging import BINDINGS, dispatch
from epfo_observability import health_router, install
from epfo_persistence import Consumer, OutboxRelay


@asynccontextmanager
async def lifespan(app: FastAPI):
    workers = []
    if os.environ.get("DISABLE_MESSAGING") != "1":
        workers = [OutboxRelay(engine(), settings.rabbitmq_url),
                   Consumer(engine(), settings.rabbitmq_url, "claim-service.events", BINDINGS, dispatch)]
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
    app.include_router(lifecycle_routes.router)       # first: /members/me/claims/eligibility-preview before /{claim_id}
    app.include_router(routes.router)
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


app = create_app()
