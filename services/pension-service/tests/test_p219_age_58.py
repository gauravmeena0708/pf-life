"""EPS membership and pensionable service cease at 58; pension may be deferred to 60."""
import asyncio
from datetime import date

from sqlalchemy import update

from app.infra.db import sessions
from app.infra.tables import eps_accounts, member_service
from app.api.routes import eps_service
from app.domain.pension import pension_at_start
from epfo_persistence.policy import baseline, pension_on
from tests.test_pensioner_services import at
from tests.test_pensions import SUBJECTS, ctx, hdr  # noqa: F401
from tests.test_settlement import step


def change_member(*, exited):
    async def run():
        async with sessions()() as s, s.begin():
            await s.execute(update(member_service).where(member_service.c.subject == SUBJECTS["member-e"]).values(
                date_of_birth=date(1967, 1, 1), date_of_joining=date(2000, 1, 1), date_of_exit=exited))
            await s.execute(update(eps_accounts).where(eps_accounts.c.uan == "100000000004").values(
                date_of_joining=date(2000, 1, 1), date_of_exit=exited))
    asyncio.run(run())


def test_service_and_deferred_formula_without_database():
    spell = {"account_link_id": "P219-1", "establishment_id": "EST", "date_of_joining": date(2000, 1, 1),
             "date_of_exit": None, "breaks_months": 0}
    assert eps_service([spell], date(2026, 10, 1), date(2025, 1, 1))[0] == 300
    base = pension_on(1500000, 300, 58, baseline())["monthly_paise"]
    result = pension_at_start(1500000, 300, date(1967, 1, 1), date(2027, 1, 1), baseline())
    assert result["monthly_paise"] == base * 10816 // 10000


def test_service_estimate_stops_at_58_while_still_employed(ctx, monkeypatch):
    client, _, _ = ctx
    at(monkeypatch, date(2026, 10, 1))
    change_member(exited=None)
    r = client.get("/api/v1/members/me/pension-eligibility-preview", headers=hdr(SUBJECTS["member-e"], "member"))
    assert r.status_code == 200, r.json()
    assert r.json()["data"]["service_months_so_far"] == 300


def test_deferred_pension_uses_service_to_58_and_compounded_increment(ctx, monkeypatch):
    client, _, _ = ctx
    at(monkeypatch, date(2026, 10, 1))
    change_member(exited=date(2026, 6, 30))
    r = step(client, "POST", "/api/v1/members/me/pension-applications", SUBJECTS["member-e"], "member",
             {"pension_from": "2027-01-01"})
    assert r.status_code == 201, r.json()
    claim = r.json()["data"]
    base = pension_on(1500000, 300, 58, baseline())["monthly_paise"]
    assert claim["service_months"] == 300
    assert claim["estimate"]["monthly_paise"] == base * 10816 // 10000
