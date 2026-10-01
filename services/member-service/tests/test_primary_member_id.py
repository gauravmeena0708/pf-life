"""Phase 2, slice 7d: the primary member ID — the latest member ID that has received contributions, over the
member's Aadhaar-verified set — shown to the member and the office, moved by a first contribution and a transfer."""
import asyncio

from sqlalchemy import select

from tests.test_exits import MEMBER_D, deliver, hdr
from tests.test_member_api import SEED, api  # noqa: F401  (api is a fixture)
from tests.test_member_processes import outbox
from tests.test_onboarding import hdr as office_hdr

MEMBER_B = SEED["keycloak_subjects"]["member-b"]


def test_establishment_office_transfer_moves_employments(api):
    from app.infra.db import sessions
    from app.infra.tables import employments

    async def offices():
        async with sessions()() as session:
            return (await session.execute(select(employments.c.office_id).where(
                employments.c.establishment_id == "EST-DEMO-0001"))).scalars().all()

    assert set(asyncio.run(offices())) == {"RO-DEMO-01"}
    payload = {"establishment_id": "EST-DEMO-0001", "from_office_id": "RO-DEMO-01",
               "to_office_id": "RO-DEMO-02", "effective_from": "2026-10-01"}
    deliver("EstablishmentOfficeTransferred.v1", payload)
    deliver("EstablishmentOfficeTransferred.v1", payload)
    assert set(asyncio.run(offices())) == {"RO-DEMO-02"}


def test_primary_and_secondary_member_ids_in_the_service_history(api):
    h = api.get("/api/v1/members/me/service-history", headers=hdr(MEMBER_D)).json()["data"]
    assert h["primary_member_id"] == "AL-0009"                            # joined 2026-01-15 and paid into; AL-0008 is older
    assert {m["account_link_id"]: m["primary"] for m in h["member_ids"]} == {"AL-0008": False, "AL-0009": True}


def test_an_older_uan_with_the_same_verified_aadhaar_is_in_the_set(api):
    h = api.get("/api/v1/members/me/service-history", headers=hdr(MEMBER_B)).json()["data"]
    assert h["aadhaar_set_uans"] == ["100000000903"] and h["primary_member_id"] == "AL-0002"
    da = office_hdr(SEED["keycloak_subjects"]["do-caseworker"], "fo.da_accounts", establishment=None)
    m360 = api.get("/api/v1/office/members/100000000903?purpose=Checking%20the%20Aadhaar%20set", headers=da).json()["data"]
    assert m360["aadhaar_set_uans"] == ["100000000002", "100000000903"] and m360["primary_member_id"] == "AL-0002"
    assert m360["member_ids"][0]["primary"] is False                       # AL-0903 is secondary: the primary is on the other UAN


def test_a_new_member_id_becomes_primary_with_its_first_contribution(api):
    from tests.test_onboarding import JOINEE, operator
    body = {**JOINEE, "name": "FARAH DEMO", "date_of_birth": "1992-02-14", "existing_uan": "100000000006", "date_of_joining": "2026-09-01"}
    member_c = SEED["keycloak_subjects"]["member-c"]
    r = api.post("/api/v1/employers/me/members", json=body, headers=operator())
    assert r.status_code == 201, r.json()
    new = r.json()["data"]["account_link_id"]
    assert api.get("/api/v1/members/me/service-history", headers=hdr(member_c)).json()["data"]["primary_member_id"] == "AL-0006"   # not paid into yet
    deliver("ContributionPosted.v1", {"journal_id": "J", "payment_id": "P", "filing_id": "F", "establishment_id": "EST-DEMO-0001", "wage_month": "2026-09",
                                      "postings": [{"account_code": "AC01_EPF", "side": "credit", "amount_paise": 180000, "account_link_id": new, "share": "employee"}]})
    assert api.get("/api/v1/members/me/service-history", headers=hdr(member_c)).json()["data"]["primary_member_id"] == new
    moved = outbox("PrimaryMemberIdChanged.v1")
    assert moved[-1]["primary_account_link_id"] == new and moved[-1]["previous_account_link_id"] == "AL-0006"
