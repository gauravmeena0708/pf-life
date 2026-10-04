"""Tests for pay runs integration (P2.22): provider pay runs, validation sandbox,
employer summary, ECR draft generation, idempotency and authorization."""
import pytest
from tests.test_ecr_api import EST, MONTH, SEED, ctx, hdr, preparer

PROVIDER_SUB = "00000000-0000-4000-8000-000000000082"
MEMBERS = SEED["members"]


def provider_hdr(grants=("payroll.submit",), establishment=EST, **kw):
    return hdr(PROVIDER_SUB, "payroll_provider", grants, establishment=establishment, **kw)


def employer_hdr(**kw):
    return preparer(**kw)


def test_token_without_payroll_submit_refused(ctx):
    client, q = ctx
    payload = {
        "wage_month": MONTH,
        "run_ref": "RUN-AUTH-01",
        "pay_date": "2026-08-31",
        "rows": [{
            "uan": MEMBERS[0]["uan"],
            "name": MEMBERS[0]["name"],
            "gross_wages_paise": 1500000,
            "epf_wages_paise": 1500000,
            "eps_wages_paise": 1500000,
            "edli_wages_paise": 1500000,
            "ncp_days": 0,
        }],
    }
    # No grants -> 403
    r = client.post("/api/v1/partners/payroll/pay-runs", json=payload, headers=provider_hdr(grants=[]))
    assert r.status_code == 403
    assert r.json()["type"] == "/problems/missing-grant"

    # Wrong grant -> 403
    r = client.post("/api/v1/partners/payroll/pay-runs", json=payload, headers=provider_hdr(grants=["ecr.prepare"]))
    assert r.status_code == 403

    # Provider GET without payroll.submit -> 403
    r_get = client.get(f"/api/v1/partners/payroll/pay-runs?wage_month={MONTH}", headers=provider_hdr(grants=[]))
    assert r_get.status_code == 403


def test_unknown_uan_and_eps_above_ceiling_rejected(ctx):
    client, q = ctx

    # Unknown UAN
    bad_uan_payload = {
        "wage_month": MONTH,
        "run_ref": "RUN-BAD-UAN",
        "pay_date": "2026-08-31",
        "rows": [{
            "uan": "999999999999",
            "name": "UNKNOWN WORKER",
            "gross_wages_paise": 1500000,
            "epf_wages_paise": 1500000,
            "eps_wages_paise": 1500000,
            "edli_wages_paise": 1500000,
            "ncp_days": 0,
        }],
    }
    r_uan = client.post("/api/v1/partners/payroll/pay-runs", json=bad_uan_payload, headers=provider_hdr())
    assert r_uan.status_code == 422
    assert r_uan.json()["type"] == "/problems/pay-run-invalid"
    issues = r_uan.json()["issues"]
    assert any(i["code"] == "E-UAN-UNKNOWN" for i in issues)
    # Check nothing stored
    assert q("SELECT count(*) FROM pay_runs WHERE run_ref='RUN-BAD-UAN'")[0][0] == 0

    # EPS above ceiling (ceiling in 2026-08 is 15,000 rupees = 1,500,000 paise)
    high_eps_payload = {
        "wage_month": MONTH,
        "run_ref": "RUN-HIGH-EPS",
        "pay_date": "2026-08-31",
        "rows": [{
            "uan": MEMBERS[0]["uan"],
            "name": MEMBERS[0]["name"],
            "gross_wages_paise": 2500000,
            "epf_wages_paise": 2500000,
            "eps_wages_paise": 2500000,
            "edli_wages_paise": 1500000,
            "ncp_days": 0,
        }],
    }
    r_eps = client.post("/api/v1/partners/payroll/pay-runs", json=high_eps_payload, headers=provider_hdr())
    assert r_eps.status_code == 422
    assert r_eps.json()["type"] == "/problems/pay-run-invalid"
    issues_eps = r_eps.json()["issues"]
    assert any(i["code"] == "E-EPS-CEILING" for i in issues_eps)
    # Check nothing stored
    assert q("SELECT count(*) FROM pay_runs WHERE run_ref='RUN-HIGH-EPS'")[0][0] == 0


