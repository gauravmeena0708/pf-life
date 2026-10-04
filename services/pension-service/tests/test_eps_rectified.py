"""P2.19c: a member ID found not eligible for EPS loses its pension service (HO circular WSU/2025/E-961539); credited back
when EPS was wrongly denied."""
import asyncio
import uuid
from datetime import date

from tests.test_pensioner_services import at
from tests.test_pensions import SUBJECTS, ctx, hdr  # noqa: F401
from tests.test_settlement import step

MEMBER_E = SUBJECTS["member-e"]                          # DEV DEMO, AL-0004: 15 years, left in January 2026


def rectified(scenario):
    from app.infra.db import sessions
    from app.infra.messaging import BINDINGS, dispatch
    from epfo_persistence.consumer import apply_once
    assert "contribution-service.EpsRectified.v1" in BINDINGS
    event = {"event_id": str(uuid.uuid4()), "event_type": "EpsRectified.v1", "producer": "contribution-service", "correlation_id": str(uuid.uuid4()),
             "payload": {"rectification_id": "EPSR-T", "uan": "100000000004", "account_link_id": "AL-0004", "scenario": scenario,
                         "from_month": "2014-09", "to_month": "2026-01", "months": 137, "amount_paise": 1, "interest_paise": 0, "exempted": False}}
    asyncio.run(apply_once(sessions(), event, dispatch))


def test_service_deleted_then_credited(ctx, monkeypatch):
    client, q, _ = ctx
    at(monkeypatch, date(2026, 9, 29))
    preview = lambda: client.get("/api/v1/members/me/pension-eligibility-preview", headers=hdr(MEMBER_E, "member")).json()["data"]  # noqa: E731
    before = preview()["service_months_so_far"]
    assert before > 120
    rectified("WRONGLY_ALLOWED")
    after = preview()
    [spell] = [x for x in after["service_by_member_id"] if x["account_link_id"] == "AL-0004"]
    assert spell["months"] == 0 and spell["eps_member"] is False and after["service_months_so_far"] < before
    r = step(client, "POST", "/api/v1/members/me/pension-applications", MEMBER_E, "member", {})
    assert r.status_code == 422 and "WSU/2025/E-961539" in r.json()["detail"]
    rectified("WRONGLY_DENIED")
    assert preview()["service_months_so_far"] == before
    assert q("SELECT eps_member FROM eps_accounts WHERE account_link_id='AL-0004'") in ([(1,)], [(True,)])
