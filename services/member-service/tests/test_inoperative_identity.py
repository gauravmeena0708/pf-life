"""P2.12a synthetic face, OTP, and co-worker verification routes."""
import asyncio
import hashlib
import json

from sqlalchemy import select, update

from tests.test_member_api import SEED, api  # noqa: F401
from tests.test_member_processes import outbox
from tests.test_onboarding import hdr

S = SEED["keycloak_subjects"]
ALLOT_URL = "/api/v1/members/uan-allotments"
ALLOT = {"aadhaar": "345678912345", "name": "New Demo", "date_of_birth": "1995-02-03", "gender": "FEMALE",
         "mobile": "9876543210", "face_auth_token": "MOCK-FACE-MATCH"}


def test_csc_allotment_has_no_raw_aadhaar_and_no_employment(api):
    from app.infra.db import sessions
    from app.infra.tables import employments, members

    csc = hdr("csc-demo", "csc_operator", establishment=None)
    bad = api.post(ALLOT_URL, json={**ALLOT, "face_auth_token": "wrong"}, headers=csc)
    assert bad.status_code == 422 and bad.json()["type"] == "/problems/face-auth-failed"
    created = api.post(ALLOT_URL, json=ALLOT, headers=csc)
    assert created.status_code == 201, created.json()
    data = created.json()["data"]
    assert data["name"] == "NEW DEMO" and "employer links" in data["next_step"]
    assert ALLOT["aadhaar"] not in json.dumps(created.json())

    async def stored():
        async with sessions()() as session:
            member = (await session.execute(select(members).where(members.c.uan == data["uan"]))).mappings().one()
            jobs = (await session.execute(select(employments.c.account_link_id).where(
                employments.c.member_id == member["member_id"]))).all()
            return dict(member), jobs

    member, jobs = asyncio.run(stored())
    assert member["aadhaar_ref"] == hashlib.sha256(f"demo-aadhaar:{ALLOT['aadhaar']}".encode()).hexdigest()
    assert member["kyc"]["aadhaar"] == "VERIFIED" and not jobs
    assert ALLOT["aadhaar"] not in json.dumps(member, default=str)
    assert outbox("UanAllotted.v1") == [{"uan": data["uan"], "channel": "CSC"}]
    duplicate = api.post(ALLOT_URL, json=ALLOT, headers=csc)
    assert duplicate.status_code == 409 and duplicate.json()["type"] == "/problems/uan-exists"
    assert data["uan"] not in json.dumps(duplicate.json()) and data["uan"][-4:] in json.dumps(duplicate.json())
    own = api.post(ALLOT_URL, json=ALLOT, headers=hdr(S["member-a"], "member", establishment=None))
    assert own.status_code == 409 and own.json()["type"] == "/problems/uan-exists"
    assert SEED["members"][0]["uan"] not in json.dumps(own.json())


def test_member_activates_only_own_uan_once(api):
    uan = SEED["members"][0]["uan"]
    url = "/api/v1/members/uan-activations"
    member = hdr(S["member-a"], "member", establishment=None)
    other = api.post(url, json={"uan": SEED["members"][1]["uan"], "otp": "123456"}, headers=member)
    assert other.status_code == 403 and other.json()["type"] == "/problems/not-your-uan"
    wrong = api.post(url, json={"uan": uan, "otp": "000000"}, headers=member)
    assert wrong.status_code == 422 and wrong.json()["type"] == "/problems/otp-failed"
    activated = api.post(url, json={"uan": uan, "otp": "123456"}, headers=member)
    assert activated.status_code == 200 and activated.json()["data"]["activated_at"]
    assert "Demo-only" in activated.json()["data"]["demo"]
    again = api.post(url, json={"uan": uan, "otp": "123456"}, headers=member)
    assert again.status_code == 409 and again.json()["type"] == "/problems/already-active"


def test_inoperative_holder_requires_overlapping_co_workers_and_office(api):
    from app.infra.db import sessions
    from app.infra.tables import employments

    target = SEED["members"][3]
    account = target["account_link_id"]
    url = f"/api/v1/office/accounts/{account}/crowdsource-verifications"
    first, second = SEED["members"][0]["uan"], SEED["members"][1]["uan"]
    da = hdr(S["do-caseworker"], "fo.da_accounts", establishment=None)

    async def age_account():
        async with sessions()() as session, session.begin():
            await session.execute(update(employments).where(employments.c.account_link_id == account)
                                  .values(last_contribution_month="2020-03"))

    premature = api.post(url, json={"co_worker_uans": [first, second], "note": "Known to colleagues"}, headers=da)
    assert premature.status_code == 422 and premature.json()["type"] == "/problems/not-inoperative"
    asyncio.run(age_account())
    body = {"co_worker_uans": [first, second], "note": "Known to colleagues"}
    missing = api.post(url, json={**body, "co_worker_uans": [first, "999999999999"]}, headers=da)
    assert missing.status_code == 422 and "999999999999" in missing.json()["detail"]
    duplicate = api.post(url, json={**body, "co_worker_uans": [first, first]}, headers=da)
    assert duplicate.status_code == 422 and "2 distinct" in duplicate.json()["detail"]
    async def move_colleague(joined):
        async with sessions()() as session, session.begin():
            await session.execute(update(employments).where(
                employments.c.account_link_id == SEED["members"][1]["account_link_id"])
                .values(date_of_joining=joined))

    from datetime import date
    asyncio.run(move_colleague(date(2026, 9, 1)))
    no_overlap = api.post(url, json=body, headers=da)
    assert no_overlap.status_code == 422 and second in no_overlap.json()["detail"]
    asyncio.run(move_colleague(date.fromisoformat(SEED["members"][1]["date_of_joining"])))
    self_check = api.post(url, json={**body, "co_worker_uans": [first, target["uan"]]}, headers=da)
    assert self_check.status_code == 422 and target["uan"] in self_check.json()["detail"]
    forbidden = api.post(url, json=body, headers=hdr(S["member-a"], "member", establishment=None))
    assert forbidden.status_code == 403
    wrong_office = api.post(url, json=body, headers=hdr(S["ro-oic"], "fo.da_accounts", establishment=None))
    assert wrong_office.status_code == 404
    verified = api.post(url, json=body, headers=da)
    assert verified.status_code == 201, verified.json()
    assert verified.json()["data"]["co_workers"] == 2
    [event] = outbox("InoperativeAccountVerified.v1")
    assert event == {"account_link_id": account, "uan": target["uan"], "co_workers": 2,
                     "verified_by_office": "RO-DEMO-01"}
    again = api.post(url, json=body, headers=da)
    assert again.status_code == 409 and again.json()["type"] == "/problems/already-verified"
