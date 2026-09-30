"""Synthetic dashboard reads respect postings, establishment scope and due-month rules."""
import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from sqlalchemy import func, insert, select

from app.api import compliance_routes, dashboard_routes
from app.infra.tables import claim_facts, grievance_facts, office_staff
from epfo_persistence.policy import baseline
from tests.conftest import KEY, KID
from tests.test_compliance_reads import compliance_data, employer_headers, fact, insert_facts
from tests.test_read_models import ctx, hdr

DISTRICT_PATH = "/api/v1/do/dashboards"
EMPLOYER_PATH = "/api/v1/employers/me/dashboard"
AS_OF = date(2026, 9, 30)
OFFICE = "RO-DEMO-01"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(dashboard_routes, "today", lambda: AS_OF)
    monkeypatch.setattr(compliance_routes, "today", lambda: AS_OF)


def write_rows(table, *rows):
    from app.infra.db import sessions

    async def write():
        async with sessions()() as session, session.begin():
            for row in rows:
                await session.execute(insert(table).values(**row))

    asyncio.run(write())


def posting(*, subject="test-subject", stakeholder="do.incharge", office=OFFICE):
    write_rows(office_staff, {"subject": subject, "stakeholder": stakeholder, "office_id": office})


def claim_fact(claim_id, *, days_ago=0, office=OFFICE, **values):
    return {"claim_id": claim_id, "office_id": office, "form_type": "19", "amount_paise": 10000,
            "route": "REVIEW", "submitted_at": datetime.combine(AS_OF - timedelta(days=days_ago),
                                                                    datetime.min.time(), tzinfo=UTC), **values}


def grievance_fact(grievance_id, *, office=OFFICE, resolved=None, within_sla=None, escalations=0):
    return {"grievance_id": grievance_id, "office_id": office, "category": "OTHER", "tier": "RO",
            "registered_at": datetime(2026, 8, 1, tzinfo=UTC), "resolved_at": resolved,
            "within_sla": within_sla, "escalations": escalations}


