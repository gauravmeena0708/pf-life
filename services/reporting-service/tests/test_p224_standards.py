"""Published standards use event-built facts and protect small public groups."""
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert

from app.domain.standards import performance
from app.domain.standards import CHARTER_STANDARDS
from app.infra.tables import claim_facts, grievance_facts, service_standards
from tests.test_read_models import ctx, hdr

URL = "/api/v1/public/service-standards"
NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


def test_completion_cohort_boundary_percentile_and_overdue_open():
    rows = [{"submitted_at": NOW - timedelta(days=duration),
             "settled_at": NOW - timedelta(days=1)} for duration in range(2, 12)]
    rows.append({"submitted_at": NOW - timedelta(days=22), "settled_at": None})
    result = performance(rows, start_field="submitted_at", end_field="settled_at",
                         days=5, as_of=NOW, period_days=30)
    assert result == {"completed": 10, "within_pct": 50, "median_days": 5.5,
                      "p90_days": 9, "open_past_standard": None, "met": False}


def test_fewer_than_ten_completed_cases_suppresses_all_metrics():
    rows = [{"submitted_at": NOW - timedelta(days=2), "settled_at": NOW} for _ in range(9)]
    rows.append({"submitted_at": NOW - timedelta(days=22), "settled_at": None})
    assert performance(rows, start_field="submitted_at", end_field="settled_at",
                       days=20, as_of=NOW, period_days=30) is None


def write(table, rows):
    from app.infra.db import sessions

    async def save():
        async with sessions()() as session, session.begin():
            await session.execute(insert(table), rows)

    asyncio.run(save())


def test_charter_lists_statutory_and_target_standards(ctx):
    client, _ = ctx
    write(service_standards, list(CHARTER_STANDARDS))
    response = client.get(URL, headers=hdr("public"))
    assert response.status_code == 200, response.text
    standards = {row["code"]: row for row in response.json()["data"]["standards"]}
    assert {code: (row["days"], row["basis"]) for code, row in standards.items()} == {
        "CLAIM_SETTLEMENT": (20, "STATUTORY"),
        "AUTO_CLAIM": (3, "TARGET"),
        "GRIEVANCE": (30, "TARGET"),
        "TRANSFER": (20, "TARGET"),
    }
    assert standards["TRANSFER"]["availability"] == "NO_READ_MODEL"
    assert all(row["performance"] is None for row in standards.values())


def test_per_office_period_performance_and_small_count_suppression(ctx, monkeypatch):
    from app.api import standards_routes

    client, _ = ctx
    monkeypatch.setattr(standards_routes, "now", lambda: NOW)
    write(service_standards, list(CHARTER_STANDARDS))
    claims = []
    for i in range(10):
        start = NOW - timedelta(days=20 if i < 9 else 25)
        claims.append({"claim_id": f"C{i}", "office_id": "RO-1", "route": "REVIEW",
                       "submitted_at": start, "settled_at": NOW - timedelta(days=10), "decision": "APPROVED"})
    claims[9]["settled_at"] = NOW - timedelta(days=2)
    claims.append({"claim_id": "OPEN", "office_id": "RO-1", "route": "REVIEW",
                   "submitted_at": NOW - timedelta(days=21), "settled_at": None})
    claims.append({"claim_id": "SMALL", "office_id": "RO-2", "route": "REVIEW",
                   "submitted_at": NOW - timedelta(days=22), "settled_at": NOW - timedelta(days=1)})
    claims.append({"claim_id": "OLD", "office_id": "RO-1", "route": "REVIEW",
                   "submitted_at": NOW - timedelta(days=60), "settled_at": NOW - timedelta(days=40)})
    claims.extend({"claim_id": f"AUTO-{i}", "office_id": "RO-3", "route": "AUTO",
                   "submitted_at": NOW - timedelta(days=2), "settled_at": NOW - timedelta(days=1)}
                  for i in range(10))
    write(claim_facts, [{"decision": None, **row} for row in claims])
    write(grievance_facts, [{"grievance_id": f"G{i}", "office_id": "RO-1", "category": "OTHER",
                             "tier": "RO", "registered_at": NOW - timedelta(days=40),
                             "resolved_at": NOW - timedelta(days=10) if i < 10 else None}
                            for i in range(11)])
    response = client.get(URL + "?days=30", headers=hdr("public"))
    assert response.status_code == 200, response.text
    offices = {row["office_id"]: row for row in response.json()["data"]["offices"]}
    claim = next(row for row in offices["RO-1"]["standards"] if row["code"] == "CLAIM_SETTLEMENT")
    assert claim["performance"]["completed"] == 10
    assert claim["performance"]["within_pct"] == 90
    assert claim["performance"]["open_past_standard"] is None
    assert claim["performance"]["median_days"] is not None
    assert claim["performance"]["p90_days"] is not None
    auto = next(row for row in offices["RO-3"]["standards"] if row["code"] == "AUTO_CLAIM")
    assert auto["performance"]["within_pct"] == 100 and auto["performance"]["met"] is True
    grievance = next(row for row in offices["RO-1"]["standards"] if row["code"] == "GRIEVANCE")
    assert grievance["performance"]["within_pct"] == 100
    small = next(row for row in offices["RO-2"]["standards"] if row["code"] == "CLAIM_SETTLEMENT")
    assert small["performance"] is None and small["availability"] == "SUPPRESSED"
    assert "SMALL" not in response.text and "C0" not in response.text
    filtered = client.get(URL + "?days=30&office_id=RO-2", headers=hdr("public")).json()["data"]
    assert [row["office_id"] for row in filtered["offices"]] == ["RO-2"]
