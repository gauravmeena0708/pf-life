"""EPS para 16: family, nominee and dependent-parent precedence."""
import asyncio
from datetime import date

import pytest
from sqlalchemy import insert

from app.infra.db import sessions
from app.infra.tables import family_members, member_service
from tests.test_pensions import ctx  # noqa: F401
from tests.test_settlement import step
from tests.test_settlement import DA_P

UAN = "100000000997"
URL = "/api/v1/claimants/family-pension-applications"


def setup_family(*, father_dead=False, nominee=False, children=()):
    async def run():
        async with sessions()() as s, s.begin():
            await s.execute(insert(member_service).values(subject="p219-deceased", name="DECEASED DEMO",
                date_of_birth=date(1970, 1, 1), date_of_joining=date(2000, 1, 1), date_of_exit=date(2026, 1, 1),
                eps_wages_paise=1500000, office_id="RO-DEMO-01", uan=UAN, account_link_id="P219-AL"))
            for relation, born, disabled in [("FATHER", date(1940, 1, 1), False), ("MOTHER", date(1942, 1, 1), False),
                                             *(("CHILD", born, disabled) for born, disabled in children)]:
                subject = f"p219-{relation.lower()}-{born.year}"
                await s.execute(insert(family_members).values(id=subject, uan=UAN, name=subject.upper(), relation=relation,
                    date_of_birth=born, disabled=disabled, subject=subject, dependent=True,
                    date_of_death=date(2026, 7, 1) if relation == "FATHER" and father_dead else None))
            if nominee:
                await s.execute(insert(family_members).values(id="p219-nominee", uan=UAN, name="NOMINEE DEMO",
                    relation="NOMINEE", date_of_birth=date(1980, 1, 1), subject="p219-nominee", nomination_valid=True))
    asyncio.run(run())


@pytest.mark.parametrize("father_dead,nominee,expected", [
    (False, False, "FATHER"), (True, False, "MOTHER"), (False, True, "NOMINEE")])
def test_parent_succession_and_nominee_precedence(ctx, father_dead, nominee, expected):
    client, _, _ = ctx
    setup_family(father_dead=father_dead, nominee=nominee)
    subject = "p219-nominee" if expected == "NOMINEE" else f"p219-{expected.lower()}-{1940 if expected == 'FATHER' else 1942}"
    r = step(client, "POST", URL, subject, "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN)
    assert r.status_code == 201, r.json()
    assert r.json()["data"]["kind"] == expected
    if expected == "MOTHER":
        assert r.json()["data"]["pension_from"] == "2026-07-02"
    rival = "p219-mother-1942" if expected == "FATHER" else "p219-father-1940"
    assert step(client, "POST", URL, rival, "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN).status_code == 422


def test_disabled_child_is_paid_in_addition_to_two_ordinary_children(ctx):
    client, _, _ = ctx
    setup_family(children=((date(2002, 1, 1), False), (date(2003, 1, 1), False),
                           (date(2004, 1, 1), False), (date(2005, 1, 1), True)))
    for year in (2002, 2003, 2005):
        r = step(client, "POST", URL, f"p219-child-{year}", "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN)
        assert r.status_code == 201, r.json()
        if year == 2005:
            assert r.json()["data"]["family"]["disabled_child"] is True
    r = step(client, "POST", URL, "p219-child-2004", "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN)
    assert r.status_code == 422, r.json()


def test_disabled_child_over_25_can_claim_for_life(ctx):
    client, _, _ = ctx
    setup_family(children=((date(1990, 1, 1), True),))
    r = step(client, "POST", URL, "p219-child-1990", "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN)
    assert r.status_code == 201, r.json()
    assert r.json()["data"]["family"]["disabled_child"] is True


def test_office_records_documented_dependent_parent_for_claim(ctx):
    client, _, _ = ctx
    async def member_only():
        async with sessions()() as s, s.begin():
            await s.execute(insert(member_service).values(subject="p219-deceased", name="DECEASED DEMO",
                date_of_birth=date(1970, 1, 1), date_of_joining=date(2000, 1, 1), date_of_exit=date(2026, 1, 1),
                eps_wages_paise=1500000, office_id="RO-DEMO-01", uan=UAN, account_link_id="P219-AL"))
    asyncio.run(member_only())
    body = {"deceased_uan": UAN, "subject": "p219-father", "name": "FATHER DEMO", "relation": "FATHER",
            "date_of_birth": "1940-01-01", "dependent": True, "evidence_ref": "FORM-10D-PARENT-1"}
    path = "/api/v1/office/pensions/family-beneficiaries"
    r = step(client, "POST", path, DA_P, "fo.da_pension", body, "record-family-beneficiary", UAN)
    assert r.status_code == 201, r.json()
    claim = step(client, "POST", URL, "p219-father", "claimant", {"deceased_uan": UAN}, "file-family-pension", UAN)
    assert claim.status_code == 201, claim.json()
