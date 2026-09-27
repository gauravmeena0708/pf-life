import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .internal_jwt import load_signing_key, public_jwks
from .oidc import router as oidc_router
from .permissions import load_permissions, stakeholder_for_claims
from .pipeline import handle_api
from .problems import problem
from .request_activity import record_activity
from .routing import load_routes
from .session import SessionStore

structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"),
                                structlog.processors.add_log_level,
                                structlog.processors.JSONRenderer()],
                    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))
logger = structlog.get_logger("gateway")


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        incoming = request.headers.get("x-correlation-id", "")
        try:
            correlation_id = str(uuid.UUID(incoming))
        except (ValueError, AttributeError):
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        await record_activity(request, response.status_code, round((time.perf_counter() - started) * 1000))
        return response


def create_app(*, redis_client=None, settings=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        yield
        await app.state.http_client.aclose()
        if redis_client is None:
            await app.state.redis.aclose()

    app = FastAPI(title="EPFO synthetic POC gateway", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(CorrelationMiddleware)
    app.state.settings = settings or get_settings()
    app.state.routes = load_routes()
    app.state.permissions = load_permissions()
    app.state.stakeholder_for_claims = lambda claims: stakeholder_for_claims(
        claims, set(app.state.permissions.keys()))
    app.state.redis = redis_client or redis.from_url(app.state.settings.redis_url, decode_responses=False)
    app.state.activity_hmac_key = secrets.token_bytes(32)
    if app.state.settings.gateway_session_fernet_key:
        fernet = Fernet(app.state.settings.gateway_session_fernet_key.encode())
    else:
        fernet = Fernet.generate_key()
        logger.warning("ephemeral session encryption key generated; sessions will not survive restart")
        fernet = Fernet(fernet)
    app.state.sessions = SessionStore(app.state.redis, fernet, app.state.settings.session_idle_seconds,
                                      app.state.settings.session_max_seconds)
    app.state.signing_key = load_signing_key(app.state.settings.gateway_signing_key_pem)
    if not app.state.settings.gateway_signing_key_pem:
        logger.warning("ephemeral internal JWT signing key generated; configure GATEWAY_SIGNING_KEY_PEM for stable JWKS")
    import httpx
    app.state.http_client = httpx.AsyncClient()
    app.include_router(oidc_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return problem(request, 400, "invalid-request", "Invalid request")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return problem(request, exc.status_code, "http-error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("unhandled gateway error", correlation_id=request.state.correlation_id)
        return problem(request, 500, "internal-error", "Internal gateway error")

    @app.get("/internal/jwks")
    async def jwks():
        return public_jwks(app.state.signing_key)

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready(request: Request):
        try:
            await request.app.state.redis.ping()
        except Exception:
            return problem(request, 503, "not-ready", "Redis is unavailable")
        return {"status": "ready"}

    @app.api_route("/api/v1/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def api(request: Request, path: str):
        return await handle_api(request, path)

    return app


app = create_app()
