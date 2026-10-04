"""P2.21b: a death on record (here from the civil registry) stops the member's own pension and lets the family apply."""
import asyncio
import uuid

from tests.test_pensions import SUBJECTS, ctx, hdr  # noqa: F401


def deliver(payload):
    from app.infra.db import sessions
    from app.infra.messaging import BINDINGS, dispatch
    from epfo_persistence.consumer import apply_once
    assert "member-service.MemberDeathRecorded.v1" in BINDINGS
    event = {"event_id": str(uuid.uuid4()), "event_type": "MemberDeathRecorded.v1", "producer": "member-service",
             "correlation_id": str(uuid.uuid4()), "payload": payload}
    asyncio.run(apply_once(sessions(), event, dispatch))


def test_family_may_apply_once_the_registry_reports_the_death(ctx):
    client, q, _ = ctx
    meena = hdr(SUBJECTS["claimant-b"], "claimant", {"action": "file-family-pension", "resource_id": "100000000916"})
    body = {"form_type": "FORM_10D", "deceased_uan": "100000000916"}
    assert client.post("/api/v1/claimants/family-pension-applications", json=body, headers=meena).status_code == 422   # not recorded yet
    deliver({"uan": "100000000916", "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY", "registration_no": "D-2026-DL-0001"})
    deliver({"uan": "100000000916", "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY", "registration_no": "D-2026-DL-0001"})
    r = client.post("/api/v1/claimants/family-pension-applications", json=body, headers=meena)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["pension_from"] == "2026-10-01" and r.json()["data"]["estimate"]["monthly_paise"] > 0


def test_a_pension_stops_on_the_pensioners_own_death_only(ctx):
    _, q, _ = ctx
    # GOPAL DEMO's pension (PPO-DEMO-0001) is on UAN 100000000901, which is also GANESH DEMO's (born on another day):
    # GANESH's death must not stop it
    deliver({"uan": "100000000901", "date_of_death": "2026-07-15", "source": "EMPLOYER", "registration_no": None})
    assert q("SELECT status FROM pensioners WHERE ppo_id='PPO-DEMO-0001'") == [("IN_PAYMENT",)]
    async def own_record():                                  # now the member record is GOPAL's own
        from sqlalchemy import text
        from app.infra.db import sessions
        async with sessions()() as session, session.begin():
            await session.execute(text("UPDATE member_service SET date_of_birth='1965-05-10' WHERE uan='100000000901'"))
    asyncio.run(own_record())
    deliver({"uan": "100000000901", "date_of_death": "2026-09-30", "source": "CIVIL_REGISTRY", "registration_no": "D-2026-DL-0042"})
    [(status, reason)] = q("SELECT status, status_reason FROM pensioners WHERE ppo_id='PPO-DEMO-0001'")
    assert status == "STOPPED" and "civil registry (registration D-2026-DL-0042)" in reason and "recovered" in reason
