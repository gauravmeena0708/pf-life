"""Phase 2, slice 8c on the running stack: a member in service since 2011 opts for pension on higher wages and the
employer validates the wages (dues worked out from the rules); the employer applies for a Certificate of Coverage for
a worker posted to Germany, uploads the signed application, the International Workers cell issues it and the
employer extends it; the international worker sees their coverage; an admitted EDLI claim is decided by the EDLI
section on verified wages. Repeatable: the CoC is for a fresh joinee; the pension option and the EDLI claim carry on
from an earlier run."""
import base64
import secrets
from datetime import UTC, datetime, timedelta

from tests.e2e.officers import decide, recommend
from tests.e2e.test_death_claims import file as file_death_claim
from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, step_up, wait_for
from tests.e2e.test_journey_b_claim import case_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

WAGES = "\n".join(f"{y}-{m:02d},40000" for y in (2015, 2016) for m in range(1, 13))
OFFICERS = {"fo.ss": "ro-ss", "fo.ao": "ro-ao", "fo.apfc": "ro-apfc", "fo.oic": "ro-oic"}


def test_joint_option_for_higher_pension_validated_by_the_employer(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    h = persona("member-h", "/member/pension")
    uan = call(h, "GET", "/api/v1/members/me")[1]["data"]["uan"]
    mine = call(h, "GET", "/api/v1/members/me/higher-pension-options")[1]["data"]
    assert mine["in_service_on"] == "2014-09-01"
    if not mine["options"]:
        status, r = call(h, "POST", "/api/v1/members/me/higher-pension-options",
                         {"higher_wages_from": "2014-09", "declaration": True, "consent_to_dues_adjustment": True},
                         {"X-Step-Up-Token": step_up(h, "submit-higher-pension-option", uan)})
        assert status == 201 and r["data"]["state"] == "SUBMITTED", r
    a = persona("member-a", "/member/pension")
    refused = call(a, "POST", "/api/v1/members/me/higher-pension-options",
                   {"higher_wages_from": "2022-06", "declaration": True, "consent_to_dues_adjustment": True},
                   {"X-Step-Up-Token": step_up(a, "submit-higher-pension-option", "100000000001")})
    assert refused[0] == 422 and "in service on" in refused[1]["detail"], refused

    sig = persona("emp-signatory", "/employer/members")
    option = next(o for o in call(sig, "GET", "/api/v1/employers/me/higher-pension-options")[1]["data"] if o["uan"] == uan)
    if option["state"] == "SUBMITTED":
        body = {"decision": "VALIDATE", "wages": WAGES, "note": "Wages as paid, from the payroll register"}
        status, preview = call(sig, "POST", f"/api/v1/employers/me/higher-pension-options/{option['option_id']}/dues-previews", body)
        assert status == 200 and preview["data"]["dues_paise"] == 24 * (4000000 - 1500000) * 833 // 10000, preview
        status, r = call(sig, "POST", f"/api/v1/employers/me/higher-pension-options/{option['option_id']}/validations", body,
                         {"X-Step-Up-Token": step_up(sig, "validate-higher-pension", option["option_id"], None, preview["data"]["dues_paise"])})
        assert status == 200 and r["data"]["state"] == "VALIDATED", r
    mine = call(h, "GET", f"/api/v1/members/me/higher-pension-options/{option['option_id']}")[1]["data"]
    assert mine["state"] == "VALIDATED" and mine["dues_paise"] > 0 and len(mine["wages"]) == 24


def test_certificate_of_coverage_issued_and_extended(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    operator = persona("emp-preparer", "/employer/registration")
    tag = secrets.token_hex(3).upper()
    today = datetime.now(UTC).date()
    status, r = call(operator, "POST", "/api/v1/employers/me/members", {
        "name": f"Posted {tag} Demo", "date_of_birth": "1990-03-03", "gender": "FEMALE",
        "aadhaar": f"{secrets.choice('23456789')}{secrets.randbelow(10**10):010d}5", "mobile": "9876511111",
        "date_of_joining": (today - timedelta(days=30)).isoformat()})
    assert status == 201, r
    uan, link = r["data"]["uan"], r["data"]["account_link_id"]

    sig = persona("emp-signatory", "/employer/international")
    countries = {x["country"]: x for x in call(sig, "GET", "/api/v1/international/agreements")[1]["data"]["agreements"]}
    assert countries["Germany"]["max_extension_months"] > 0
    start, end = today + timedelta(days=30), today + timedelta(days=30 + 365)
    body = {"uan": uan, "account_link_id": link, "country": "Germany", "host_employer": "Demo GmbH (synthetic)",
            "posting_from": start.isoformat(), "posting_to": end.isoformat()}
    too_long = call(sig, "POST", "/api/v1/international/coc-applications", {**body, "posting_to": (start + timedelta(days=31 * 60)).isoformat()})
    assert too_long[0] in (404, 422), too_long
    status, app = wait_for(lambda: (lambda x: x if x[0] == 201 else None)(
        call(sig, "POST", "/api/v1/international/coc-applications", body)), timeout=30, every=2)    # the joinee reaches the service by event
    app_id = app["data"]["application_id"]
    assert app["data"]["state"] == "AWAITING_SIGNED_UPLOAD"
    assert call(sig, "POST", "/api/v1/international/coc-applications", body)[0] == 422            # overlaps the first
    pdf = base64.b64encode(b"%PDF-1.4\n% signed CoC application (synthetic)\n").decode()
    status, r = call(sig, "POST", f"/api/v1/international/coc-applications/{app_id}/signed-uploads",
                     {"filename": "coc-application-signed.pdf", "content_base64": pdf})
    assert status == 200 and r["data"]["state"] == "SUBMITTED", r

    iw = persona("iw-officer", "/office/international")
    assert any(x["application_id"] == app_id for x in call(iw, "GET", "/api/v1/office/international/coc-applications")[1]["data"])
    status, r = call(iw, "POST", f"/api/v1/office/international/coc-applications/{app_id}/decisions",
                     {"decision": "ISSUE", "reason": "Posting letter and signed application verified"},
                     {"X-Step-Up-Token": step_up(iw, "decide-coc", app_id)})
    assert status == 200 and r["data"]["state"] == "ISSUED" and r["data"]["certificate_no"].startswith("IN-COC-DEU-"), r
    cert = call(sig, "GET", f"/api/v1/international/coc-applications/{app_id}/certificate")[1]["data"]
    assert cert["uan"] == uan and "Germany" in cert["text"] and cert["verification_code"]
    status, ext = call(sig, "POST", f"/api/v1/international/coc-applications/{app_id}/extensions",
                       {"posting_to": (end + timedelta(days=180)).isoformat()})
    assert status == 201 and ext["data"]["kind"] == "EXTENSION" and ext["data"]["posting_from"] == (end + timedelta(days=1)).isoformat(), ext

    ho = persona("ho-iwu", "/ho/agreements")
    assert len(call(ho, "GET", "/api/v1/international/agreements")[1]["data"]["agreements"]) == 20          # India's 20 partner countries (illustrative terms)
    expat = persona("worker-expat", "/international-worker")
    me = call(expat, "GET", "/api/v1/members/me/international")[1]["data"]
    assert me["nationality"] == "United States" and me["agreement"] is None and "full wages" in me["coverage"]


def test_the_edli_section_decides_an_admitted_edli_claim(persona):
    claimant = persona("claimant-a", "/claimant")
    c = file_death_claim(claimant, "FORM_5IF")
    claim_id = c["claim_id"]
    track = lambda: call(claimant, "GET", f"/api/v1/claimants/death-claims/{claim_id}")[1]["data"]  # noqa: E731
    if c["state"] == "UNDER_REVIEW":
        da = persona("do-caseworker", "/office/work-queue")
        case = wait_for(lambda: case_for(da, claim_id))
        status, r = recommend(da, case, "EDLI claim of the nominee", checks=("Death certificate seen", "Nomination on record"))
        assert status == 200, r
        wait_for(lambda: track()["state"] != "UNDER_REVIEW", timeout=30)
    while track()["state"] in ("RECOMMENDED", "AWAITING_NEXT_APPROVAL"):
        state = track()["state"]
        officer = None
        for name in OFFICERS.values():
            page = persona(name, "/office/work-queue")
            case = case_for(page, claim_id)
            if case:
                officer = (page, case)
                break
        assert officer, f"no officer holds claim {claim_id}"
        status, r = decide(officer[0], officer[1], "decisions" if state == "RECOMMENDED" else "second-approvals",
                           reason="Admitted: death in service and nomination in order")
        assert status == 200, r
        wait_for(lambda: track()["state"] != state, timeout=30)
    if track()["state"] == "PENDING_EDLI_DECISION":
        edli = persona("ro-edli", "/office/edli-claims")
        assert any(x["claim_id"] == claim_id for x in call(edli, "GET", "/api/v1/office/edli-claims")[1]["data"])
        status, p = call(edli, "POST", f"/api/v1/office/edli-claims/{claim_id}/benefit-previews", {"average_monthly_wages_paise": 1400000})
        assert status == 200, p
        status, r = call(edli, "POST", f"/api/v1/office/edli-claims/{claim_id}/decisions",
                         {"decision": "APPROVE", "average_monthly_wages_paise": 1400000, "reason": "Average wages verified on the Form 5IF certificate"},
                         {"X-Step-Up-Token": step_up(edli, "decide-edli", claim_id, p["data"]["version"], p["data"]["amount_paise"])})
        assert status == 200 and r["data"]["state"] == "APPROVED" and r["data"]["amount_paise"] == p["data"]["amount_paise"], r
    assert track()["state"] in ("APPROVED", "PAYMENT_PENDING", "SETTLED")
