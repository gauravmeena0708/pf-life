"""Notification channel and delivery evidence tests (SQLite integration)."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update, text

from app.domain.notifications import deliver_due, handle_notification_requested
from app.infra.tables import (notification_deliveries, notification_delivery_attempts,
                              notification_preferences)
from tests.test_member_api import MEMBER_A, api, token  # noqa: F401


def event(template="CLAIM_SUBMITTED"):
    return {"event_id": str(uuid.uuid4()), "event_type": "NotificationRequested.v1",
            "payload": {"recipient_subject": MEMBER_A, "template": template, "reference_id": "REF-TEST"}}


def run(coro):
    return asyncio.run(coro)


async def create_notice(template="CLAIM_SUBMITTED"):
    from app.infra.db import sessions
    async with sessions()() as session, session.begin():
        await handle_notification_requested(session, event(template))
    async with sessions()() as session:
        return (await session.execute(select(notification_deliveries).order_by(
            notification_deliveries.c.created_at.desc()))).mappings().all()[-2:]


def test_preferences_and_essential_sms(api):
    path = "/api/v1/members/me/notification-preferences"
    response = api.put(path, headers=token(MEMBER_A), json={"sms": False, "email": False, "language": "hi"})
    assert response.status_code == 200
    assert "दावे का भुगतान" in response.json()["data"]["essential_sms_titles"]
    assert api.get(path, headers=token(MEMBER_A)).json()["data"]["language"] == "hi"
    run(create_notice())
    run(create_notice("CLAIM_SETTLED"))
    notices = api.get("/api/v1/members/me/notifications", headers=token(MEMBER_A)).json()["data"]
    ordinary = next(n for n in notices if n["template"] == "CLAIM_SUBMITTED")
    essential = next(n for n in notices if n["template"] == "CLAIM_SETTLED")
    assert {d["state"] for d in ordinary["deliveries"]} == {"SKIPPED"}
    assert next(d for d in essential["deliveries"] if d["channel"] == "SMS")["state"] == "QUEUED"
    assert next(d for d in essential["deliveries"] if d["channel"] == "EMAIL")["state"] == "SKIPPED"
    assert "दाव" in essential["title"]                   # दावा / दावे (claim), inflected


def test_worker_retry_schedule_failure_and_attempts(api):
    rows = run(create_notice())
    sms = next(row for row in rows if row["channel"] == "SMS")
    from app.infra.db import sessions
    now = datetime.now(UTC) + timedelta(seconds=1)

    async def unavailable(channel, payload):
        return httpx.Response(503, json={"status": "UNAVAILABLE"})

    async def work(at):
        async with sessions()() as session, session.begin():
            await deliver_due(session, at, unavailable)
        async with sessions()() as session:
            row = (await session.execute(select(notification_deliveries).where(
                notification_deliveries.c.delivery_id == sms["delivery_id"]))).mappings().one()
            evidence = (await session.execute(select(notification_delivery_attempts).where(
                notification_delivery_attempts.c.delivery_id == sms["delivery_id"]))).mappings().all()
            return row, evidence

    for number, delay in enumerate((1, 5, 30), 1):
        row, evidence = run(work(now))
        assert row["state"] == "RETRYING" and len(evidence) == number
        assert abs((row["next_attempt_at"].replace(tzinfo=UTC) - now).total_seconds() - delay * 60) < 1
        now += timedelta(minutes=delay)
    row, evidence = run(work(now))
    assert row["state"] == "FAILED" and row["attempts"] == len(evidence) == 4
    assert row["reason"] == "gateway unavailable after 4 attempts"

    async def failure_event():
        async with sessions()() as session:
            return (await session.execute(text("SELECT event_type FROM outbox WHERE event_type = 'NotificationDeliveryFailed.v1'"))).all()
    assert run(failure_event())

    office = api.get("/api/v1/office/notification-deliveries?state=FAILED",
                     headers=token("00000000-0000-4000-8000-000000000012", "fo.pro"))
    assert office.status_code == 200
    assert any(d["delivery_id"] == sms["delivery_id"] and len(d["attempts_evidence"]) == 4
               for d in office.json()["data"])
    retry = api.post(f"/api/v1/office/notification-deliveries/{sms['delivery_id']}/retries",
                     headers=token("00000000-0000-4000-8000-000000000012", "fo.pro"))
    assert retry.status_code == 200 and retry.json()["data"]["attempts"] == 4
    assert api.post(f"/api/v1/office/notification-deliveries/{sms['delivery_id']}/retries",
                    headers=token("00000000-0000-4000-8000-000000000012", "fo.pro")).status_code == 409


def test_delivered_bounced_and_office_scope(api):
    rows = run(create_notice())
    sms = next(row for row in rows if row["channel"] == "SMS")
    email = next(row for row in rows if row["channel"] == "EMAIL")
    from app.infra.db import sessions

    async def transport(channel, payload):
        if channel == "EMAIL":
            return httpx.Response(422, json={"status": "BOUNCED"})
        return httpx.Response(202, json={"status": "DELIVERED", "message_id": "MSG-1"})

    async def work():
        async with sessions()() as session, session.begin():
            await deliver_due(session, datetime.now(UTC) + timedelta(seconds=1), transport)
        async with sessions()() as session:
            return (await session.execute(select(notification_deliveries).where(
                notification_deliveries.c.delivery_id.in_([sms["delivery_id"], email["delivery_id"]])))).mappings().all()

    result = {row["channel"]: row for row in run(work())}
    assert result["SMS"]["state"] == "DELIVERED" and result["SMS"]["gateway_message_id"] == "MSG-1"
    assert result["EMAIL"]["state"] == "FAILED" and result["EMAIL"]["reason"] == "BOUNCED"

    async def move_office():
        async with sessions()() as session, session.begin():
            await session.execute(update(notification_deliveries).where(
                notification_deliveries.c.delivery_id == email["delivery_id"]).values(office_id="RO-OTHER"))
    run(move_office())
    path = "/api/v1/office/notification-deliveries"
    pro = api.get(path, headers=token("00000000-0000-4000-8000-000000000012", "fo.pro"))
    ho = api.get(path, headers=token("ho-test", "ho.is"))
    assert pro.status_code == ho.status_code == 200
    assert email["delivery_id"] not in {d["delivery_id"] for d in pro.json()["data"]}
    assert email["delivery_id"] in {d["delivery_id"] for d in ho.json()["data"]}
    assert api.post(f"{path}/{email['delivery_id']}/retries",
                    headers=token("00000000-0000-4000-8000-000000000012", "fo.pro")).status_code == 404


def test_a_notice_for_a_member_without_a_login_is_skipped_not_retried(api):
    """A Joint Declaration notice for a member who has no login names no recipient: it was matched to some other
    member without a login, failed on insert and was dead-lettered after five tries. It is skipped."""
    from app.infra.db import sessions
    from app.infra.tables import notifications

    async def deliver():
        async with sessions()() as session, session.begin():
            await handle_notification_requested(session, {"event_id": str(uuid.uuid4()), "event_type": "NotificationRequested.v1",
                                                          "payload": {"recipient_subject": None, "template": "JD_EMPLOYER_ATTESTED",
                                                                      "reference_id": "CASE-X", "params": {}}})
        async with sessions()() as session:
            return (await session.execute(select(notifications).where(notifications.c.reference_id == "CASE-X"))).all()
    assert run(deliver()) == []