def test_sandbox_validation_stores_nothing(ctx):
    client, q = ctx

    valid_payload = {
        "wage_month": MONTH,
        "run_ref": "RUN-SANDBOX-VALID",
        "pay_date": "2026-08-31",
        "rows": [{
            "uan": MEMBERS[0]["uan"],
            "name": MEMBERS[0]["name"],
            "gross_wages_paise": 1500000,
            "epf_wages_paise": 1500000,
            "eps_wages_paise": 1500000,
            "edli_wages_paise": 1500000,
            "ncp_days": 0,
        }],
    }
    r_valid = client.post("/api/v1/partners/sandbox/payroll/pay-runs/validations", json=valid_payload, headers=provider_hdr())
    assert r_valid.status_code == 200
    res_valid = r_valid.json()["data"]
    assert res_valid["valid"] is True
    assert res_valid["issues"] == []
    assert q("SELECT count(*) FROM pay_runs WHERE run_ref='RUN-SANDBOX-VALID'")[0][0] == 0

    invalid_payload = {
        "wage_month": MONTH,
        "run_ref": "RUN-SANDBOX-INVALID",
        "pay_date": "2026-08-31",
        "rows": [{
            "uan": "999999999999",
            "name": "GHOST",
            "gross_wages_paise": 1500000,
            "epf_wages_paise": 1500000,
            "eps_wages_paise": 1500000,
            "edli_wages_paise": 1500000,
            "ncp_days": 0,
        }],
    }
    r_inv = client.post("/api/v1/partners/sandbox/payroll/pay-runs/validations", json=invalid_payload, headers=provider_hdr())
    assert r_inv.status_code == 200
    res_inv = r_inv.json()["data"]
    assert res_inv["valid"] is False
    assert any(i["code"] == "E-UAN-UNKNOWN" for i in res_inv["issues"])
    assert q("SELECT count(*) FROM pay_runs WHERE run_ref='RUN-SANDBOX-INVALID'")[0][0] == 0


