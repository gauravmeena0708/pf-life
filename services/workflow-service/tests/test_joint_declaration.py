"""Joint Declaration on the process engine: member → employer → DA → SS/AO → APFC (major) or AO (minor)."""
import json
import time
import uuid

import jwt

from tests.conftest import KEY, KID
from tests.test_cases_api import S, ctx, queue  # noqa: F401  (ctx is a fixture)

MEMBER_B, SIGNATORY = S["member-b"], S["emp-signatory"]
DA, SS, AO, APFC = S["do-caseworker"], S["ro-ss"], S["ro-ao"], S["ro-apfc"]
UAN_B = "100000000002"
EST = "EST-DEMO-0001"


def hdr(subject, stakeholder, step_up=None, establishment=None):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "workflow-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    if step_up:
        claims["step_up"] = step_up
    if establishment:
        claims["establishment_id"] = establishment
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def submit(client, parameter="NAME", subject=MEMBER_B, uan=UAN_B):
    return client.post("/api/v1/members/me/joint-declarations", json={
        "parameter": parameter, "current_value": "BHARAT DEMO", "corrected_value": "BHARAT KUMAR DEMO",
        "reason": "Name in the employer's records is incomplete"},
        headers=hdr(subject, "member", {"action": "submit-joint-declaration", "resource_id": uan}))


def attest(client, case, decision="ATTEST", establishment=EST):
    return client.post(f"/api/v1/employers/me/joint-declarations/{case['case_id']}/decisions",
                       json={"decision": decision, "note": "Matches our records"},
                       headers=hdr(SIGNATORY, "employer.signatory",
                                   {"action": "attest-joint-declaration", "resource_id": case["case_id"], "resource_version": case["version"]},
                                   establishment))


def office(client, case, path, subject, role, body, step=False):
    return client.post(f"/api/v1/office/member-change-requests/{case['case_id']}/{path}", json=body,
                       headers=hdr(subject, role, {"action": "decide-joint-declaration", "resource_id": case["case_id"],
                                                   "resource_version": case["version"]} if step else None))


def transitions(q):
    return [p["to_state"] for p in ((json.loads(x) if isinstance(x, str) else x)["envelope"]["payload"]
            for (x,) in q("SELECT payload FROM outbox WHERE event_type='ProcessTransitioned.v1' ORDER BY id"))]


def run_to_verified(client, parameter="NAME"):
    case = submit(client, parameter).json()["data"]
    case = attest(client, case).json()["data"]
    listed = client.get("/api/v1/office/member-change-requests", headers=hdr(DA, "fo.da_accounts")).json()["data"]
    assert [c["case_id"] for c in listed] == [case["case_id"]]
    case = office(client, case, "recommendations", DA, "fo.da_accounts", {"documents_checked": "YES", "note": "School certificate seen"}).json()["data"]
    return office(client, case, "verifications", SS, "fo.ss", {"finding": "CONSISTENT", "note": "Matches the KYC documents"}).json()["data"]


def test_major_change_goes_to_apfc_and_is_applied(ctx):
    client, q, _ = ctx
    r = submit(client)
    assert r.status_code == 200, r.json()
    case = r.json()["data"]
    assert case["state"] == "SUBMITTED" and case["data"]["change_class"] == "MAJOR" and case["subject_ref"] == UAN_B
    employer_list = client.get("/api/v1/employers/me/joint-declarations", headers=hdr(SIGNATORY, "employer.signatory", establishment=EST))
    assert [c["case_id"] for c in employer_list.json()["data"]] == [case["case_id"]]
    case = client.get("/api/v1/office/member-change-requests", headers=hdr(DA, "fo.da_accounts")).json()["data"]
    assert case == []                                                   # not attested yet: not in the office queue
    first = r.json()["data"]
    attested = attest(client, first).json()["data"]
    assert attested["state"] == "EMPLOYER_ATTESTED"
    case = office(client, attested, "recommendations", DA, "fo.da_accounts", {"documents_checked": "YES", "note": "School certificate seen"}).json()["data"]
    case = office(client, case, "verifications", SS, "fo.ss", {"finding": "CONSISTENT", "note": "Matches the KYC documents"}).json()["data"]
    [queued] = queue(client, APFC, "fo.apfc")
    assert queued["next_action"] == "decide"
    assert office(client, case, "decisions", AO, "fo.ao", {"decision": "APPROVE", "reason": "Documents are in order"}, step=True).status_code == 403
    r = office(client, case, "decisions", APFC, "fo.apfc", {"decision": "APPROVE", "reason": "Documents are in order"}, step=True)
    assert r.status_code == 200 and r.json()["data"]["state"] == "APPROVED"
    assert transitions(q) == ["SUBMITTED", "EMPLOYER_ATTESTED", "INITIATED", "VERIFIED", "APPROVED"]
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='ProcessTransitioned.v1' ORDER BY id DESC LIMIT 1")
    data = (json.loads(payload) if isinstance(payload, str) else payload)["envelope"]["payload"]["data"]
    assert data["parameter"] == "NAME" and data["corrected_value"] == "BHARAT KUMAR DEMO"


def test_minor_change_is_decided_by_the_ao(ctx):
    client, _, _ = ctx
    case = run_to_verified(client, parameter="FATHER_NAME")
    assert case["data"]["change_class"] == "MINOR"
    assert office(client, case, "decisions", APFC, "fo.apfc", {"decision": "APPROVE", "reason": "Documents are in order"}, step=True).status_code == 403
    r = office(client, case, "decisions", AO, "fo.ao", {"decision": "APPROVE", "reason": "Documents are in order"}, step=True)
    assert r.status_code == 200 and r.json()["data"]["state"] == "APPROVED"


def test_scope_member_self_and_employer_establishment(ctx):
    client, _, _ = ctx
    stranger = submit(client, subject=str(uuid.uuid4()))                   # no member record behind this login
    assert stranger.status_code == 404
    case = submit(client).json()["data"]
    assert submit(client).status_code == 409                                  # one open JD at a time
    assert attest(client, case, establishment="EST-OTHER").status_code == 404
    assert client.post(f"/api/v1/employers/me/joint-declarations/{case['case_id']}/decisions",
                       json={"decision": "ATTEST", "note": "ok ok"}, headers=hdr(SIGNATORY, "employer.signatory", establishment=EST)).status_code == 428


def test_return_to_da_starts_a_new_round_and_employer_rejection_closes(ctx):
    client, _, _ = ctx
    case = run_to_verified(client)
    r = office(client, case, "decisions", APFC, "fo.apfc", {"decision": "RETURN", "reason": "Attach the birth certificate"}, step=True)
    case = r.json()["data"]
    assert case["state"] == "EMPLOYER_ATTESTED"
    again = office(client, case, "recommendations", DA, "fo.da_accounts", {"documents_checked": "YES", "note": "Birth certificate now attached"})
    assert again.status_code == 200                                           # same DA may act in the new round
    other = submit(client, subject=S["member-a"], uan="100000000001").json()["data"]
    assert attest(client, other, decision="REJECT").json()["data"]["state"] == "REJECTED_BY_EMPLOYER"
    assert submit(client, subject=S["member-a"], uan="100000000001").status_code == 200   # closed: may file again
