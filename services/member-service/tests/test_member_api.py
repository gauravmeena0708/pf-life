"""Member-service API tests on SQLite with signed internal tokens."""
import asyncio
import importlib
import json
import os
import time
import uuid
from pathlib import Path

import jwt
import pytest
from sqlalchemy import func, select

from tests.conftest import JWKS, KEY, KID

SEED_FILE = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"
SEED = json.loads(SEED_FILE.read_text(encoding="utf-8"))
MEMBER_A, MEMBER_B = (member["subject"] for member in SEED["members"][:2])
ESTABLISHMENT = SEED["establishment"]["establishment_id"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/member.db")
    monkeypatch.setenv("SEED_FILE", str(SEED_FILE))

    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None

    from app.infra.models import Base
    from app.infra.tables import metadata

    async def setup():
        async with db.engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(metadata.create_all)
        from app import seed
        seed.SEED_FILE = os.environ["SEED_FILE"]
        await seed.main()
        await seed.main()

    asyncio.run(setup())

    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="member-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))
    yield TestClient(application, raise_server_exceptions=True)
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def token(subject: str, stakeholder: str = "member", grants: tuple[str, ...] = (),
          establishment: str | None = None) -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "member-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
              "grants": list(grants)}
    if establishment:
        claims["establishment_id"] = establishment
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_member_profiles_are_subject_scoped(api):
    a = api.get("/api/v1/members/me", headers=token(MEMBER_A))
    b = api.get("/api/v1/members/me", headers=token(MEMBER_B))
    assert a.status_code == b.status_code == 200
    assert a.json()["data"]["uan"] == SEED["members"][0]["uan"]
    assert b.json()["data"]["uan"] == SEED["members"][1]["uan"]
    assert a.json()["data"]["kyc"]["pan"] == "VERIFIED"
    assert b.json()["data"]["kyc"]["pan"] == "NOT_SEEDED"
    forged_query = api.get("/api/v1/members/me?member_id=" + SEED["members"][0]["member_id"],
                           headers=token(MEMBER_B))
    assert forged_query.json()["data"]["member_id"] == b.json()["data"]["member_id"]
    assert api.get("/api/v1/members/me/" + SEED["members"][0]["member_id"], headers=token(MEMBER_B)).status_code == 404


def test_member_access_and_missing_row(api):
    for stakeholder in ("fo.da_accounts", "employer.operator"):
        response = api.get("/api/v1/members/me", headers=token(MEMBER_A, stakeholder))
        assert response.status_code == 403
    missing = api.get("/api/v1/members/me", headers=token("missing-subject"))
    assert missing.status_code == 404
    assert missing.json()["type"] == "/problems/not-found"


def test_history_and_identity_assurance(api):
    history = api.get("/api/v1/members/me/employment-history", headers=token(MEMBER_A))
    assert history.status_code == 200
    assert history.json()["data"][0]["account_link_id"] == SEED["members"][0]["account_link_id"]
    assert history.json()["data"][0]["status"] == "ACTIVE"
    full = api.get("/api/v1/members/me/identity-assurance", headers=token(MEMBER_A))
    partial = api.get("/api/v1/members/me/identity-assurance", headers=token(MEMBER_B))
    assert full.json()["data"]["level"] == "FULL"
    assert partial.json()["data"]["level"] == "PARTIAL"
    assert "pan" in partial.json()["data"]["next_step"]


def test_notification_handler_is_idempotent_and_scoped(api):
    from app.domain.notifications import handle_notification_requested
    from app.infra.db import sessions
    from app.infra.tables import notifications

    event = {"event_id": str(uuid.uuid4()), "event_type": "NotificationRequested.v1",
             "payload": {"recipient_subject": MEMBER_A, "template": "CLAIM_SETTLED", "reference_id": "CLM-0001",
                         "params": {"amount_paise": 60000000}}}   # the bank ending is looked up here

    async def deliver():
        async with sessions()() as session, session.begin():
            await handle_notification_requested(session, event)
            await handle_notification_requested(session, event)
        async with sessions()() as session:
            return (await session.execute(select(func.count()).select_from(notifications))).scalar_one()

    assert asyncio.run(deliver()) == 1
    own = api.get("/api/v1/members/me/notifications", headers=token(MEMBER_A))
    other = api.get("/api/v1/members/me/notifications", headers=token(MEMBER_B))
    assert own.status_code == other.status_code == 200
    assert "CLM-0001" in own.json()["data"][0]["body"]
    assert own.json()["data"][0]["body"] == ("Your claim CLM-0001 for ₹6,00,000 was paid into your bank account "
                                             "ending 0001.")
    assert other.json()["data"] == []


def test_employer_list_requires_grant_and_establishment(api):
    subject = SEED["keycloak_subjects"]["emp-preparer"]
    path = "/api/v1/employers/me/members"
    no_grant = api.get(path, headers=token(subject, "employer.operator", establishment=ESTABLISHMENT))
    assert no_grant.status_code == 403
    assert no_grant.json()["type"] == "/problems/missing-grant"
    own = api.get(path, headers=token(subject, "employer.operator", ("ecr.prepare",), ESTABLISHMENT))
    assert own.status_code == 200
    assert len(own.json()["data"]) == len(SEED["members"])
    other = api.get(path, headers=token(subject, "employer.operator", ("members.manage",), "EST-OTHER"))
    assert other.status_code == 200
    assert other.json()["data"] == []
