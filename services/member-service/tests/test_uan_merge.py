"""Office UAN merger keeps the member's service and an alias for the old login."""
import asyncio
import json

from sqlalchemy import insert, select, update

from tests.test_member_api import SEED, api, token  # noqa: F401

ACTIVE = SEED["members"][0]
DUPLICATE_UAN = "199999999991"
URL = "/api/v1/office/uan-merges"


def prepare_duplicate(*, name=None, aadhaar=None, claim=False):
    from app.infra.db import sessions
    from app.infra.tables import employments, member_applications, members

    async def run():
        async with sessions()() as session:
            async with session.begin():
                source = (await session.execute(select(members).where(members.c.uan == ACTIVE["uan"]))).mappings().one()
                values = dict(source)
                values.update(member_id="MERGE-DEMO", uan=DUPLICATE_UAN, subject="duplicate-login",
                              name=name or "  " + source["name"].lower() + "  ",
                              aadhaar_ref=aadhaar if aadhaar is not None else source["aadhaar_ref"])
                values.pop("created_at")
                await session.execute(insert(members).values(**values))
                job = (await session.execute(select(employments).where(employments.c.member_id == source["member_id"]))).mappings().first()
                if job:
                    values = dict(job)
                    values.update(account_link_id="AL-MERGE", member_id="MERGE-DEMO")
                    await session.execute(insert(employments).values(**values))
                if claim:
                    await session.execute(insert(member_applications).values(application_id="CLAIM-MERGE", uan=DUPLICATE_UAN,
                        process="claim_settlement", title="Claim", state="IN_REVIEW", terminal=False))
    asyncio.run(run())


def post(api, role="fo.ao"):
    return api.post(URL, headers=token("officer", role), json={"active_uan": ACTIVE["uan"],
        "duplicate_uan": DUPLICATE_UAN, "note": "Same person verified in office"})


def test_merge_links_service_alias_and_emits_once(api):
    prepare_duplicate()
    response = post(api)
    assert response.status_code == 201, response.json()
    assert response.json()["data"]["account_link_ids"] == ["AL-MERGE"]
    assert api.get("/api/v1/members/me", headers=token("duplicate-login")).json()["data"]["uan"] == ACTIVE["uan"]
    history = api.get("/api/v1/members/me/service-history", headers=token(ACTIVE["subject"])).json()["data"]
    assert "AL-MERGE" in [x["account_link_id"] for x in history["member_ids"]]
    assert post(api).status_code == 409
    assert len(api.get(URL, headers=token("officer", "fo.apfc")).json()["data"]) == 1

    from app.infra.db import sessions
    from app.infra.models import Outbox
    from app.infra.tables import members, employments
    async def rows():
        async with sessions()() as session:
            return ((await session.execute(select(members).where(members.c.uan == DUPLICATE_UAN))).mappings().one(),
                    (await session.execute(select(employments.c.member_id).where(employments.c.account_link_id == "AL-MERGE"))).scalar_one(),
                    (await session.execute(select(Outbox).where(Outbox.event_type == "UanMerged.v1"))).scalars().all())
    merged, owner, events = asyncio.run(rows())
    assert merged["account_state"] == "MERGED" and merged["merged_into"] == ACTIVE["uan"]
    assert merged["merged_at"] and merged["merged_by"] == "officer" and owner == ACTIVE["member_id"]
    assert len(events) == 1
    payload = events[0].payload.get("envelope", {}).get("payload", events[0].payload)
    assert payload == {"active_uan": ACTIVE["uan"], "duplicate_uan": DUPLICATE_UAN,
                       "account_link_ids": ["AL-MERGE"], "merged_at": payload["merged_at"]}


def test_merge_rejects_identity_mismatch_claim_and_wrong_role(api):
    prepare_duplicate(name="OTHER PERSON")
    assert post(api).status_code == 422
    assert post(api, "fo.da_accounts").status_code == 403
    from app.infra.db import sessions
    from app.infra.tables import members, member_applications
    async def fix():
        async with sessions()() as session:
            async with session.begin():
                await session.execute(update(members).where(members.c.uan == DUPLICATE_UAN).values(name=ACTIVE["name"]))
                await session.execute(insert(member_applications).values(application_id="CLAIM-MERGE", uan=DUPLICATE_UAN,
                    process="claim_settlement", title="Claim", state="IN_REVIEW", terminal=False))
    asyncio.run(fix())
    assert post(api).status_code == 409


def test_merge_rejects_aadhaar_mismatch_same_uan_and_allows_apfc(api):
    # Same UAN refused
    r = api.post(URL, headers=token("officer", "fo.ao"), json={
        "active_uan": ACTIVE["uan"], "duplicate_uan": ACTIVE["uan"], "note": "Same UAN test"})
    assert r.status_code == 422

    # Nonexistent UAN refused
    r = api.post(URL, headers=token("officer", "fo.ao"), json={
        "active_uan": "999999999999", "duplicate_uan": ACTIVE["uan"], "note": "Missing active UAN"})
    assert r.status_code == 422

    # Aadhaar mismatch refused
    prepare_duplicate(aadhaar="DIFFERENT-AADHAAR-HASH")
    r = post(api, "fo.apfc")
    assert r.status_code == 422

    # With matching Aadhaar, fo.apfc can successfully merge
    from app.infra.db import sessions
    from app.infra.tables import members
    async def match_aadhaar():
        async with sessions()() as session:
            async with session.begin():
                active_ref = (await session.execute(select(members.c.aadhaar_ref).where(members.c.uan == ACTIVE["uan"]))).scalar_one_or_none()
                await session.execute(update(members).where(members.c.uan == DUPLICATE_UAN).values(aadhaar_ref=active_ref))
    asyncio.run(match_aadhaar())
    r = post(api, "fo.apfc")
    assert r.status_code == 201