def test_district_counts_are_scoped_to_posting_and_small_counts_stay_exact(compliance_data):
    posting()
    sla = baseline()["claims"]["settlement_sla_days"]
    write_rows(claim_facts,
               claim_fact("OLD-PENDING", days_ago=sla + 1, returned_count=2),
               claim_fact("SLA-BOUNDARY", days_ago=sla),
               claim_fact("NEW-PENDING", days_ago=1),
               claim_fact("APPROVED", days_ago=sla + 1, decision="APPROVED"),
               claim_fact("REJECTED", days_ago=sla + 1, decision="REJECTED"),
               claim_fact("SETTLED", days_ago=50, decision="APPROVED",
                          settled_at=datetime(2026, 9, 30, 23, 59, tzinfo=UTC), returned_count=1),
               claim_fact("CUTOFF", days_ago=50, decision="APPROVED",
                          settled_at=datetime(2026, 8, 31, tzinfo=UTC)),
               claim_fact("OLDER", days_ago=50, decision="APPROVED",
                          settled_at=datetime(2026, 8, 30, 23, 59, tzinfo=UTC)),
               claim_fact("OTHER-OFFICE", days_ago=100, office="RO-OTHER", returned_count=99))
    write_rows(grievance_facts,
               grievance_fact("OPEN"), grievance_fact("ESCALATED", escalations=3),
               grievance_fact("RESOLVED", resolved=datetime(2026, 9, 30, 23, 59, tzinfo=UTC),
                              within_sla=True, escalations=1),
               grievance_fact("CUTOFF", resolved=datetime(2026, 8, 31, tzinfo=UTC), within_sla=False),
               grievance_fact("OLDER", resolved=datetime(2026, 8, 30, tzinfo=UTC), within_sla=True),
               grievance_fact("OTHER-OFFICE", office="RO-OTHER", escalations=1))
    # A token's office claim cannot override the stored posting.
    response = compliance_data.get(DISTRICT_PATH, headers=hdr("do.incharge", "RO-OTHER"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["office_id"] == OFFICE and data["as_of"] == "2026-09-30"
    assert data["claims"] == {"pending": 3, "settled_last_30_days": 2,
                              "pending_over_sla": 1, "returned_payments": 3}
    assert data["grievances"] == {"open": 2, "resolved_last_30_days": 2,
                                  "resolved_within_sla_pct": None, "escalated_open": 1}
    assert data["establishments"] == {"with_filings": 4, "defaulting": 2,
                                      "paid_late_last_12_months": 2}
    assert "all are included for the single demo office" in data["note"]
    assert "small numbers are not shown" in data["note"]


@pytest.mark.parametrize("resolved_count, expected", [(0, None), (4, None), (5, 80)])
def test_district_sla_percentage_threshold_and_office_scope(ctx, resolved_count, expected):
    client, _ = ctx
    posting()
    for i in range(resolved_count):
        write_rows(grievance_facts, grievance_fact(f"RESOLVED-{i}",
                   resolved=datetime(2026, 8, 1, tzinfo=UTC), within_sla=i != 0))
    write_rows(grievance_facts, grievance_fact("OTHER", office="RO-OTHER",
               resolved=datetime(2026, 9, 29, tzinfo=UTC), within_sla=False))
    data = client.get(DISTRICT_PATH, headers=hdr("do.incharge")).json()["data"]
    assert data["grievances"]["resolved_within_sla_pct"] == expected
    assert data["grievances"]["resolved_last_30_days"] == 0
    assert data["claims"] == {"pending": 0, "settled_last_30_days": 0,
                              "pending_over_sla": 0, "returned_payments": 0}
    assert data["establishments"] == {"with_filings": 0, "defaulting": 0,
                                      "paid_late_last_12_months": 0}


def test_district_uses_policy_sla(ctx, monkeypatch):
    client, _ = ctx
    posting()
    monkeypatch.setattr(dashboard_routes, "baseline", lambda: {"claims": {"settlement_sla_days": 3}})
    write_rows(claim_facts, claim_fact("OVER", days_ago=4), claim_fact("BOUNDARY", days_ago=3))
    assert client.get(DISTRICT_PATH, headers=hdr("do.incharge")).json()["data"]["claims"]["pending_over_sla"] == 1


@pytest.mark.parametrize("posted_role", [None, "fo.oic"])
def test_district_requires_matching_posting(ctx, posted_role):
    client, _ = ctx
    if posted_role:
        posting(stakeholder=posted_role)
    # A posting for another subject and a claimed office grant no access.
    posting(subject="other-subject")
    response = client.get(DISTRICT_PATH, headers=hdr("do.incharge", OFFICE))
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/no-posting"


@pytest.mark.parametrize("stakeholder", ["employer.owner", "employer.operator", "employer.signatory"])
def test_employer_returns_alerts_and_counts_match_compliance(compliance_data, stakeholder):
    response = compliance_data.get(EMPLOYER_PATH, headers=employer_headers(stakeholder))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["establishment_id"] == "EST-DEFAULT" and data["as_of"] == "2026-09-30"
    assert data["returns"] == [
        {"wage_month": "2026-08", "status": "FILED_AND_PAID_ON_TIME", "due_date": "2026-09-15", "paid_on": "2026-09-15"},
        {"wage_month": "2026-07", "status": "PAID_LATE", "due_date": "2026-08-15", "paid_on": "2026-08-20"},
        {"wage_month": "2026-06", "status": "FILED_NOT_PAID", "due_date": "2026-07-15", "paid_on": None},
    ]
    assert data["alerts"] == [
        {"kind": "FILED_NOT_PAID", "message": "Challan for 2026-06 not paid", "link": "/employer/ecr#ecr-challans"},
        {"kind": "PAID_LATE", "message": "1 month(s) paid late in the last 12 — 14B/7Q demands may follow",
         "link": "/employer/returns#demands-heading"},
    ]
    summary = compliance_data.get("/api/v1/employers/me/compliance-summary",
                                  headers=employer_headers(stakeholder)).json()["data"]
    assert data["counts"] == summary["counts"] == {
        "FILED_AND_PAID_ON_TIME": 2, "PAID_LATE": 1, "FILED_NOT_PAID": 1, "NOT_FILED": 1}
    assert data["see_also"] == [
        {"label": "Member approvals", "link": "/employer/members#approvals-heading"},
        {"label": "KYC approvals", "link": "/employer/registration#kyc-approvals-heading"},
        {"label": "Missing details", "link": "/employer/registration#missing-heading"},
    ]
    assert "kept by member-service and shown on those pages" in data["note"]


def test_employer_latest_missing_return_and_each_unpaid_month_alert(ctx):
    client, _ = ctx
    insert_facts(fact("APR", "2026-04"), fact("JUN", "2026-06"),
                 fact("JUN-SUPPLEMENT", "2026-06"))
    data = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]
    assert [r["wage_month"] for r in data["returns"]] == ["2026-08", "2026-07", "2026-06"]
    assert data["alerts"] == [
        {"kind": "NOT_FILED", "message": "Return for 2026-08 not filed", "link": "/employer/ecr#ecr-returns"},
        {"kind": "FILED_NOT_PAID", "message": "Challan for 2026-06 not paid", "link": "/employer/ecr#ecr-challans"},
        {"kind": "FILED_NOT_PAID", "message": "Challan for 2026-04 not paid", "link": "/employer/ecr#ecr-challans"},
    ]


def test_paid_late_window_counts_months_and_keeps_full_compliance_counts(ctx):
    client, _ = ctx
    posting()
    insert_facts(
        fact("OLD-LATE", "2025-08", paid=datetime(2025, 9, 20, tzinfo=UTC)),
        fact("WINDOW-START", "2025-09", paid=datetime(2025, 10, 20, tzinfo=UTC)),
        fact("RECENT-LATE", "2026-08", paid=datetime(2026, 9, 20, tzinfo=UTC)),
        fact("SUPPLEMENT", "2026-08", paid=datetime(2026, 9, 21, tzinfo=UTC)),
        fact("VALIDATED", "2025-01", establishment="EST-VALIDATED", submitted=False),
        fact("UNKNOWN", None, establishment="EST-UNKNOWN"),
    )
    employer = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]
    assert employer["counts"]["PAID_LATE"] == 3
    late = next(a for a in employer["alerts"] if a["kind"] == "PAID_LATE")
    assert late["message"] == "2 month(s) paid late in the last 12 — 14B/7Q demands may follow"
    district = client.get(DISTRICT_PATH, headers=hdr("do.incharge")).json()["data"]
    assert district["establishments"] == {"with_filings": 3, "defaulting": 1,
                                          "paid_late_last_12_months": 2}


