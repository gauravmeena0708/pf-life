"""Pension estimates label each PF spell from its own end date."""
import asyncio
import uuid

from tests.test_pensions import ctx, hdr  # noqa: F401


def test_exemption_event_reseed_and_spell_dates(ctx):
    client, q, _ = ctx
    from app.infra.db import sessions
    from app.infra.messaging import BINDINGS, dispatch
    from app.seed import main as seed
    from epfo_persistence.consumer import apply_once
    assert "employer-service.ExemptionStatusChanged.v1" in BINDINGS
    payload = {"establishment_id": "EST-DEMO-0004", "status": "CANCELLED",
               "ended_on": "2026-07-01", "past_accumulations_due": "2026-08-01"}

    def deliver():
        event = {"event_id": str(uuid.uuid4()), "event_type": "ExemptionStatusChanged.v1",
                 "producer": "employer-service", "correlation_id": str(uuid.uuid4()), "payload": payload}
        asyncio.run(apply_once(sessions(), event, dispatch))

    deliver()
    deliver()
    asyncio.run(seed())
    assert q("SELECT status,ended_on FROM exempted_establishments WHERE establishment_id='EST-DEMO-0004'") == [
        ("CANCELLED", "2026-07-01")]
    from tests.test_pensions import SUBJECTS
    priya = client.get("/api/v1/members/me/pension-eligibility-preview",
                       headers=hdr(SUBJECTS["member-p"], "member"))
    ravi = client.get("/api/v1/members/me/pension-eligibility-preview",
                      headers=hdr(SUBJECTS["member-r"], "member"))
    assert priya.status_code == ravi.status_code == 200
    assert next(s for s in priya.json()["data"]["service_by_member_id"] if s["account_link_id"] == "AL-0915")["pf_with"] == "EPFO"
    assert next(s for s in ravi.json()["data"]["service_by_member_id"] if s["account_link_id"] == "AL-0918")["pf_with"].startswith("TRUST ")


def test_status_column_holds_every_exemption_status():
    """SQLite does not enforce VARCHAR lengths; Postgres does (UNEXEMPTED_COMPLIANCE once broke this copy's consumer)."""
    from app.infra.tables import exempted_establishments
    assert exempted_establishments.c.status.type.length >= max(map(len, ("ACTIVE", "UNEXEMPTED_COMPLIANCE", "SURRENDERED", "CANCELLED")))
