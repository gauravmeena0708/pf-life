"""Phase 2, slice 6b on the running stack: the owner registers the signatory's DSC and sends the signed request
letter; the APFC approves it (Authorized eSign List); the signatory sees what waits for signature; the widow of a
member who died in service files Form 10D for a family pension, which reaches the DA (Accounts)."""
import base64

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

EST = "EST-DEMO-0001"
PDF = base64.b64encode(b"%PDF-1.4 signed signatory request letter (synthetic)").decode()


def test_dsc_registration_letter_and_office_approval(persona):
    owner = persona("emp-owner", "/employer/establishment")
    ensure_verified_and_granted(owner)
    sid = next(s["grant_id"] for s in call(owner, "GET", "/api/v1/employers/me/signatories")[1]["data"]
               if s["username"] == "emp-signatory" and s["status"] == "ACTIVE")

    def mine():
        return next((r for r in call(owner, "GET", "/api/v1/employers/me/signature-registrations")[1]["data"]
                     if r["signatory_id"] == sid and r["purpose"] == "REGISTER" and r["state"] != "REJECTED"), None)
    if not mine():
        status, r = call(owner, "POST", f"/api/v1/employers/me/signatories/{sid}/dsc-registrations",
                         {"certificate_serial": "3A5F9C2B11D0", "issuer": "Demo CA (mock)", "holder_name": "Signatory Demo", "valid_to": "2028-03-31"},
                         {"X-Step-Up-Token": step_up(owner, "register-signature", sid)})
        assert status == 201, r
    if mine()["state"] == "LETTER_PENDING":
        status, r = call(owner, "POST", f"/api/v1/employers/me/signatories/{sid}/request-letters", {"filename": "request.pdf", "content_base64": PDF})
        assert status == 201 and r["data"]["state"] == "PENDING_OFFICE", r
    reg = mine()
    if reg["state"] == "PENDING_OFFICE":
        apfc = persona("ro-apfc", "/office/olre")
        assert any(x["reg_id"] == reg["reg_id"] for x in call(apfc, "GET", "/api/v1/office/signature-registrations")[1]["data"])
        status, r = call(apfc, "POST", f"/api/v1/office/establishments/{EST}/signature-registrations/{reg['reg_id']}/decisions",
                         {"decision": "APPROVE", "note": "Letter on the letterhead, signed by the owner"},
                         {"X-Step-Up-Token": step_up(apfc, "decide-signature-registration", reg["reg_id"])})
        assert status == 200, r
    assert mine()["state"] == "APPROVED"
    signatory = persona("emp-signatory", "/employer/members")
    status, pending = call(signatory, "GET", "/api/v1/employers/me/pending-approvals")
    assert status == 200 and "items" in pending["data"], pending


def test_widow_files_form_10d_for_a_family_pension(persona):
    widow = persona("claimant-a", "/claimant")
    url = "/api/v1/claimants/family-pension-applications"
    status, r = call(widow, "POST", url, {"form_type": "FORM_10D", "deceased_uan": "100000000901"},
                     {"X-Step-Up-Token": step_up(widow, "file-family-pension", "100000000901")})
    assert status == 201 or r.get("type") == "/problems/already-applied", r
    if status == 201:
        assert r["data"]["kind"] == "SPOUSE" and r["data"]["estimate"]["monthly_paise"] >= 100000
    [claim] = call(widow, "GET", url)[1]["data"]
    da = persona("do-caseworker", "/office/pension-claims")
    wait_for(lambda: any(c["claim_id"] == claim["claim_id"] for c in call(da, "GET", "/api/v1/office/pension-claims")[1]["data"]), timeout=20)
