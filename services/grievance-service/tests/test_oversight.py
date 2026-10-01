"""RTI and CPGRAMS workflows."""
import hashlib
import hmac
import asyncio
from datetime import date, timedelta
from sqlalchemy import insert

from app.api.oversight_routes import SECRET
from tests.test_grievance_api import SEED, ctx, hdr

PRO = next(s["subject"] for s in SEED["office_staff"] if s["stakeholder"] == "fo.pro" and s["office_id"] == "RO-DEMO-01")
OTHER = "other-office-pro"


def add_other_pro():
    from app.infra.db import engine
    from app.infra.tables import office_staff
    async def write():
        async with engine().begin() as connection:
            await connection.execute(insert(office_staff).values(subject=OTHER, stakeholder="fo.pro", office_id="RO-DEMO-02"))
    asyncio.run(write())


def rti(days=0, **kw):
    body = {"applicant_name": "Demo Applicant", "received_on": (date.today()-timedelta(days=days)).isoformat(),
            "mode": "POST", "subject": "Pension record request", "information_sought": "Please provide the full pension payment record.",
            "fee_paid": True, "bpl": False}
    return {**body, **kw}


def test_rti_rules_scope_and_late_reply(ctx):
    client, events = ctx
    url = "/api/v1/office/rti-requests"
    pro = hdr(PRO, "fo.pro")
    assert client.post(url, json=rti(fee_paid=False), headers=pro).status_code == 422
    assert client.post(url, json=rti(fee_paid=False, bpl=True), headers=pro).status_code == 201
    made = client.post(url, json=rti(days=40), headers=pro)
    assert made.status_code == 201, made.text
    d = made.json()["data"]
    add_other_pro()
    assert d["registration_no"].startswith("RTI/RO-DEMO-01/")
    assert d["reply_due"] == (date.today()-timedelta(days=10)).isoformat()
    assert any(x["request_id"] == d["request_id"] and x["overdue"] for x in client.get(url+"?state=OPEN", headers=pro).json()["data"])
    reply_url = f"{url}/{d['request_id']}/replies"
    body = {"outcome": "REFUSED", "reply": "The requested record is exempt from disclosure."}
    assert client.post(reply_url, json=body, headers=pro).status_code == 422
    assert client.post(reply_url, json={**body, "exemption_section": "8(1)(j)"}, headers=hdr(OTHER, "fo.pro")).status_code == 404
    assert all(x["request_id"] != d["request_id"] for x in client.get(url, headers=hdr(OTHER, "fo.pro")).json()["data"])
    body["exemption_section"] = "8(1)(j)"
    replied = client.post(reply_url, json=body, headers=pro)
    assert replied.status_code == 200, replied.text
    assert replied.json()["data"]["late"] is True
    assert events("RtiReplied.v1") == [{"request_id": d["request_id"], "office_id": "RO-DEMO-01", "outcome": "REFUSED", "late": True}]
    assert client.post(reply_url, json=body, headers=pro).status_code == 409


def test_rti_transfer_five_day_flag(ctx):
    client, _ = ctx
    pro = hdr(PRO, "fo.pro")
    made = client.post("/api/v1/office/rti-requests", json=rti(days=6), headers=pro)
    assert made.status_code == 201, made.text
    url = f"/api/v1/office/rti-requests/{made.json()['data']['request_id']}/replies"
    body = {"outcome": "TRANSFERRED", "reply": "Transferring this request to the relevant authority."}
    assert client.post(url, json=body, headers=pro).status_code == 422
    done = client.post(url, json={**body, "transferred_to": "Other public authority"}, headers=pro)
    assert done.status_code == 200, done.text
    assert done.json()["data"]["transfer_late"] is True
    assert done.json()["data"]["late"] is False


def cpgrams():
    body = {"cpgrams_registration_no": "CPG/2026/0001", "name": "Demo Applicant", "mobile": "9876543210",
            "category": "CLAIM_DELAY", "description": "My pension payment has not reached the bank account.",
            "received_on": date.today().isoformat(), "uan": "100000000001", "office_id": "RO-DEMO-01"}
    parts = [body[x] for x in ("cpgrams_registration_no", "name", "mobile", "category", "description", "received_on", "uan", "office_id")]
    body["signature"] = hmac.new(SECRET.encode(), "|".join(parts).encode(), hashlib.sha256).hexdigest()
    return body


def test_cpgrams_signature_idempotency_and_queue(ctx):
    client, events = ctx
    url = "/api/v1/integrations/cpgrams/grievances"
    ext = hdr("cpgrams", "ext.cpgrams")
    body = cpgrams()
    assert client.post(url, json={**body, "signature": "0"*64}, headers=ext).status_code == 401
    made = client.post(url, json=body, headers=ext)
    assert made.status_code == 201, made.text
    gid = made.json()["data"]["grievance_id"]
    repeat = client.post(url, json=body, headers=ext)
    assert repeat.status_code == 200 and repeat.json()["data"]["grievance_id"] == gid
    assert len(events("GrievanceRegistered.v1")) == 1
    queue = client.get("/api/v1/office/grievances", headers=hdr(PRO, "fo.pro"))
    assert queue.status_code == 200, queue.text
    assert any(g["grievance_id"] == gid and g["source"] == "CPGRAMS" for g in queue.json()["data"])
