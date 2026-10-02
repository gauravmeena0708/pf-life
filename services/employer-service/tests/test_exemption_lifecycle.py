"""Trust audit and the two exemption proceeding paths on SQLite."""
import asyncio
from datetime import date, timedelta

from sqlalchemy import text, update

from tests.test_employer_api import SEED, api, token


TRUSTS = [SEED["exempted_establishment"], *SEED["more_exempted_establishments"]["establishments"]]
SUBJECTS = SEED["keycloak_subjects"]


def trust(n=1, action=None, resource=None):
    ex = TRUSTS[n]
    step = {"action": action, "resource_id": resource or ex["establishment_id"]} if action else None
    return token(ex["trust_users"][0]["subject"], "exempted.trust", establishment=None, step_up=step)


def officer(name, action=None, resource=None):
    return token(SUBJECTS[name], {"ro-exemption": "fo.exemption", "ro-oic": "fo.oic",
                                  "zo-acc": "zo.acc", "ho-exemption": "ho.exemption"}[name],
                 establishment=None, step_up={"action": action, "resource_id": resource} if action else None)


def step(api, pid, name, who, status=200, **extra):
    response = api.post(f"/api/v1/office/exempted/proceedings/{pid}/steps",
                        json={"step": name, "note": "Synthetic case note", **extra},
                        headers=officer(who, "exemption-step", pid))
    assert response.status_code == status, response.text
    return response.json()["data"] if status == 200 else response


def decision(api, est, name, status=200, **extra):
    response = api.post(f"/api/v1/ho/exemptions/{est}/decisions",
                        json={"decision": name, "note": "Synthetic decision", **extra},
                        headers=officer("ho-exemption", "exemption-decision", est))
    assert response.status_code == status, response.text
    return response.json()["data"] if status == 200 else response


def surrender_body(days=30):
    return {"surrender_date": (date.today() + timedelta(days=days)).isoformat(),
            "bot_resolution_ref": "BOT/2026/1", "employer_undertaking": True, "employees_consent": True,
            "corpus_paise": 100000, "members": 10}


def test_audit_arithmetic_revision_and_scope(api):
    est = TRUSTS[1]["establishment_id"]
    body = {"financial_year": "2025-26", "auditor_name": "Demo Auditor", "auditor_registration": "REG/1",
            "opening_corpus_paise": 1000, "contributions_paise": 200, "interest_credited_paise": 30,
            "claims_paid_paise": 100, "other_paise": -10, "closing_corpus_paise": 1120,
            "opinion": "QUALIFIED", "observations": "Synthetic finding"}
    url = "/api/v1/exempted/me/audits"
    assert api.post(url, json={**body, "closing_corpus_paise": 1}, headers=trust()).status_code == 422
    assert api.post(url, json={**body, "observations": ""}, headers=trust()).status_code == 422
    assert api.post(url, json={**body, "financial_year": "2006-07"}, headers=trust()).status_code == 422
    filed = api.post(url, json=body, headers=trust())
    assert filed.status_code == 201, filed.text
    data = filed.json()["data"]
    assert data["due_on"] == "2026-09-30" and data["late_days"] == max(0, (date.today() - date(2026, 9, 30)).days)
    assert data["needs_attention"] == ["LATE", "QUALIFIED"]
    assert api.post(url, json=body, headers=trust()).status_code == 409
    revised = api.post(url, json={**body, "revised": True, "opinion": "UNQUALIFIED", "observations": None}, headers=trust())
    assert revised.status_code == 201, revised.text
    own = api.get(url, headers=trust()).json()["data"]
    assert {a["status"] for a in own} == {"CURRENT", "SUPERSEDED"}
    assert api.get(url, headers=trust(2)).json()["data"] == []
    assert len(api.get(f"/api/v1/office/exempted/{est}/audits", headers=officer("ro-exemption")).json()["data"]) == 2
    assert api.get(f"/api/v1/office/exempted/{est}/audits", headers=officer("ho-exemption")).status_code == 200


