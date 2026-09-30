"""Phase 2, slice 7c: the annual statement (opening, the year's movements by kind, closing) and the taxable
interest split."""
from tests.test_ecr_api import SEED, ctx, hdr  # noqa: F401
from tests.test_returns import regular_posted

MEMBER_A = SEED["keycloak_subjects"]["member-a"]


def member():
    return hdr(MEMBER_A, "member", [], establishment=None)


def test_annual_statement_for_the_year_of_posting(ctx):
    client, _ = ctx
    regular_posted(client)                                                  # posted in September 2026 → 2026-27
    [a] = client.get("/api/v1/members/me/annual-statements/2026-27", headers=member()).json()["data"]["accounts"]
    assert a["account_link_id"] == "AL-0001" and a["movements"]["contributions"]["employee"] == 180000
    assert a["opening"]["employee"] + a["opening"]["employer"] == 600000000           # the balance brought forward
    assert a["closing_total_paise"] == 600000000 + 180000 + a["movements"]["contributions"]["employer"]
    [before] = client.get("/api/v1/members/me/annual-statements/2025-26", headers=member()).json()["data"]["accounts"]
    assert before["movements"]["contributions"]["employee"] == 0
    assert client.get("/api/v1/members/me/annual-statements/2025-27", headers=member()).status_code == 422


def test_taxable_interest_split():
    from app.api.statement_routes import taxable_split
    within = taxable_split(20000000, 1600000, 825, 25000000)
    assert within["taxable_interest_paise"] == 0 and within["non_taxable_interest_paise"] == 1600000
    above = taxable_split(35000000, 2500000, 825, 25000000)
    assert above["excess_paise"] == 10000000 and above["taxable_interest_paise"] == 825000 and above["non_taxable_interest_paise"] == 1675000


def test_taxable_interest_endpoint(ctx):
    client, _ = ctx
    r = client.get("/api/v1/members/me/tax/taxable-interest?financialYear=2026-27", headers=member()).json()["data"]
    assert r["threshold_paise"] == 25000000 and r["taxable_interest_paise"] == 0 and r["illustrative"] is True
