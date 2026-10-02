"""Synthetic exempted establishment and trust profile."""
import asyncio

from tests.test_employer_api import SEED, api, owner, token  # noqa: F401


TRUST = SEED["exempted_establishment"]
EST = TRUST["establishment_id"]


def test_employer_exemption_uses_seeded_record(api):
    none = api.get("/api/v1/employers/me/exemption", headers=owner())
    assert none.status_code == 200
    assert none.json()["data"]["exempted"] is False

    from app.infra.db import engine
    from app.infra.tables import grants

    async def grant_owner():
        async with engine().begin() as connection:
            await connection.execute(grants.insert().values(
                grant_id="GR-EXEMPT-TEST", establishment_id=EST, subject="exempt-owner-test",
                username="exempt-owner-test", kind="OWNER", grants=["establishment.manage"],
                status="ACTIVE", granted_by="test"))

    asyncio.run(grant_owner())
    exempt_owner = token("exempt-owner-test", "employer.owner", ["establishment.manage"], establishment=EST)
    response = api.get("/api/v1/employers/me/exemption", headers=exempt_owner)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["establishment_id"] == EST and data["exempted"] is True
    assert data["kind"] == "S17_1A" and data["trust_id"] == TRUST["trust_id"]
    assert data["pf_exempt"] is True and data["pension_exempt"] is False and data["edli_exempt"] is False
    assert data["notification_date"] == TRUST["notification_date"]


def test_trust_profile_requires_mapped_subject(api):
    url = "/api/v1/exempted/me/profile"
    assert api.get(url, headers=owner()).status_code == 403
    assert api.get(url, headers=token("unmapped", "exempted.trust", establishment=None)).status_code == 403
    response = api.get(url, headers=token(TRUST["trust_users"][0]["subject"], "exempted.trust", establishment=None))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["establishment"] == {"establishment_id": EST, "legal_name": "Demo Steel Works"}
    assert data["trust_name"] == TRUST["trust_name"]
    assert data["effective_from"] == TRUST["effective_from"] and data["status"] == "ACTIVE"
    assert "whole establishment" in data["kind_description"]
    assert [c["number"] for c in data["conditions"]] == [3, 4, 5, 7, 9, 12, 14, 15]
    assert "EPS" in data["note"] and "EDLI" in data["note"]


def test_exemption_seed_is_idempotent(api):
    from app import seed
    from app.infra.db import engine
    from sqlalchemy import text

    asyncio.run(seed.main())

    async def count():
        async with engine().connect() as connection:
            return (await connection.execute(text("SELECT COUNT(*) FROM establishment_exemptions"))).scalar_one()

    assert int(asyncio.run(count())) == 3
