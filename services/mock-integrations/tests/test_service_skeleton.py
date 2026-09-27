"""Slice-1 checks every service must pass (generated from the template)."""
import re

from app.api.catalogue_routes import OPERATIONS


def test_live(client):
    assert client.get("/health/live").status_code == 200


def test_ready_is_503_without_database(client):
    assert client.get("/health/ready").status_code == 503


def _concrete(path: str) -> str:
    return "/api/v1" + re.sub(r"{[^}]+}", "x1", path)


def test_every_phase1_operation_is_routed_and_protected(client, internal_token):
    for op in OPERATIONS:
        method, path = op.split(" ", 1)
        url = _concrete(path)
        anonymous = client.request(method, url)
        assert anonymous.status_code == 401, (op, anonymous.status_code)
        wrong_audience = client.request(method, url, headers={"Authorization": f"Bearer {internal_token(audience='other-service')}"})
        assert wrong_audience.status_code == 401, op
        ok = client.request(method, url, headers={"Authorization": f"Bearer {internal_token()}"})
        # Routed and authenticated: never a router-level miss (/problems/http-404 or 405) and never 401.
        # Real routes may still answer 400/403/404/409/422, or 500 here because tests run without a database.
        assert ok.json().get("type") not in ("/problems/http-404", "/problems/http-405"), op
        assert ok.json().get("type") != "/problems/unauthenticated", (op, ok.json())  # the token was accepted
