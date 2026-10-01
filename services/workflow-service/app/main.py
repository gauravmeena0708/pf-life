"""workflow-service — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, hr_routes, locks_routes, outreach_routes, routes, vigilance_routes
from app.engine.engine import build_router, definitions
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
                   Consumer(engine(), settings.rabbitmq_url, "workflow-service.events", BINDINGS, dispatch)]
        for w in workers:
            w.start()
    yield
    for w in workers:
        await w.stop()


def create_app() -> FastAPI:
    definitions()  # and the process definitions
    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
    install(app, settings.service_name)
    epfo_auth.configure(audience=settings.service_name,
                        jwks=epfo_auth.JwksCache(settings.gateway_jwks_url))
    app.include_router(health_router(database_ready))
    app.include_router(routes.router)
    app.include_router(locks_routes.router)
    app.include_router(hr_routes.router)
    app.include_router(outreach_routes.router)
    app.include_router(vigilance_routes.router)
    app.include_router(build_router())               # tier-2 processes from config/processes
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


app = create_app()
