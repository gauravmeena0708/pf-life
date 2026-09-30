"""Compliance reads use synthetic contribution facts and the caller's establishment."""
import asyncio
from datetime import UTC, date, datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import insert

from app.api import compliance_routes
from app.infra.tables import contribution_facts
from tests.conftest import KEY, KID
from tests.test_read_models import ctx, hdr

OFFICE_PATH = "/api/v1/office/compliance/defaulters"
EMPLOYER_PATH = "/api/v1/employers/me/compliance-summary"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(compliance_routes, "today", lambda: date(2026, 9, 30))


def employer_headers(stakeholder="employer.owner", establishment="EST-DEFAULT"):
    headers = hdr(stakeholder)
    claims = jwt.decode(headers["Authorization"].split()[1], options={"verify_signature": False})
    if establishment is not None:
        claims["establishment_id"] = establishment
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def fact(filing_id, month, *, establishment="EST-DEFAULT", total=10000, paid=None,
         submitted=True):
    return {"filing_id": filing_id, "establishment_id": establishment, "wage_month": month,
            "total_paise": total, "submitted_at": datetime(2026, 1, 1, tzinfo=UTC) if submitted else None,
            "paid_at": paid}


def insert_facts(*rows):
    from app.infra.db import sessions

    async def write():
        async with sessions()() as session:
            await session.execute(insert(contribution_facts), list(rows))
            await session.commit()

    asyncio.run(write())


@pytest.fixture
def compliance_data(ctx):
    insert_facts(
        fact("D-APR", "2026-04", paid=datetime(2026, 5, 15, tzinfo=UTC)),
        # May is missing, June unpaid, July late, August paid on its due date.
        fact("D-JUN", "2026-06", total=12000),
        fact("D-JUN-SUPPLEMENT", "2026-06", total=3000),
        fact("D-JUL", "2026-07", total=20000, paid=datetime(2026, 8, 20, tzinfo=UTC)),
        fact("D-AUG", "2026-08", paid=datetime(2026, 9, 15, 23, 59, tzinfo=UTC)),
        fact("D-SEP", "2026-09", total=999999),  # Not overdue yet.
        fact("OK-JUL", "2026-07", establishment="EST-COMPLIANT",
             paid=datetime(2026, 8, 15, tzinfo=UTC)),
        fact("OK-AUG", "2026-08", establishment="EST-COMPLIANT",
             paid=datetime(2026, 9, 14, tzinfo=UTC)),
        fact("EARLIER-APR", "2026-04", establishment="EST-EARLIER", total=2000),
        fact("LATE-AUG", "2026-08", establishment="EST-LATE-ONLY",
             paid=datetime(2026, 9, 20, tzinfo=UTC)),
    )
    return ctx[0]


@pytest.mark.parametrize("stakeholder", ["fo.da_compliance", "fo.apfc", "fo.oic"])
def test_defaulters_missing_unpaid_late_and_compliant(compliance_data, stakeholder):
    response = compliance_data.get(OFFICE_PATH, headers=hdr(stakeholder))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["as_of"] == "2026-09-30"
    assert [row["establishment_id"] for row in data["defaulters"]] == ["EST-EARLIER", "EST-DEFAULT"]
    assert data["defaulters"][0]["since"] == "2026-04"
    assert data["defaulters"][1] == {
        "establishment_id": "EST-DEFAULT", "non_filing_months": ["2026-05"],
        "non_payment_months": ["2026-06"], "unpaid_paise": 15000,
        "late_payment_months": [{"wage_month": "2026-07", "days_late": 5}], "since": "2026-05",
    }
    assert data["note"] == (
        "Illustrative detection from filings and payments; the office verifies before opening a case.")


@pytest.mark.parametrize("stakeholder", ["employer.owner", "employer.operator", "employer.signatory"])
def test_employer_summary_is_scoped_and_newest_first(compliance_data, stakeholder):
    response = compliance_data.get(EMPLOYER_PATH, headers=employer_headers(stakeholder))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["establishment_id"] == "EST-DEFAULT"
    assert data["as_of"] == "2026-09-30"
    assert data["months"] == [
        {"wage_month": "2026-08", "due_date": "2026-09-15", "status": "FILED_AND_PAID_ON_TIME",
         "paid_on": "2026-09-15", "days_late": 0, "total_paise": 10000},
        {"wage_month": "2026-07", "due_date": "2026-08-15", "status": "PAID_LATE",
         "paid_on": "2026-08-20", "days_late": 5, "total_paise": 20000},
        {"wage_month": "2026-06", "due_date": "2026-07-15", "status": "FILED_NOT_PAID",
         "paid_on": None, "days_late": 0, "total_paise": 15000},
        {"wage_month": "2026-05", "due_date": "2026-06-15", "status": "NOT_FILED",
         "paid_on": None, "days_late": 0, "total_paise": 0},
        {"wage_month": "2026-04", "due_date": "2026-05-15", "status": "FILED_AND_PAID_ON_TIME",
         "paid_on": "2026-05-15", "days_late": 0, "total_paise": 10000},
    ]
    assert data["counts"] == {"FILED_AND_PAID_ON_TIME": 2, "PAID_LATE": 1,
                              "FILED_NOT_PAID": 1, "NOT_FILED": 1}
    compliant = compliance_data.get(EMPLOYER_PATH, headers=employer_headers(
        establishment="EST-COMPLIANT")).json()["data"]
    assert compliant["establishment_id"] == "EST-COMPLIANT"
    assert compliant["counts"] == {"FILED_AND_PAID_ON_TIME": 2, "PAID_LATE": 0,
                                   "FILED_NOT_PAID": 0, "NOT_FILED": 0}