def test_surrender_full_chain_and_refusals(api):
    est = TRUSTS[1]["establishment_id"]
    url = "/api/v1/exempted/me/surrender-requests"
    assert api.post(url, json=surrender_body(1), headers=trust(1, "surrender-exemption")).status_code == 422
    assert api.post(url, json=surrender_body(), headers=trust(1)).status_code == 428
    start = api.post(url, json=surrender_body(), headers=trust(1, "surrender-exemption"))
    assert start.status_code == 201, start.text
    pid = start.json()["data"]["proceeding_id"]
    assert api.post(url, json=surrender_body(), headers=trust(1, "surrender-exemption")).status_code == 409
    step(api, pid, "PERMIT_UNEXEMPTED", "ro-exemption", 403)
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption", 409)
    assert api.post(f"/api/v1/office/exempted/proceedings/{pid}/steps",
                    json={"step": "PERMIT_UNEXEMPTED", "note": "Test"}, headers=officer("ro-oic")).status_code == 428
    permitted = step(api, pid, "PERMIT_UNEXEMPTED", "ro-oic")
    assert permitted["stage"] == "UNEXEMPTED_COMPLIANCE"
    assert api.get("/api/v1/exempted/me/profile", headers=trust(1)).json()["data"]["status"] == "UNEXEMPTED_COMPLIANCE"
    assert api.get("/api/v1/exempted/me/proceedings", headers=trust(1)).status_code == 200
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption")
    assert len(api.get("/api/v1/office/exempted/proceedings?stage=AT_ZO", headers=officer("zo-acc")).json()["data"]) == 1
    assert api.get("/api/v1/office/exempted/proceedings?stage=AT_ZO", headers=officer("ro-oic")).status_code == 200
    step(api, pid, "FORWARD_TO_HO", "zo-acc")
    assert decision(api, est, "CBT_RATIFIED", status=409).json()["title"].startswith("Stage")
    assert api.post(f"/api/v1/ho/exemptions/{est}/decisions",
                    json={"decision": "EEC_RECOMMENDED", "note": "Test"}, headers=officer("ho-exemption")).status_code == 428
    decision(api, est, "EEC_RECOMMENDED")
    decision(api, est, "CBT_RATIFIED")
    decision(api, est, "SENT_TO_GOVERNMENT")
    decision(api, est, "GOVERNMENT_NOTIFIED", reference="S.O. DEMO", date=date.today().isoformat())
    closed = step(api, pid, "GAZETTE_NOTIFY", "ro-exemption")
    assert closed["stage"] == "CLOSED" and closed["open"] is False
    assert api.get("/api/v1/exempted/me/profile", headers=trust(1)).json()["data"]["status"] == "SURRENDERED"
    from app import seed
    asyncio.run(seed.main())
    assert api.get("/api/v1/exempted/me/profile", headers=trust(1)).json()["data"]["status"] == "SURRENDERED"
    events = api.outbox_events()
    assert "ExemptionSurrenderRequested.v1" in events and events.count("ExemptionStatusChanged.v1") == 2
    assert events.count("ExemptionProceedingAdvanced.v1") == 9
    from app.infra.db import engine
    async def payloads():
        async with engine().connect() as conn:
            return [r[0] for r in (await conn.execute(text(
                "SELECT payload FROM outbox WHERE event_type = 'ExemptionStatusChanged.v1'"))).all()]
    import json
    status_events = [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for p in asyncio.run(payloads())]
    assert [p["status"] for p in status_events] == ["UNEXEMPTED_COMPLIANCE", "SURRENDERED"]
    assert all(p["ended_on"] == surrender_body()["surrender_date"] and p["past_accumulations_due"] for p in status_events)


def test_cancellation_reply_drop_and_no_reply(api):
    est = TRUSTS[2]["establishment_id"]
    url = f"/api/v1/office/exempted/{est}/cancellation-proceedings"
    body = {"grounds": [{"code": "CLAIMS_LATE", "text": "Synthetic late claims"}], "note": "Form CE-1"}
    assert api.post(url, json=body, headers=officer("ro-exemption")).status_code == 428
    response = api.post(url, json=body, headers=officer("ro-exemption", "show-cause-exemption", est))
    assert response.status_code == 201, response.text
    pid = response.json()["data"]["proceeding_id"]
    assert step(api, pid, "AGENDA_TO_ZO", "ro-exemption", 409)
    reply_url = f"/api/v1/exempted/me/proceedings/{pid}/replies"
    assert api.post(reply_url, json={"reply": "Response"}, headers=trust(2)).status_code == 428
    reply = api.post(reply_url, json={"reply": "Response"}, headers=trust(2, "reply-show-cause", pid))
    assert reply.status_code == 200 and reply.json()["data"]["stage"] == "REPLIED"
    assert step(api, pid, "DROP", "ro-exemption")["stage"] == "DROPPED"
    second = api.post(url, json=body, headers=officer("ro-exemption", "show-cause-exemption", est))
    assert second.status_code == 201, second.text
    pid2 = second.json()["data"]["proceeding_id"]
    from app.infra.db import engine
    from app.infra.tables import exemption_proceedings
    async def expire():
        async with engine().begin() as conn:
            await conn.execute(update(exemption_proceedings).where(exemption_proceedings.c.proceeding_id == pid2)
                               .values(reply_due=date.today() - timedelta(days=1)))
    asyncio.run(expire())
    assert step(api, pid2, "AGENDA_TO_ZO", "ro-exemption")["stage"] == "AT_ZO"


