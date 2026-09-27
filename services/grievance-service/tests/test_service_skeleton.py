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
        # A router-level miss (/problems/http-404 or 405) means the operation is not routed at all.
        assert ok.json().get("type") not in ("/problems/http-404", "/problems/http-405"), op
        assert ok.status_code in (200, 201, 400, 404, 409, 422, 501), (op, ok.status_code)
