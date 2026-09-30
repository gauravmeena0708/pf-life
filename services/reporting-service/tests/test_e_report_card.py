"""The public report card shows the last twelve due wage months."""
from datetime import UTC, date, datetime

import jwt
import pytest

from app.api import compliance_routes
from tests.conftest import KEY, KID
from tests.test_compliance_reads import fact, insert_facts
from tests.test_read_models import ctx, hdr

URL = "/api/v1/public/establishments/EST-DEFAULT/e-report-card"


def public_headers():
    claims = jwt.decode(hdr("public")["Authorization"].split()[1], options={"verify_signature": False})
    claims["sub"] = "anonymous"
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(compliance_routes, "today", lambda: date(2026, 9, 30))


def test_report_card_limits_due_months_orders_newest_first_and_totals_paid_months(ctx):
    client, _ = ctx
    insert_facts(
        # Older paid history must be excluded from both counts and remittances.
        fact("OLD", "2025-07", total=999999, paid=datetime(2025, 8, 15, tzinfo=UTC)),
        fact("SEP", "2025-09", total=1100, paid=datetime(2025, 10, 15, tzinfo=UTC)),
        fact("APR", "2026-04", total=10000, paid=datetime(2026, 5, 15, tzinfo=UTC)),
        fact("JUN", "2026-06", total=12000),
        fact("JUN-SUPPLEMENT", "2026-06", total=3000),
        fact("JUL", "2026-07", total=20000, paid=datetime(2026, 8, 20, tzinfo=UTC)),
        fact("AUG", "2026-08", total=10000, paid=datetime(2026, 9, 15, 23, 59, tzinfo=UTC)),
        fact("NOT-DUE", "2026-09", total=888888),
        fact("OTHER-EST", "2026-08", establishment="EST-OTHER", total=777777,
             paid=datetime(2026, 9, 15, tzinfo=UTC)),
    )
    response = client.get(URL, headers=public_headers())
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["establishment_id"] == "EST-DEFAULT" and data["as_of"] == "2026-09-30"
    assert [m["wage_month"] for m in data["months"]] == [
        "2026-08", "2026-07", "2026-06", "2026-05", "2026-04", "2026-03",
        "2026-02", "2026-01", "2025-12", "2025-11", "2025-10", "2025-09",
    ]
    assert [m["status"] for m in data["months"][:4]] == [
        "FILED_AND_PAID_ON_TIME", "PAID_LATE", "FILED_NOT_PAID", "NOT_FILED",
    ]
    assert data["counts"] == {"FILED_AND_PAID_ON_TIME": 3, "PAID_LATE": 1,
                              "FILED_NOT_PAID": 1, "NOT_FILED": 7}
    assert data["remitted_paise"] == 41100
    assert all(set(m) == {"wage_month", "due_date", "status", "paid_on", "days_late"}
               for m in data["months"])


def test_unknown_establishment_has_no_report_card(ctx):
    client, _ = ctx
    insert_facts(fact("KNOWN", "2026-08"))
    response = client.get("/api/v1/public/establishments/EST-UNKNOWN/e-report-card", headers=public_headers())
    assert response.status_code == 404, response.text
