"""P2.22 on the running stack: the owner authorises payroll software; the provider (its own machine login, b2b-sandbox)
tests a payload in the conformance sandbox, then sends two pay runs for a month; the operator sees each member's month
totals and makes the month's ECR from them — EPS wages capped at the ceiling though the two runs add up past it; the
owner revokes the provider, which is refused at once. Repeatable: a random month of 2024-2025 each run (other tests file
returns for 2001-2023)."""
import json
import random
import secrets
import urllib.error
import urllib.parse
import urllib.request

from tests.e2e.test_journey_a_ecr import WEB, call, ensure_verified_and_granted, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

KEYCLOAK = "http://localhost:8080/realms/epfo-demo/protocol/openid-connect/token"
EST, A, B = "EST-DEMO-0001", "100000000001", "100000000002"


def provider(method, path, body=None):
    token = json.loads(urllib.request.urlopen(urllib.request.Request(KEYCLOAK, data=urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": "b2b-sandbox", "client_secret": "change-me-b2b-secret"}).encode()),
        timeout=15).read())["access_token"]
    req = urllib.request.Request(f"{WEB}/api/v1{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Establishment-Id": EST})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def row(uan, name, rupees):
    w = rupees * 100
    return {"uan": uan, "name": name, "gross_wages_paise": w, "epf_wages_paise": w, "eps_wages_paise": w, "edli_wages_paise": w, "ncp_days": 0}


def test_pay_runs_from_payroll_software_make_the_month_ecr(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    providers = call(owner, "GET", "/api/v1/employers/me/payroll-providers")[1]["data"]
    active = next((p for p in providers["authorised"] if p["provider_id"] == "PP-DEMO-1" and p["status"] == "ACTIVE"), None)
    if not active:
        status, r = call(owner, "POST", "/api/v1/employers/me/payroll-providers/authorisations", {"provider_id": "PP-DEMO-1"},
                         {"X-Step-Up-Token": step_up(owner, "authorise-payroll-provider", "PP-DEMO-1")})
        assert status == 201, r
        active = r["data"]

    month = f"{random.randint(2024, 2025)}-{random.randint(1, 12):02d}"
    bad = {"wage_month": month, "run_ref": "SANDBOX", "pay_date": f"{month}-15", "rows": [{**row(A, "ASHA DEMO", 10000), "eps_wages_paise": 2000000}]}
    status, r = provider("POST", "/partners/sandbox/payroll/pay-runs/validations", bad)
    assert status == 200 and r["data"]["valid"] is False and r["data"]["issues"], r          # EPS above the ceiling: said, not stored

    tag = secrets.token_hex(3).upper()
    for half, day in ((1, 15), (2, 28)):
        run = {"wage_month": month, "run_ref": f"RUN-{tag}-{half}", "pay_date": f"{month}-{day:02d}",
               "rows": [row(A, "ASHA DEMO", 10000), row(B, "BHARAT DEMO", 6000)]}
        status, r = provider("POST", "/partners/payroll/pay-runs", run)
        assert status == 201 and r["data"]["state"] == "ACCEPTED", r
    status, again = provider("POST", "/partners/payroll/pay-runs", run)
    assert status == 200 and again["data"]["run_ref"] == run["run_ref"], again                 # the same run twice: once

    operator = persona("emp-preparer", "/employer/pay-runs")
    summary = call(operator, "GET", f"/api/v1/employers/me/pay-runs?wage_month={month}")[1]["data"]
    asha = next(m for m in summary["members"] if m["uan"] == A)
    assert asha["epf_wages_paise"] == 2000000 and asha["runs"] == 2 and summary["can_make_ecr"], summary
    status, made = call(operator, "POST", f"/api/v1/employers/me/pay-runs/{month}/ecr-drafts")
    assert status == 201 and made["data"]["filing"]["state"] == "VALIDATED", made
    report = made["data"]["validation_report"]
    # EPS: Asha's ₹20,000 capped at ₹15,000 (₹1,250); Bharat's ₹12,000 under the ceiling (₹1,000)
    assert report["summary"]["totals_paise"]["AC10_EPS"] == 125000 + 100000, report["summary"]

    status, r = call(owner, "POST", f"/api/v1/employers/me/payroll-providers/authorisations/{active['grant_id']}/revocations",
                     {"reason": "Changed payroll vendor (test)"}, {"X-Step-Up-Token": step_up(owner, "revoke-payroll-provider", active["grant_id"])})
    assert status == 200, r
    status, _ = provider("POST", "/partners/payroll/pay-runs", {**run, "run_ref": f"RUN-{tag}-3"})
    assert status == 403                                                                     # cut off at once
