import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from epfo_observability import Problem, envelope, health_router, install


def make_app(ready: bool = True) -> FastAPI:
    app = FastAPI()
    install(app, "test-service")

    async def check() -> bool:
        return ready

    app.include_router(health_router(check))

    @app.get("/ok")
    async def ok() -> dict:
        return envelope({"x": 1})

    @app.get("/problem")
    async def problem() -> None:
        raise Problem(409, "/problems/conflict", "Version conflict", "Reload and try again")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail must not leak")

    return app


def test_envelope_and_correlation_id_echoed():
    cid = str(uuid.uuid4())
    r = TestClient(make_app()).get("/ok", headers={"X-Correlation-Id": cid})
    assert r.status_code == 200
    assert r.headers["X-Correlation-Id"] == cid
    body = r.json()
    assert body["data"] == {"x": 1}
    assert body["meta"]["correlation_id"] == cid and body["meta"]["source"] == "synthetic-poc"


def test_invalid_correlation_id_is_replaced():
    r = TestClient(make_app()).get("/ok", headers={"X-Correlation-Id": "not-a-uuid"})
    uuid.UUID(r.headers["X-Correlation-Id"])


def test_problem_details():
    r = TestClient(make_app()).get("/problem")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/problems/conflict" and r.json()["correlation_id"]


def test_unexpected_error_hides_detail():
    r = TestClient(make_app(), raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text


def test_not_found_is_problem():
    r = TestClient(make_app()).get("/nope")
    assert r.status_code == 404 and r.json()["type"] == "/problems/http-404"


def test_health():
    assert TestClient(make_app(True)).get("/health/ready").status_code == 200
    assert TestClient(make_app(False)).get("/health/ready").status_code == 503
    assert TestClient(make_app(False)).get("/health/live").status_code == 200
