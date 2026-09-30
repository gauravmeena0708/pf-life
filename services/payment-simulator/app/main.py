"""payment-simulator — the MOCK bank. EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, routes
from app.config import settings
from app.infra.db import database_ready, engine
from epfo_observability import get_logger, health_router, install
from epfo_persistence import Consumer, OutboxRelay

log = get_logger("payment-simulator")


async def _mock_bank_loop() -> None:
    while True:
        try:
            await routes.process_due_payments()
        except Exception:
            log.exception("mock_bank_loop_error")
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    workers, bank = [], None
    if os.environ.get("DISABLE_MESSAGING") != "1":
        workers = [OutboxRelay(engine(), settings.rabbitmq_url),
                   Consumer(engine(), settings.rabbitmq_url, "payment-simulator.ecr",
                            ["contribution-service.ECRSubmitted.v1", "claim-service.PaymentInstructed.v1",
                             "contribution-service.ChallanGenerated.v1", "contribution-service.ChallanStatusChanged.v1",
                             "contribution-service.DemandStateChanged.v1"],
                            routes.dispatch)]
        for w in workers:
            w.start()
        bank = asyncio.create_task(_mock_bank_loop(), name="mock-bank")
    yield
    for w in workers:
        await w.stop()
    if bank:
        bank.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bank


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)
    install(app, settings.service_name)
    epfo_auth.configure(audience=settings.service_name, jwks=epfo_auth.JwksCache(settings.gateway_jwks_url))
    app.include_router(health_router(database_ready))
    app.include_router(routes.router)
    handled = {(m, r.path) for r in app.router.routes for m in getattr(r, "methods", set())}
    for route in catalogue_routes.router.routes:
        if not any((m, route.path) in handled for m in route.methods):
            app.router.routes.append(route)
    return app


app = create_app()
