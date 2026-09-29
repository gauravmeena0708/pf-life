"""Phase 2, slice 6b: a signatory's DSC / e-sign registration with the request letter and the PF office's approval
(the Authorized eSign List); a revocation backed by a revoke letter the office accepts."""
import base64

from tests.test_employer_api import EST, SUBJECTS, api, owner, token  # noqa: F401  (api is a fixture)

APFC = SUBJECTS["ro-apfc"]
PDF = base64.b64encode(b"%PDF-1.4 signed request letter (synthetic)").decode()


def signatory(api):
    r = api.post("/api/v1/employers/me/signatories/authorisations", json={"username": "emp-signatory", "grants": ["ecr.approve"]},
                 headers=owner({"action": "authorise-signatory", "resource_id": EST}))
    assert r.status_code == 201, r.json()
    return r.json()["data"]["grant_id"]


def apfc(step_up=None):
    return token(APFC, "fo.apfc", establishment=None, step_up=step_up)


def test_dsc_registration_letter_and_office_approval(api):
    sid = signatory(api)
    url = f"/api/v1/employers/me/signatories/{sid}"
    dsc = {"certificate_serial": "3A5F9C2B11D0", "issuer": "Demo CA (mock)", "holder_name": "Signatory Demo", "valid_to": "2028-03-31"}
    step = {"action": "register-signature", "resource_id": sid}
    assert api.post(f"{url}/dsc-registrations", json={**dsc, "valid_to": "2020-01-01"}, headers=owner(step)).json()["type"] == "/problems/certificate-expired"
    assert api.post(f"{url}/dsc-registrations", json=dsc, headers=owner()).status_code == 428
    reg = api.post(f"{url}/dsc-registrations", json=dsc, headers=owner(step)).json()["data"]
    assert reg["state"] == "LETTER_PENDING" and reg["details"]["certificate_serial"] == "…2B11D0"
    assert api.post(f"{url}/esign-registrations", json={"holder_name": "X Demo", "aadhaar_last4": "1234"}, headers=owner(step)).status_code == 409
    bad = {"filename": "letter.pdf", "content_base64": base64.b64encode(b"not a pdf").decode()}
    assert api.post(f"{url}/request-letters", json=bad, headers=owner()).status_code == 422
    sent = api.post(f"{url}/request-letters", json={"filename": "request letter.pdf", "content_base64": PDF}, headers=owner()).json()["data"]
    assert sent["state"] == "PENDING_OFFICE" and len(sent["letter"]["sha256"]) == 64 and sent["letter"]["filename"] == "request_letter.pdf"
    [pending] = api.get("/api/v1/office/signature-registrations", headers=apfc()).json()["data"]
    assert pending["reg_id"] == reg["reg_id"] and pending["username"] == "emp-signatory"
    decide = f"/api/v1/office/establishments/{EST}/signature-registrations/{reg['reg_id']}/decisions"
    body = {"decision": "APPROVE", "note": "Letter on the letterhead, signed by the owner"}
    assert api.post(decide, json=body, headers=apfc()).status_code == 428
    done = api.post(decide, json=body, headers=apfc({"action": "decide-signature-registration", "resource_id": reg["reg_id"]})).json()["data"]
    assert done["state"] == "APPROVED"
    listed = api.get("/api/v1/employers/me/signature-registrations", headers=owner()).json()["data"]
    assert [(x["purpose"], x["state"]) for x in listed] == [("REGISTER", "APPROVED")]

    # revocation: revoke the signatory, then the signed revoke letter goes to the office
    assert api.post(f"{url}/revoke-letters", json={"filename": "revoke.pdf", "content_base64": PDF}, headers=owner()).status_code == 409
    assert api.post(f"{url}/revocations", json={"reason": "Left the company"},
                    headers=owner({"action": "revoke-signatory", "resource_id": sid})).status_code == 200
    rev = api.post(f"{url}/revoke-letters", json={"filename": "revoke.pdf", "content_base64": PDF}, headers=owner()).json()["data"]
    assert rev["purpose"] == "REVOKE" and rev["state"] == "PENDING_OFFICE"
    api.post(f"/api/v1/office/establishments/{EST}/signature-registrations/{rev['reg_id']}/decisions", json={"decision": "APPROVE", "note": "Revoke letter in order"},
             headers=apfc({"action": "decide-signature-registration", "resource_id": rev["reg_id"]}))
    states = {x["purpose"]: x["state"] for x in api.get("/api/v1/employers/me/signature-registrations", headers=owner()).json()["data"]}
    assert states == {"REGISTER": "REVOKED", "REVOKE": "APPROVED"}