def test_employer_compliant_and_empty_histories_are_scoped(compliance_data):
    insert_facts(fact("VALIDATED", "2026-01", establishment="EST-VALIDATED", submitted=False),
                 fact("FUTURE", "2026-09", establishment="EST-FUTURE"))
    compliant = compliance_data.get(EMPLOYER_PATH, headers=employer_headers(
        establishment="EST-COMPLIANT")).json()["data"]
    assert compliant["alerts"] == []
    assert len(compliant["returns"]) == 2
    assert compliant["counts"]["FILED_AND_PAID_ON_TIME"] == 2
    for establishment in ("EST-EMPTY", "EST-VALIDATED", "EST-FUTURE"):
        data = compliance_data.get(EMPLOYER_PATH, headers=employer_headers(establishment=establishment)).json()["data"]
        assert data["returns"] == [] and data["alerts"] == []
        assert data["counts"] == dict.fromkeys(compliance_routes.STATUSES, 0)


def test_dashboard_due_today_is_excluded(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setattr(dashboard_routes, "today", lambda: date(2026, 2, 15))
    insert_facts(fact("NOV", "2025-11", paid=datetime(2025, 12, 15, tzinfo=UTC)),
                 fact("JAN", "2026-01"))
    data = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]
    assert data["as_of"] == "2026-02-15"
    assert [r["wage_month"] for r in data["returns"]] == ["2025-12", "2025-11"]
    assert data["alerts"] == [{"kind": "NOT_FILED", "message": "Return for 2025-12 not filed",
                               "link": "/employer/ecr#ecr-returns"}]


@pytest.mark.parametrize("stakeholder", ["employer.owner", "employer.operator", "employer.signatory"])
def test_employer_without_establishment_gets_problem(ctx, stakeholder):
    client, _ = ctx
    response = client.get(EMPLOYER_PATH, headers=employer_headers(stakeholder, establishment=None))
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/no-establishment"


@pytest.mark.parametrize("path, stakeholder", [
    (DISTRICT_PATH, "member"), (DISTRICT_PATH, "fo.oic"), (DISTRICT_PATH, "zo.acc"),
    (DISTRICT_PATH, "employer.owner"), (EMPLOYER_PATH, "member"), (EMPLOYER_PATH, "do.incharge"),
])
def test_wrong_role_is_forbidden(ctx, path, stakeholder):
    client, _ = ctx
    posting()
    assert client.get(path, headers=employer_headers(stakeholder)).status_code == 403


@pytest.mark.parametrize("path", [DISTRICT_PATH, EMPLOYER_PATH])
def test_dashboards_require_authentication(ctx, path):
    client, _ = ctx
    assert client.get(path).status_code == 401


def test_office_posting_seed_is_idempotent_and_demo_incharge_can_read(ctx, monkeypatch):
    from app import seed
    from app.infra.db import sessions

    client, _ = ctx
    seed_path = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"
    monkeypatch.setattr(seed, "SEED_FILE", str(seed_path))
    asyncio.run(seed.main())

    async def count():
        async with sessions()() as session:
            return (await session.execute(select(func.count()).select_from(office_staff))).scalar_one()

    first_count = asyncio.run(count())
    asyncio.run(seed.main())
    assert asyncio.run(count()) == first_count > 0
    claims = jwt.decode(hdr("do.incharge")["Authorization"].split()[1], options={"verify_signature": False})
    claims["sub"] = "00000000-0000-4000-8000-000000000050"
    headers = {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}
    response = client.get(DISTRICT_PATH, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["office_id"] == OFFICE
