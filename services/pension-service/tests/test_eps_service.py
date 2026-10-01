"""P2.9b: pension service adds up across a member's IDs — the union of the spells, less breaks — from the EPS
account each member ID keeps; new IDs and exits arrive by event."""
import asyncio
import uuid
from datetime import date

from app.api.routes import eps_service
from tests.test_pensions import SUBJECTS, ctx, hdr  # noqa: F401 (fixture)

DAY = date(2026, 10, 1)


def spell(acc, start, end=None, breaks=0):
    return {"account_link_id": acc, "establishment_id": "EST", "date_of_joining": date.fromisoformat(start),
            "date_of_exit": date.fromisoformat(end) if end else None, "breaks_months": breaks}


def test_spells_add_up_overlaps_count_once_and_breaks_are_taken_off():
    total, by_id = eps_service([spell("A", "2010-01-01", "2014-12-31"), spell("B", "2015-01-01", "2019-12-31"), spell("C", "2020-01-01")], DAY)
    assert [x["months"] for x in by_id] == [59, 59, 81] and total == 59 + 59 + 81
    total, _ = eps_service([spell("A", "2010-01-01", "2015-12-31"), spell("B", "2015-01-01", "2016-12-31")], DAY)   # a year of overlap
    assert total == 83
    total, _ = eps_service([spell("A", "2010-01-01", "2014-12-31", breaks=3)], DAY)
    assert total == 56


def test_the_estimate_counts_every_member_id_of_the_member(ctx):
    client, _, _ = ctx
    est = client.get("/api/v1/members/me/pension-eligibility-preview", headers=hdr(SUBJECTS["member-g"], "member")).json()["data"]
    ids = [x["account_link_id"] for x in est["service_by_member_id"]]
    assert ids == ["AL-0905", "AL-0906"], est                                       # the earlier job and the present one
    assert est["service_months_so_far"] >= 90                                      # 2018 onwards, not only since February 2026


def test_new_member_ids_and_exits_arrive_by_event(ctx):
    client, q, _ = ctx
    from app.infra.db import sessions
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once

    def deliver(event_type, payload):
        event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "producer": "member-service",
                 "correlation_id": str(uuid.uuid4()), "payload": payload}
        asyncio.run(apply_once(sessions(), event, dispatch))
    deliver("MemberRegistered.v1", {"uan": "100000000001", "account_link_id": "AL-NEW-1", "member_subject": None, "name": "ASHA DEMO",
                                    "date_of_birth": "1990-04-12", "gender": "FEMALE", "establishment_id": "EST-DEMO-0002",
                                    "date_of_joining": "2026-09-01", "new_uan": False, "pan_verified": True})
    deliver("MemberExitMarked.v1", {"uan": "100000000001", "account_link_id": "AL-0001", "date_of_exit": "2026-08-31", "reason": "CESSATION",
                                    "marked_by": "EMPLOYER"})
    rows = q("SELECT account_link_id, date_of_exit FROM eps_accounts WHERE uan='100000000001' ORDER BY account_link_id")
    assert [r[0] for r in rows] == ["AL-0001", "AL-NEW-1"] and str(rows[0][1]).startswith("2026-08-31")
    est = client.get("/api/v1/members/me/pension-eligibility-preview", headers=hdr(SUBJECTS["member-a"], "member")).json()["data"]
    assert [x["account_link_id"] for x in est["service_by_member_id"]] == ["AL-0001", "AL-NEW-1"]