def test_two_runs_accepted_summary_and_ecr_draft(ctx):
    client, q = ctx

    run1 = {
        "wage_month": MONTH,
        "run_ref": "RUN-2026-08-PART1",
        "pay_date": "2026-08-15",
        "rows": [
            {
                "uan": MEMBERS[0]["uan"],
                "name": MEMBERS[0]["name"],
                "gross_wages_paise": 700000,
                "epf_wages_paise": 700000,
                "eps_wages_paise": 700000,
                "edli_wages_paise": 700000,
                "ncp_days": 1,
            },
            {
                "uan": MEMBERS[1]["uan"],
                "name": MEMBERS[1]["name"],
                "gross_wages_paise": 1200000,
                "epf_wages_paise": 1200000,
                "eps_wages_paise": 1200000,
                "edli_wages_paise": 1200000,
                "ncp_days": 0,
            },
        ],
    }
    r1 = client.post("/api/v1/partners/payroll/pay-runs", json=run1, headers=provider_hdr())
    assert r1.status_code == 201, r1.json()
    d1 = r1.json()["data"]
    assert d1["state"] == "ACCEPTED"
    assert d1["totals"] == {"gross_paise": 1900000, "epf_wages_paise": 1900000, "rows": 2}
    assert d1["pay_run_id"].startswith("PR-")

    # One repeated run_ref returns the first with 200
    r1_repeat = client.post("/api/v1/partners/payroll/pay-runs", json=run1, headers=provider_hdr())
    assert r1_repeat.status_code == 200, r1_repeat.json()
    assert r1_repeat.json()["data"]["pay_run_id"] == d1["pay_run_id"]
    assert r1_repeat.json()["data"]["run_ref"] == "RUN-2026-08-PART1"

    # Second run for the demo month
    run2 = {
        "wage_month": MONTH,
        "run_ref": "RUN-2026-08-PART2",
        "pay_date": "2026-08-31",
        "rows": [
            {
                "uan": MEMBERS[0]["uan"],
                "name": MEMBERS[0]["name"],
                "gross_wages_paise": 800000,
                "epf_wages_paise": 800000,
                "eps_wages_paise": 800000,
                "edli_wages_paise": 800000,
                "ncp_days": 2,
            },
            {
                "uan": MEMBERS[2]["uan"],
                "name": MEMBERS[2]["name"],
                "gross_wages_paise": 1500000,
                "epf_wages_paise": 1500000,
                "eps_wages_paise": 1500000,
                "edli_wages_paise": 1500000,
                "ncp_days": 0,
            },
        ],
    }
    r2 = client.post("/api/v1/partners/payroll/pay-runs", json=run2, headers=provider_hdr())
    assert r2.status_code == 201, r2.json()
    d2 = r2.json()["data"]
    assert d2["state"] == "ACCEPTED"

    # GET /partners/payroll/pay-runs?wage_month=
    p_runs = client.get(f"/api/v1/partners/payroll/pay-runs?wage_month={MONTH}", headers=provider_hdr())
    assert p_runs.status_code == 200
    p_data = p_runs.json()["data"]
    assert len(p_data) == 2
    assert {x["run_ref"] for x in p_data} == {"RUN-2026-08-PART1", "RUN-2026-08-PART2"}

    # Employer summary sums member 0 over both runs
    emp_summary = client.get(f"/api/v1/employers/me/pay-runs?wage_month={MONTH}", headers=employer_hdr())
    assert emp_summary.status_code == 200, emp_summary.json()
    summary_data = emp_summary.json()["data"]
    assert summary_data["wage_month"] == MONTH
    assert summary_data["can_make_ecr"] is True
    assert len(summary_data["runs"]) == 2

    m0 = next(m for m in summary_data["members"] if m["uan"] == MEMBERS[0]["uan"])
    assert m0["runs"] == 2
    assert m0["gross_paise"] == 700000 + 800000 == 1500000
    assert m0["epf_wages_paise"] == 700000 + 800000 == 1500000
    assert m0["eps_wages_paise"] == 700000 + 800000 == 1500000
    assert m0["edli_wages_paise"] == 700000 + 800000 == 1500000
    assert m0["ncp_days"] == 1 + 2 == 3

    m1 = next(m for m in summary_data["members"] if m["uan"] == MEMBERS[1]["uan"])
    assert m1["runs"] == 1
    assert m1["epf_wages_paise"] == 1200000

    m2 = next(m for m in summary_data["members"] if m["uan"] == MEMBERS[2]["uan"])
    assert m2["runs"] == 1
    assert m2["epf_wages_paise"] == 1500000

    # The ECR made from them validates cleanly with each member's summed wages and the runs become INCLUDED
    ecr_draft = client.post(f"/api/v1/employers/me/pay-runs/{MONTH}/ecr-drafts", headers=employer_hdr())
    assert ecr_draft.status_code == 201, ecr_draft.json()
    draft_res = ecr_draft.json()["data"]
    filing = draft_res["filing"]
    report = draft_res["validation_report"]

    assert filing["state"] == "VALIDATED"
    assert report["valid"] is True
    assert report["summary"]["rows"] == 3
    # Check runs became INCLUDED with filing_id
    rows_in_db = q(f"SELECT run_ref, state, filing_id FROM pay_runs WHERE wage_month='{MONTH}'")
    assert len(rows_in_db) == 2
    for ref, state, fid in rows_in_db:
        assert state == "INCLUDED"
        assert fid == filing["filing_id"]

    # Making it again is refused (409)
    again = client.post(f"/api/v1/employers/me/pay-runs/{MONTH}/ecr-drafts", headers=employer_hdr())
    assert again.status_code == 409
    assert again.json()["type"] == "/problems/no-accepted-pay-runs"