def test_supplementary_filings_use_earliest_payment_and_sum_unpaid_rows(ctx):
    client, _ = ctx
    insert_facts(
        fact("JUL-FIRST", "2026-07", total=1000, paid=datetime(2026, 8, 15, tzinfo=UTC)),
        fact("JUL-LATE", "2026-07", total=2000, paid=datetime(2026, 8, 22, tzinfo=UTC)),
        fact("JUL-UNPAID", "2026-07", total=3000),
        fact("AUG-UNPAID", "2026-08", total=4000),
    )
    data = client.get(OFFICE_PATH, headers=hdr("fo.oic")).json()["data"]["defaulters"][0]
    assert data["non_filing_months"] == []
    assert data["non_payment_months"] == ["2026-08"]
    assert data["late_payment_months"] == []
    assert data["unpaid_paise"] == 7000
    months = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]["months"]
    assert months[1]["status"] == "FILED_AND_PAID_ON_TIME"
    assert months[1]["paid_on"] == "2026-08-15"
    assert months[1]["total_paise"] == 6000


def test_history_starts_at_first_submitted_or_paid_month(ctx):
    client, _ = ctx
    insert_facts(
        fact("VALIDATED", "2026-01", submitted=False, total=None),
        fact("UNKNOWN-MONTH", None),
        fact("PAID", "2026-07", submitted=False, paid=datetime(2026, 8, 16, tzinfo=UTC)),
    )
    months = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]["months"]
    assert [month["wage_month"] for month in months] == ["2026-08", "2026-07"]
    assert [month["status"] for month in months] == ["NOT_FILED", "PAID_LATE"]


def test_due_today_is_excluded_and_months_cross_year_boundary(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setattr(compliance_routes, "today", lambda: date(2026, 2, 15))
    insert_facts(fact("NOV", "2025-11", paid=datetime(2025, 12, 15, tzinfo=UTC)),
                 fact("JAN", "2026-01"))
    months = client.get(EMPLOYER_PATH, headers=employer_headers()).json()["data"]["months"]
    assert [month["wage_month"] for month in months] == ["2025-12", "2025-11"]
    assert months[0]["due_date"] == "2026-01-15"
    assert months[0]["status"] == "NOT_FILED"


def test_paid_date_is_evaluated_in_utc():
    # SQLite removes timezone information, so evaluate an aware payment directly.
    row = fact("UTC", "2026-08", paid=datetime(2026, 9, 16, 0, 30,
                                               tzinfo=timezone(timedelta(hours=2))))
    months, _ = compliance_routes._evaluate([row], date(2026, 9, 30))
    assert months[0]["paid_on"] == "2026-09-15"
    assert months[0]["status"] == "FILED_AND_PAID_ON_TIME"


def test_no_history_returns_empty_reads(ctx):
    client, _ = ctx
    insert_facts(fact("VALIDATED", "2026-01", submitted=False, total=None),
                 fact("NOT-DUE", "2026-09", establishment="EST-NOT-DUE"))
    assert client.get(OFFICE_PATH, headers=hdr("fo.oic")).json()["data"]["defaulters"] == []
    for establishment in ["EST-DEFAULT", "EST-NOT-DUE", "EST-EMPTY"]:
        data = client.get(EMPLOYER_PATH, headers=employer_headers(
            establishment=establishment)).json()["data"]
        assert data["establishment_id"] == establishment
        assert data["months"] == []
        assert data["counts"] == dict.fromkeys(compliance_routes.STATUSES, 0)


def test_employer_without_establishment_gets_problem(ctx):
    client, _ = ctx
    response = client.get(EMPLOYER_PATH, headers=employer_headers(establishment=None))
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/no-establishment"


@pytest.mark.parametrize("path", [OFFICE_PATH, EMPLOYER_PATH])
def test_member_role_is_forbidden(ctx, path):
    client, _ = ctx
    assert client.get(path, headers=hdr("member")).status_code == 403
