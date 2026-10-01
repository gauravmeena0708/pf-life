"""Phase 2, slice 12f on the running stack: the disaster-recovery site's replication status and a simulated failover
drill; a training sandbox; a request taken at a Nidhi Aapke Nikat camp; a totalisation claim routed under an
agreement; a foreign agency verifying a certificate of coverage with its own machine login; the composite death claim.
Repeatable: every run records its own drill, sandbox, camp request and claim."""
import json
import urllib.parse
import urllib.request

from tests.e2e.test_death_claims import UAN as DECEASED
from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

WEB, KEYCLOAK = "http://localhost:5173", "http://localhost:8080/realms/epfo-demo/protocol/openid-connect/token"


def test_dr_site_training_sandbox_and_camp(persona):
    adc = persona("ndc-adc", "/ndc/dr")
    status, r = call(adc, "GET", "/api/v1/ndc/dr/replication-status")
    assert status == 200 and len(r["data"]["databases"]) >= 10 and r["data"]["overall_status"] in ("IN_SYNC", "LAGGING"), r
    status, drill = call(adc, "POST", "/api/v1/ndc/dr/failover-drills", {"scenario": "DATABASE", "notes": "Quarterly drill (synthetic)"},
                         {"X-Step-Up-Token": step_up(adc, "run-failover-drill", "DATABASE")})
    assert status in (200, 201) and drill["data"]["rto_minutes"] > 0 and "within_target" in drill["data"], drill

    trainer = persona("pdnasa-trainer", "/training")
    status, sandbox = call(trainer, "POST", "/api/v1/training/sandboxes",
                           {"course": "Claims settlement for new DAs", "trainees": 3, "personas": ["member-a", "do-caseworker"], "starts_on": "2026-10-05"})
    assert status in (200, 201) and len(sandbox["data"]["training_logins"]) == 3, sandbox
    assert call(trainer, "POST", "/api/v1/training/sandboxes",
                {"course": "Claims settlement for new DAs", "trainees": 3, "personas": ["vigilance-investigator"], "starts_on": "2026-10-05"})[0] in (400, 422)

    nan = persona("ro-nan", "/office/nan-camp")
    status, r = call(nan, "POST", "/api/v1/office/outreach-camps/NAN-RO1-2026-10/assisted-requests",
                     {"kind": "INOPERATIVE_ACCOUNT", "name": "Synthetic Visitor", "mobile": "9876500123", "uan": "100000000910",
                      "details": "Left work in 2019; wants the old balance."})
    assert status in (200, 201) and r["data"]["reference"].startswith("NAN/") and "co-workers" in r["data"]["next_step"], r
    assert call(nan, "POST", "/api/v1/office/outreach-camps/NAN-UNKNOWN/assisted-requests",
                {"kind": "UAN_HELP", "name": "X Demo", "mobile": "9876500123", "details": "Needs help with the UAN."})[0] == 404


def test_totalisation_claim_and_foreign_agency_check(persona):
    iwu = persona("ho-iwu", "/ho/agreements")
    agreements = call(iwu, "GET", "/api/v1/international/agreements")[1]["data"]["agreements"]
    country = next(a["country"] for a in agreements if a.get("totalisation"))
    body = {"direction": "OUTBOUND", "country": country, "uan": "100000000901", "foreign_insurance_no": "F-123456", "benefit": "OLD_AGE",
            "periods": [{"from": "2010-04-01", "to": "2014-03-31", "country": country}, {"from": "2014-04-01", "to": "2020-03-31", "country": "India"}],
            "notes": "Member worked abroad before joining in India (synthetic)."}
    status, r = call(iwu, "POST", "/api/v1/international/totalisation-claims", body)
    assert status in (200, 201) and r["data"]["reference"].startswith("TOT/"), r
    no_totalisation = next((a["country"] for a in agreements if not a.get("totalisation")), None)
    if no_totalisation:
        assert call(iwu, "POST", "/api/v1/international/totalisation-claims", {**body, "country": no_totalisation})[0] in (400, 422)

    sig = persona("emp-signatory", "/employer/international")
    issued = [a for a in call(sig, "GET", "/api/v1/international/coc-applications")[1]["data"] if a.get("certificate_no")]
    assert issued, "a certificate from P2.8c's end-to-end test is needed"
    token = json.loads(urllib.request.urlopen(urllib.request.Request(KEYCLOAK, data=urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": "foreign-agency-demo", "client_secret": "change-me-foreign-agency-secret"}).encode()),
        timeout=15).read())["access_token"]

    def verify(number):
        req = urllib.request.Request(f"{WEB}/api/v1/partners/foreign-agencies/coc-certificates/{number}", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    status, r = verify(issued[0]["certificate_no"])
    assert status == 200 and r["data"]["certificate_no"] == issued[0]["certificate_no"] and "uan" not in json.dumps(r).lower(), r
    assert verify("IN-COC-XXX-000000")[0] == 404


def test_composite_death_claim(persona):
    claimant = persona("claimant-a", "/claimant")
    status, r = call(claimant, "POST", "/api/v1/claimants/death-claims", {"form_type": "CCF_DEATH", "deceased_uan": DECEASED},
                     {"X-Step-Up-Token": step_up(claimant, "file-death-claim", DECEASED)})
    if status == 409:                                                           # the PF or EDLI claim is open since an earlier test
        assert r["type"] == "/problems/claim-already-open", r
    else:
        assert status == 201 and r["data"]["composite_ref"] and {c["form_type"] for c in r["data"]["claims"]} == {"20", "5IF"}, r