def test_relinquish_permit_and_zone_scope(api):
    est = TRUSTS[2]["establishment_id"]
    body = {"grounds": [{"code": "AUDIT_FINDINGS", "text": "Synthetic audit finding"}], "note": "Form CE-1"}
    opened = api.post(f"/api/v1/office/exempted/{est}/cancellation-proceedings", json=body,
                      headers=officer("ro-exemption", "show-cause-exemption", est))
    assert opened.status_code == 201, opened.text
    pid = opened.json()["data"]["proceeding_id"]
    reply = api.post(f"/api/v1/exempted/me/proceedings/{pid}/replies", json={"reply": "Relinquished", "relinquish": True},
                     headers=trust(2, "reply-show-cause", pid))
    assert reply.status_code == 200 and reply.json()["data"]["stage"] == "RELINQUISHED"
    step(api, pid, "PERMIT_UNEXEMPTED", "ro-oic")
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption")
    from app.infra.db import engine
    from app.infra.tables import establishments, offices
    async def change_zone(zone):
        async with engine().begin() as conn:
            await conn.execute(update(offices).where(offices.c.office_id == "RO-DEMO-02").values(zone_id=zone))
    async def change_office(office):
        async with engine().begin() as conn:
            await conn.execute(update(establishments).where(establishments.c.establishment_id == est).values(office_id=office))
    asyncio.run(change_office("RO-DEMO-02"))
    assert api.get("/api/v1/office/exempted/proceedings?stage=AT_ZO", headers=officer("ro-exemption")).json()["data"] == []
    assert len(api.get("/api/v1/office/exempted/proceedings?stage=AT_ZO", headers=officer("zo-acc")).json()["data"]) == 1
    asyncio.run(change_zone("ZO-OTHER"))
    assert api.get("/api/v1/office/exempted/proceedings?stage=AT_ZO", headers=officer("zo-acc")).json()["data"] == []
    step(api, pid, "FORWARD_TO_HO", "zo-acc", 403)
    asyncio.run(change_zone("ZO-DEMO-01"))
    assert step(api, pid, "FORWARD_TO_HO", "zo-acc")["stage"] == "AT_HO"


def test_return_reapply_remand_and_eec_return(api):
    est = TRUSTS[1]["establishment_id"]
    url = "/api/v1/exempted/me/surrender-requests"
    first = api.post(url, json=surrender_body(), headers=trust(1, "surrender-exemption"))
    assert first.status_code == 201, first.text
    first_id = first.json()["data"]["proceeding_id"]
    assert step(api, first_id, "RETURN_INCOMPLETE", "ro-exemption")["stage"] == "RETURNED"
    second = api.post(url, json=surrender_body(), headers=trust(1, "surrender-exemption"))
    assert second.status_code == 201, second.text
    pid = second.json()["data"]["proceeding_id"]
    step(api, pid, "PERMIT_UNEXEMPTED", "ro-oic")
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption")
    assert step(api, pid, "REMAND", "zo-acc")["stage"] == "UNEXEMPTED_COMPLIANCE"
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption")
    step(api, pid, "FORWARD_TO_HO", "zo-acc")
    assert decision(api, est, "EEC_RETURNED")["stage"] == "AT_ZO"
    assert step(api, pid, "REMAND", "zo-acc")["stage"] == "UNEXEMPTED_COMPLIANCE"   # down to the RO, not back up to HO
    step(api, pid, "AGENDA_TO_ZO", "ro-exemption")
    assert step(api, pid, "FORWARD_TO_HO", "zo-acc")["stage"] == "AT_HO"
