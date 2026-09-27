"""Shared plumbing for EPFO POC services. Contains no business logic (init.md §11)."""
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = ["Problem", "envelope", "install", "correlation_id", "health_router", "get_logger"]

_correlation: ContextVar[str] = ContextVar("correlation_id", default="")
PROBLEM_JSON = "application/problem+json"


def correlation_id() -> str:
    """Correlation ID of the request being handled (empty outside a request)."""
    return _correlation.get()


def get_logger(name: str = "epfo") -> Any:
    return structlog.get_logger(name)


class Problem(Exception):
    """Raise to return an RFC 9457 Problem Details response."""

    def __init__(self, status: int, type_: str, title: str, detail: str | None = None, **extra: Any) -> None:
        super().__init__(title)
        self.status, self.type, self.title, self.detail, self.extra = status, type_, title, detail, extra

    def body(self) -> dict[str, Any]:
        body = {"type": self.type, "title": self.title, "status": self.status, "correlation_id": correlation_id()}
        if self.detail:
            body["detail"] = self.detail
        body.update(self.extra)
        return body


def envelope(data: Any, *, as_of: datetime | None = None) -> dict[str, Any]:
    """Standard success envelope (init.md §3.2)."""
    return {
        "data": data,
        "meta": {
            "correlation_id": correlation_id(),
            "api_version": "v1",
            "source": "synthetic-poc",
            "as_of": (as_of or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        },
    }


def _problem_response(status: int, type_: str, title: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(Problem(status, type_, title, detail).body(), status_code=status, media_type=PROBLEM_JSON)


def _configure_logging(service: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)


def install(app: FastAPI, service: str) -> None:
    """Add correlation IDs, JSON logging and Problem Details handlers to a FastAPI app."""
    _configure_logging(service)
    log = get_logger(service)

    @app.middleware("http")
    async def _correlation_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-correlation-id", "")
        try:
            cid = str(uuid.UUID(incoming))
        except ValueError:
            cid = str(uuid.uuid4())
        token = _correlation.set(cid)
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        try:
            response = await call_next(request)
        finally:
            _correlation.reset(token)
            structlog.contextvars.unbind_contextvars("correlation_id")
        response.headers["X-Correlation-Id"] = cid
        # Never log headers or bodies: they may carry tokens or personal data.
        log.info("request", method=request.method, path=request.url.path, status=response.status_code, correlation_id=cid)
        return response

    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status, media_type=PROBLEM_JSON)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        titles = {404: "Not found", 405: "Method not allowed"}
        return _problem_response(exc.status_code, f"/problems/http-{exc.status_code}", titles.get(exc.status_code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        problem = Problem(400, "/problems/validation", "Request is not valid", errors=[
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()])
        return JSONResponse(problem.body(), status_code=400, media_type=PROBLEM_JSON)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return _problem_response(500, "/problems/internal", "Unexpected error", "The error was logged with this correlation ID.")


def health_router(ready_check: Callable[[], Awaitable[bool]] | None = None) -> APIRouter:
    """`/health/live` always 200; `/health/ready` 200 only when `ready_check()` is true."""
    router = APIRouter(tags=["health"])

    @router.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @router.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        ok = True
        if ready_check is not None:
            try:
                ok = await ready_check()
            except Exception:  # readiness must never raise
                ok = False
        return JSONResponse({"status": "ready" if ok else "not-ready"}, status_code=200 if ok else 503)

    return router
