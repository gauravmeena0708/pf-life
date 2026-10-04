"""P2.21b: a death reported by the civil registry (mock) and documents pushed to DigiLocker (mock). SQLite integration."""
import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import insert, select, text

from app.domain.exits import record_exit
from app.domain.life_events import crs_signature, on_ppo_issued, push_documents_due
from app.infra.tables import digilocker_documents, employments, members
from tests.test_member_api import MEMBER_A, SEED, api, token  # noqa: F401

FEED = "/api/v1/integrations/crs/death-registrations"
CRS = ("crs-demo-subject", "ext.crs")
PRO = SEED["keycloak_subjects"]["ro-pro"]


def run(coro):
    return asyncio.run(coro)


def registration(number, name="VIJAY DEMO", dob="1982-11-11", died="2026-09-30", aadhaar="DEMO-AADHAAR-100000000916"):
    return {"registration_no": number, "name": name, "date_of_birth": dob, "date_of_death": died, "aadhaar_ref": aadhaar,
            "signature": crs_signature(number, died, name)}


async def outbox(event_type):
    from app.infra.db import sessions
    async with sessions()() as session:
        return [r[0] for r in (await session.execute(text("SELECT payload FROM outbox WHERE event_type = :t ORDER BY id"), {"t": event_type})).all()]


def payloads(event_type):
    import json
    return [(p if isinstance(p, dict) else json.loads(p))["envelope"]["payload"] for p in run(outbox(event_type))]


def test_registry_death_closes_the_member_ids_and_announces_it_once(api):
    r = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0001"))
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert (d["outcome"], d["matched_uan"], d["matched_by"], d["exits_marked"]) == ("RECORDED", "100000000916", "AADHAAR", ["AL-0960"])
    exit_ = [p for p in payloads("MemberExitMarked.v1") if p["account_link_id"] == "AL-0960"]
    assert exit_ == [{"uan": "100000000916", "account_link_id": "AL-0960", "date_of_exit": "2026-09-30", "reason": "DEATH_IN_SERVICE",
                      "marked_by": "CIVIL_REGISTRY"}]
    deaths = [p for p in payloads("MemberDeathRecorded.v1") if p["uan"] == "100000000916"]
    assert deaths == [{"uan": "100000000916", "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY", "registration_no": "D-2026-DL-0001"}]
    again = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0001"))
    assert again.status_code == 200 and again.json()["data"]["outcome"] == "RECORDED"
    assert len([p for p in payloads("MemberDeathRecorded.v1") if p["uan"] == "100000000916"]) == 1     # a repeated record does nothing
    # a second registration of the same death (another registrar): already on record, nothing announced again
    second = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0002"))
    assert second.json()["data"]["outcome"] == "ALREADY_RECORDED"
    listed = api.get("/api/v1/office/civil-registry/deaths", headers=token(PRO, "fo.pro")).json()["data"]
    assert {x["registration_no"] for x in listed} >= {"D-2026-DL-0001", "D-2026-DL-0002"}


def test_feed_is_signed_and_only_for_the_registry(api):
    body = registration("D-2026-DL-0003")
    assert api.post(FEED, headers=token(*CRS), json={**body, "signature": "0" * 64}).status_code == 401
    assert api.post(FEED, headers=token(MEMBER_A), json=body).status_code == 403
    assert api.post(FEED, headers=token(*CRS), json={**registration("D-2026-DL-0004", died="2099-01-01")}).status_code == 422
    assert api.get("/api/v1/office/civil-registry/deaths", headers=token(MEMBER_A)).status_code == 403


def test_matching_by_name_and_birth_date(api):
    # BHARAT DEMO holds two UANs (one person, one Aadhaar): the record without an Aadhaar still matches him
    r = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0005", "Bharat Demo", "1985-11-02", "2026-09-01", None)).json()["data"]
    assert (r["outcome"], r["matched_by"]) == ("RECORDED", "NAME_AND_DOB")
    assert {p["uan"] for p in payloads("MemberDeathRecorded.v1")} >= {"100000000002", "100000000903"}
    nobody = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0006", "NOT A MEMBER", "1950-01-01", "2026-09-01", None))
    assert nobody.json()["data"]["outcome"] == "NOT_A_MEMBER" and nobody.json()["data"]["matched_uan"] is None

    async def twin():                                       # another person with the same name and date of birth
        from app.infra.db import sessions
        async with sessions()() as session, session.begin():
            row = dict((await session.execute(select(members).where(members.c.uan == "100000000005"))).mappings().one())
            await session.execute(insert(members).values(**{**row, "member_id": "DEMO-TWIN", "uan": "100000000999", "subject": None,
                                                            "aadhaar_ref": "DEMO-AADHAAR-TWIN"}))
            return row
    esha = run(twin())
    r = api.post(FEED, headers=token(*CRS), json=registration("D-2026-DL-0007", esha["name"], esha["date_of_birth"].isoformat(), "2026-09-01", None))
    assert r.json()["data"]["outcome"] == "AMBIGUOUS" and r.json()["data"]["exits_marked"] == []


