"""Public circular discovery and HO publication/versioning."""
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_ai import ctx, hdr

SEED = json.loads((Path(__file__).resolve().parents[3] / "scripts/seed/synthetic.json").read_text())
S = SEED["keycloak_subjects"]
PUBLIC = "/api/v1/public/circulars"
PUBLISH = "/api/v1/ho/circulars"


def circular(**changes):
    return {"number": "TEST/CLAIMS/01", "title": "Synthetic advance claim guidance",
            "category": "CLAIMS", "issued_on": date.today().isoformat(),
            "summary": "Illustrative guidance for filing advance claims.",
            "body": "SYNTHETIC. Members should check their account details before filing an advance claim.", **changes}


def events():
    from app.infra.db import engine

    async def read():
        async with engine().connect() as connection:
            return (await connection.execute(text(
                "SELECT payload FROM outbox WHERE event_type='CircularPublished.v1' ORDER BY id"))).all()
    return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for (p,) in asyncio.run(read())]


def test_seeded_circulars_are_public_and_filterable(ctx):
    client, *_ = ctx
    headers = hdr("public", "anonymous")
    response = client.get(PUBLIC, headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]["circulars"]
    assert len(rows) == 3 and all(row["state"] == "CURRENT" for row in rows)
    for params, expected in [({"category": "PENSION"}, "PENSION"),
                             ({"q": "aUtO-SeTtLeMeNt"}, "CLAIMS"),
                             ({"category": "COMPLIANCE", "q": "15th"}, "COMPLIANCE")]:
        response = client.get(PUBLIC, params=params, headers=headers)
        assert response.status_code == 200, response.text
        [row] = response.json()["data"]["circulars"]
        assert row["category"] == expected
    assert client.get(PUBLIC, params={"category": "PENSION", "q": "remittances"},
                      headers=headers).json()["data"]["circulars"] == []


def test_publish_changed_body_supersedes_previous_version_and_emits_events(ctx):
    client, *_ = ctx
    headers = hdr("ho.publicity", S["ho-publicity"])
    body = circular()
    response = client.post(PUBLISH, json=body, headers=headers)
    assert response.status_code == 201, response.text
    first = response.json()["data"]
    assert first["version"] == 1 and first["state"] == "CURRENT"
    [event] = events()
    assert event == {k: first[k] for k in ("circular_id", "number", "version", "category", "issued_on", "sha256")}
    response = client.post(PUBLISH, json={**body, "body": body["body"] + " Revised instructions apply."}, headers=headers)
    assert response.status_code == 201, response.text
    second = response.json()["data"]
    assert second["version"] == 2 and second["sha256"] != first["sha256"]
    response = client.get(PUBLIC, params={"number": body["number"]}, headers=hdr("public", "anonymous"))
    assert response.status_code == 200, response.text
    assert [(r["version"], r["state"]) for r in response.json()["data"]["circulars"]] == [(2, "CURRENT"), (1, "SUPERSEDED")]
    current = client.get(PUBLIC, headers=hdr("public", "anonymous")).json()["data"]["circulars"]
    assert [r["version"] for r in current if r["number"] == body["number"]] == [2]
    assert [event["version"] for event in events()] == [1, 2]


def test_identical_republication_is_rejected_without_an_event(ctx):
    client, *_ = ctx
    headers = hdr("ho.publicity", S["ho-publicity"])
    assert client.post(PUBLISH, json=circular(), headers=headers).status_code == 201
    assert client.post(PUBLISH, json=circular(), headers=headers).status_code == 409
    assert len(events()) == 1


@pytest.mark.parametrize("stakeholder, subject, body, status", [
    ("ho.publicity", S["ho-publicity"], circular(issued_on=(date.today() + timedelta(days=1)).isoformat()), 422),
    ("member", S["member-a"], circular(), 403),
])
def test_invalid_date_and_member_cannot_publish(ctx, stakeholder, subject, body, status):
    client, *_ = ctx
    response = client.post(PUBLISH, json=body, headers=hdr(stakeholder, subject))
    assert response.status_code == status, response.text
    assert events() == []
