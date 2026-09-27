"""mock-integrations — EPFO POC (SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM)."""
from fastapi import FastAPI

import epfo_auth
from app.api import catalogue_routes, routes
from app.config import settings
from app.infra.db import database_ready
from epfo_observability import health_router, install


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, version="0.1.0", docs_url="/docs", redoc_url=None)
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


app = create_app()