def test_an_employer_marked_death_is_announced_too(api):
    async def mark():
        from app.infra.db import sessions
        async with sessions()() as session, session.begin():
            job = dict((await session.execute(select(employments).where(employments.c.account_link_id == "AL-0960"))).mappings().one())
            await record_exit(session, job, date(2026, 9, 29), "DEATH_IN_SERVICE", "EMPLOYER", None)
    run(mark())
    assert [p["source"] for p in payloads("MemberDeathRecorded.v1") if p["uan"] == "100000000916"] == ["EMPLOYER"]


def test_digilocker_push_retry_and_failure(api):
    path = "/api/v1/members/me/digilocker-documents"
    assert api.get(path, headers=token(MEMBER_A)).json()["data"] == []
    queued = api.post(path, headers=token(MEMBER_A), json={"doc_type": "UAN_CARD"})
    assert queued.status_code == 202 and queued.json()["data"]["state"] == "QUEUED"
    assert api.post(path, headers=token(MEMBER_A), json={"doc_type": "PPO"}).status_code in (400, 422)    # a PPO is issued, not asked for
    from app.infra.db import sessions
    sent = []

    async def ok(payload):
        sent.append(payload)
        return httpx.Response(201, json={"uri": "in.gov.epfindia.demo-UAN_CARD-ABC", "status": "ISSUED"})

    async def down(payload):
        return httpx.Response(503, json={"title": "DigiLocker unavailable"})

    async def push(at, transport):
        async with sessions()() as session, session.begin():
            await push_documents_due(session, at, transport)

    now = datetime.now(UTC) + timedelta(seconds=1)
    for minutes in (1, 5, 15, 60):
        run(push(now, down))
        doc = api.get(path, headers=token(MEMBER_A)).json()["data"][0]
        assert doc["state"] == "QUEUED" and doc["last_error"]
        run(push(now, ok))                                   # not due yet: nothing is sent
        assert not sent
        now += timedelta(minutes=minutes)
    run(push(now, down))
    doc = api.get(path, headers=token(MEMBER_A)).json()["data"][0]
    assert doc["state"] == "FAILED" and doc["attempts"] == 5 and "after 5 attempts" in doc["last_error"]
    assert api.post(path, headers=token(MEMBER_A), json={"doc_type": "UAN_CARD"}).json()["data"]["state"] == "QUEUED"   # asked again
    run(push(datetime.now(UTC) + timedelta(seconds=1), ok))
    doc = api.get(path, headers=token(MEMBER_A)).json()["data"][0]
    assert doc["state"] == "ISSUED" and doc["uri"] == "in.gov.epfindia.demo-UAN_CARD-ABC" and doc["issued_at"]
    assert sent[0]["doc_type"] == "UAN_CARD" and sent[0]["uan_masked"].endswith(SEED["members"][0]["uan"][-4:])
    assert SEED["members"][0]["uan"] not in str(sent[0])                                             # never the full UAN


def test_ppo_goes_to_the_members_digilocker_not_a_family_pension(api):
    async def issue(kind, ppo):
        from app.infra.db import sessions
        async with sessions()() as session, session.begin():
            await on_ppo_issued(session, {"payload": {"ppo_id": ppo, "pension_type": kind, "office_id": "RO-DEMO-01",
                                                      "uan": SEED["members"][0]["uan"], "pension_from": "2026-10-01"}})
            await on_ppo_issued(session, {"payload": {"ppo_id": ppo, "pension_type": kind, "office_id": "RO-DEMO-01",
                                                      "uan": SEED["members"][0]["uan"], "pension_from": "2026-10-01"}})
        async with sessions()() as session:
            return (await session.execute(select(digilocker_documents.c.reference).where(digilocker_documents.c.doc_type == "PPO"))).scalars().all()
    assert run(issue("SPOUSE", "PPO-DEMO-0101")) == []
    assert run(issue("MEMBER", "PPO-DEMO-0102")) == ["PPO-DEMO-0102"]
    docs = api.get("/api/v1/members/me/digilocker-documents", headers=token(MEMBER_A)).json()["data"]
    assert [d["title"] for d in docs] == ["e-PPO (pension payment order) — PPO-DEMO-0102"]
