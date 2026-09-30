"""Certificates of Coverage and international-worker coverage against the synthetic seed."""
import asyncio
import base64
import hashlib
import importlib
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import JWKS, KEY, KID

SEED_FILE = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"
with SEED_FILE.open(encoding="utf-8") as f:
    SEED = json.load(f)
S = SEED["keycloak_subjects"]
EST = "EST-DEMO-0001"
BASE = "/api/v1/international/coc-applications"
OFFICE = "/api/v1/office/international/coc-applications"
PDF = b"%PDF-1.4 test"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/international.db")
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base
    from app.infra.tables import metadata

    async def setup():
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            await c.run_sync(metadata.create_all)
        from app import seed
        seed.SEED_FILE = str(SEED_FILE)
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app
    app = create_app()
    epfo_auth.configure(audience="international-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def deliver(event_type, payload):
        from app.infra.messaging import dispatch
        from epfo_persistence.consumer import apply_once
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "correlation_id": str(uuid.uuid4()), "payload": payload}
        asyncio.run(apply_once(db.sessions(), event, dispatch))

    def q(sql):
        async def run():
            async with db.engine().connect() as c:
                return (await c.execute(text(sql))).all()
        return asyncio.run(run())
    yield TestClient(app, raise_server_exceptions=False), q, deliver
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(subject, stakeholder, step_up=None, establishment=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "international-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if establishment:
        claims["establishment_id"] = establishment
    if step_up:
        claims["step_up"] = step_up
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def signatory():
    return hdr(S["emp-signatory"], "employer.signatory", establishment=EST)


def posting(country="Germany", months=12):
    # Future, whole calendar months avoid the service's 90-day late-application limit.
    start = date(datetime.now(UTC).year + 1, 1, 1)
    end_year, end_month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return {"uan": "100000000001", "account_link_id": "AL-0001", "country": country,
            "host_employer": "Synthetic Overseas Employer", "posting_from": start.isoformat(),
            "posting_to": (date(end_year, end_month + 1, 1) - timedelta(days=1)).isoformat()}


def apply(client, body=None):
    response = client.post(BASE, json=body or posting(), headers=signatory())
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload(client, application_id):
    response = client.post(f"{BASE}/{application_id}/signed-uploads", headers=signatory(),
                           json={"filename": "signed.pdf", "content_base64": base64.b64encode(PDF).decode()})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "SUBMITTED"
    return response.json()["data"]


def issue(client, application_id):
    response = client.post(f"{OFFICE}/{application_id}/decisions",
                           json={"decision": "ISSUE", "reason": "Signed application verified"},
                           headers=hdr(S["iw-officer"], "fo.iw", {"action": "decide-coc", "resource_id": application_id}))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "ISSUED"
    return response.json()["data"]


@pytest.mark.parametrize("subject,stakeholder", [("ho-iwu", "ho.iwu"), ("emp-signatory", "employer.signatory")])
def test_agreements_catalogue(ctx, subject, stakeholder):
    client, _, _ = ctx
    response = client.get("/api/v1/international/agreements", headers=hdr(S[subject], stakeholder, establishment=EST))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    agreements = {a["country"]: a for a in data["agreements"]}
    assert agreements["Germany"]["max_posting_months"] == 48
    assert agreements["Germany"]["max_extension_months"] == 12
    assert agreements["France"]["max_extension_months"] == 0
    assert "Synthetic" in data["note"]


def test_member_cannot_read_agreements(ctx):
    client, _, _ = ctx
    assert client.get("/api/v1/international/agreements", headers=hdr(S["member-a"], "member")).status_code == 403


@pytest.mark.parametrize("changes,message", [
    ({"country": "United States"}, "no social-security agreement"),
    ({"posting_to": None}, "at most 48 months"),
    ({"uan": "100000000907", "account_link_id": "AL-0908"}, "international worker"),
])
def test_apply_refuses_invalid_postings(ctx, changes, message):
    client, q, _ = ctx
    body = posting(months=49) if changes.get("posting_to", "present") is None else {**posting(), **changes}
    response = client.post(BASE, json=body, headers=signatory())
    assert response.status_code == 422, response.text
    assert response.json()["type"] == "/problems/coc-invalid"
    assert message in response.json()["detail"]
    assert q("SELECT COUNT(*) FROM coc_applications") == [(0,)]


def test_member_of_another_establishment_is_not_found(ctx):
    client, _, deliver = ctx
    deliver("MemberRegistered.v1", {"account_link_id": "AL-OTHER", "uan": "100000000999", "name": "Other Worker",
                                   "establishment_id": "EST-OTHER", "date_of_joining": "2022-06-01"})
    response = client.post(BASE, json={**posting(), "account_link_id": "AL-OTHER", "uan": "100000000999"}, headers=signatory())
    assert response.status_code == 404, response.text


def test_apply_upload_issue_and_download_certificate(ctx):
    client, q, _ = ctx
    body = posting()
    application = apply(client, body)
    application_id = application["application_id"]
    assert application["kind"] == "NEW" and application["state"] == "AWAITING_SIGNED_UPLOAD"
    submitted = upload(client, application_id)
    assert submitted["signed_upload"] == {"filename": "signed.pdf", "size_bytes": len(PDF), "sha256": hashlib.sha256(PDF).hexdigest()}
    queue = client.get(OFFICE, headers=hdr(S["iw-officer"], "fo.iw"))
    assert queue.status_code == 200, queue.text
    assert [(r["application_id"], r["state"]) for r in queue.json()["data"]] == [(application_id, "SUBMITTED")]
    url = f"{OFFICE}/{application_id}/decisions"
    decision = {"decision": "ISSUE", "reason": "Signed application verified"}
    assert client.post(url, json=decision, headers=hdr(S["iw-officer"], "fo.iw")).status_code == 428
    for step in ({"action": "wrong-action", "resource_id": application_id},
                 {"action": "decide-coc", "resource_id": "COC-OTHER"}):
        assert client.post(url, json=decision, headers=hdr(S["iw-officer"], "fo.iw", step)).status_code == 403
    assert q("SELECT state FROM coc_applications") == [("SUBMITTED",)]
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='CertificateOfCoverageIssued.v1'") == [(0,)]
    issued = issue(client, application_id)
    assert issued["certificate_no"].startswith("IN-COC-DEU-")
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='CertificateOfCoverageIssued.v1'")
    event = json.loads(payload)["envelope"]["payload"]
    assert event == {"application_id": application_id, "certificate_no": issued["certificate_no"],
                     "uan": body["uan"], "account_link_id": body["account_link_id"], "country": body["country"],
                     "posting_from": body["posting_from"], "posting_to": body["posting_to"]}
    response = client.get(f"{BASE}/{application_id}/certificate", headers=signatory())
    assert response.status_code == 200, response.text
    certificate = response.json()["data"]
    assert certificate["certificate_no"] == issued["certificate_no"]
    assert "ASHA DEMO" in certificate["text"] and "Germany" in certificate["text"]
    assert issued["certificate_no"] in certificate["text"]
    expected_code = hashlib.sha256(f"{issued['certificate_no']}|{body['uan']}|{body['posting_from']}|{body['posting_to']}".encode()).hexdigest()[:20]
    assert certificate["verification_code"] == expected_code
    overlap = client.post(BASE, json=body, headers=signatory())
    assert overlap.status_code == 422 and "already covers part" in overlap.json()["detail"]


def test_non_pdf_upload_leaves_application_awaiting_upload(ctx):
    client, q, _ = ctx
    application = apply(client)
    response = client.post(f"{BASE}/{application['application_id']}/signed-uploads", headers=signatory(),
                           json={"filename": "signed.pdf", "content_base64": base64.b64encode(b"not a PDF").decode()})
    assert response.status_code == 422, response.text
    assert q("SELECT state, signed_upload FROM coc_applications") == [("AWAITING_SIGNED_UPLOAD", None)]


@pytest.mark.parametrize("country,months,status", [("Germany", 48, 201), ("France", 12, 422)])
def test_extension_terms(ctx, country, months, status):
    client, q, _ = ctx
    application = apply(client, posting(country, months))
    application_id = application["application_id"]
    upload(client, application_id)
    issue(client, application_id)
    extended_to = posting(country, months + 6)["posting_to"]
    response = client.post(f"{BASE}/{application_id}/extensions", json={"posting_to": extended_to}, headers=signatory())
    assert response.status_code == status, response.text
    if status == 201:
        extension = response.json()["data"]
        assert extension["kind"] == "EXTENSION" and extension["parent_id"] == application_id
        assert extension["state"] == "AWAITING_SIGNED_UPLOAD"
        assert extension["posting_from"] == (date.fromisoformat(application["posting_to"]) + timedelta(days=1)).isoformat()
        assert extension["posting_to"] == extended_to
        assert extension["uan"] == application["uan"] and extension["country"] == country
    else:
        assert "allows no extension" in response.json()["detail"]
        assert q("SELECT COUNT(*) FROM coc_applications") == [(1,)]


def test_international_worker_sees_full_wage_coverage_without_agreement(ctx):
    client, _, _ = ctx
    response = client.get("/api/v1/members/me/international", headers=hdr(S["worker-expat"], "intl_worker"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["nationality"] == "United States" and data["agreement"] is None
    assert data["international_worker"] is True and "full wages" in data["coverage"]
    assert data["employment"][0]["account_link_id"] == "AL-0908"


def test_registered_member_event_enables_an_application(ctx):
    client, q, deliver = ctx
    body = {**posting(), "uan": "100000000998", "account_link_id": "AL-NEW"}
    assert client.post(BASE, json=body, headers=signatory()).status_code == 404
    payload = {"uan": body["uan"], "account_link_id": body["account_link_id"], "name": "Registered Worker",
               "member_subject": "registered-worker", "establishment_id": EST, "date_of_joining": "2022-06-01"}
    deliver("MemberRegistered.v1", payload)
    deliver("MemberRegistered.v1", payload)  # A redelivery under a new event ID still projects one member.
    assert q("SELECT uan, subject FROM members WHERE account_link_id='AL-NEW'") == [(body["uan"], "registered-worker")]
    application = apply(client, body)
    assert application["uan"] == body["uan"] and application["account_link_id"] == "AL-NEW"
