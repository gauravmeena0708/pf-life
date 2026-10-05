"""Unit tests on SQLite (the relay's FOR UPDATE SKIP LOCKED is exercised against PostgreSQL in e2e)."""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from epfo_persistence import IdempotencyConflict, add_event, audit, envelope, find_response, request_hash, routing_key, store_response
from epfo_persistence.consumer import apply_once

DDL = [
    "CREATE TABLE outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE, event_type TEXT, aggregate_type TEXT, aggregate_id TEXT, payload JSON, correlation_id TEXT, created_at TEXT, published_at TEXT, attempts INTEGER DEFAULT 0)",
    "CREATE TABLE inbox (event_id TEXT PRIMARY KEY, event_type TEXT, received_at TEXT)",
    "CREATE TABLE idempotency_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_subject TEXT, operation TEXT, key TEXT, request_hash TEXT, response_status INTEGER, response_body JSON, created_at TEXT, UNIQUE(actor_subject, operation, key))",
    "CREATE TABLE audit_local (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor_subject TEXT, actor_stakeholder TEXT, action TEXT, target_type TEXT, target_id TEXT, correlation_id TEXT, detail TEXT)",
    "CREATE TABLE applied (event_id TEXT)",
]


@pytest.fixture
def separate_sessions(tmp_path):
    """A file database where each session has its own connection, as on Postgres: concurrent transactions do not commit
    each other's work (the in-memory fixture shares one connection)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/c.db")

    async def setup():
        async with engine.begin() as conn:
            for ddl in DDL:
                await conn.execute(text(ddl))
    asyncio.run(setup())
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def setup():
        async with engine.begin() as conn:
            for ddl in DDL:
                await conn.execute(text(ddl))
    asyncio.run(setup())
    return async_sessionmaker(engine, expire_on_commit=False)


def run(coro):
    return asyncio.run(coro)


def test_envelope_matches_contract_shape():
    e = envelope(producer="contribution-service", event_type="ContributionPosted.v1", aggregate_type="ledger_journal",
                 aggregate_id="J1", payload={"x": 1}, correlation_id="c")
    assert set(e) >= {"event_id", "event_type", "schema_version", "aggregate_type", "aggregate_id", "producer",
                      "occurred_at", "correlation_id", "payload"}
    assert e["occurred_at"].endswith("Z") and e["schema_version"] == 1
    assert routing_key("payment-simulator", "PaymentConfirmed.v1") == "payment-simulator.PaymentConfirmed.v1"


def test_envelope_requires_version():
    with pytest.raises(ValueError):
        envelope(producer="p", event_type="NoVersion", aggregate_type="a", aggregate_id="1", payload={}, correlation_id="c")


def test_outbox_row_written_in_callers_transaction(sessions, monkeypatch):
    import epfo_persistence.contracts as contracts
    monkeypatch.setattr(contracts, "_validator", lambda event_type: None)    # X.v1 is a made-up event with no contract

    async def go():
        async with sessions() as s:
            async with s.begin():
                await add_event(s, producer="p", event_type="X.v1", aggregate_type="a", aggregate_id="1", payload={})
                raise_rollback = True
            async with s.begin():
                count = (await s.execute(text("SELECT count(*) FROM outbox"))).scalar()
        return count
    assert run(go()) == 1


def test_consumer_applies_each_event_once(sessions):
    event = envelope(producer="p", event_type="X.v1", aggregate_type="a", aggregate_id="1", payload={}, correlation_id="c")

    async def handler(session, e):
        await session.execute(text("INSERT INTO applied (event_id) VALUES (:e)"), {"e": e["event_id"]})

    async def go():
        first = await apply_once(sessions, event, handler)
        second = await apply_once(sessions, event, handler)
        async with sessions() as s:
            n = (await s.execute(text("SELECT count(*) FROM applied"))).scalar()
        return first, second, n
    assert run(go()) == (True, False, 1)


def test_handler_failure_rolls_back_inbox(sessions):
    event = envelope(producer="p", event_type="X.v1", aggregate_type="a", aggregate_id="1", payload={}, correlation_id="c")

    async def failing(session, e):
        raise RuntimeError("boom")

    async def ok(session, e):
        await session.execute(text("INSERT INTO applied (event_id) VALUES (:e)"), {"e": e["event_id"]})

    async def go():
        with pytest.raises(RuntimeError):
            await apply_once(sessions, event, failing)
        return await apply_once(sessions, event, ok)  # retry succeeds: inbox row was rolled back
    assert run(go()) is True


def test_idempotency_returns_original_and_rejects_different_body(sessions):
    async def go():
        async with sessions() as s:
            async with s.begin():
                h = request_hash({"a": 1})
                assert await find_response(s, "u", "op", "k1", h) is None
                await store_response(s, "u", "op", "k1", h, 201, {"id": "F1"})
            async with s.begin():
                stored = await find_response(s, "u", "op", "k1", h)
                assert stored.status == 201 and stored.body == {"id": "F1"}
                with pytest.raises(IdempotencyConflict):
                    await find_response(s, "u", "op", "k1", request_hash({"a": 2}))
    run(go())


def test_audit_row(sessions):
    async def go():
        async with sessions() as s:
            async with s.begin():
                await audit(s, actor_subject="u", actor_stakeholder="member", action="X", target_type="t", target_id="1")
            async with s.begin():
                return (await s.execute(text("SELECT action FROM audit_local"))).scalar()
    assert run(go()) == "X"


class _Message:
    """Enough of an aio_pika message for the consumer: a body, ack and reject."""
    def __init__(self, event):
        self.body, self.headers, self.outcome = __import__("json").dumps(event).encode(), {}, None

    async def ack(self):
        self.outcome = "ack"

    async def reject(self, requeue=False):
        self.outcome = "dead-letter"


def test_same_record_events_apply_in_arrival_order_even_when_the_first_fails_once(separate_sessions, monkeypatch):
    """P2.30 — CI's bug: a new demand's OPEN and WITHDRAWN events handled at once; OPEN failed, was re-queued behind
    WITHDRAWN and applied last, leaving the copy OPEN. Now the same record's events wait their turn and a failure is
    retried in place; another record's event does not wait."""
    from epfo_persistence import consumer as c
    real_sleep = asyncio.sleep
    monkeypatch.setattr(c.asyncio, "sleep", lambda *_: real_sleep(0))
    order, failed_once = [], set()
    opened = envelope(producer="contribution", event_type="DemandStateChanged.v1", aggregate_type="demand", aggregate_id="D1",
                      payload={"state": "OPEN"}, correlation_id="c")
    withdrawn = envelope(producer="contribution", event_type="DemandStateChanged.v1", aggregate_type="demand", aggregate_id="D1",
                         payload={"state": "WITHDRAWN"}, correlation_id="c")
    other = envelope(producer="contribution", event_type="DemandStateChanged.v1", aggregate_type="demand", aggregate_id="D2",
                     payload={"state": "OPEN"}, correlation_id="c")

    async def handler(session, e):
        if e["event_id"] == opened["event_id"] and e["event_id"] not in failed_once:
            failed_once.add(e["event_id"])
            await asyncio.sleep(0)
            raise RuntimeError("insert collided")              # what happened on CI
        order.append((e["aggregate_id"], e["payload"]["state"]))

    consumer = c.Consumer.__new__(c.Consumer)
    consumer.queue_name, consumer.handler, consumer.sessions, consumer._locks, consumer._holders = "q", handler, separate_sessions, {}, {}
    messages = [_Message(opened), _Message(withdrawn), _Message(other)]

    async def go():
        await asyncio.gather(*(consumer._on_message(m) for m in messages))
    run(go())
    d1 = [state for agg, state in order if agg == "D1"]
    assert d1 == ["OPEN", "WITHDRAWN"]                          # the later state is applied last
    assert ("D2", "OPEN") in order and order.index(("D2", "OPEN")) < order.index(("D1", "OPEN"))   # D2 did not wait for D1's retry
    assert [m.outcome for m in messages] == ["ack", "ack", "ack"] and not consumer._locks       # locks forgotten once idle


def test_an_event_failing_every_time_goes_to_the_dead_letter_queue(sessions, monkeypatch):
    from epfo_persistence import consumer as c
    real_sleep = asyncio.sleep
    monkeypatch.setattr(c.asyncio, "sleep", lambda *_: real_sleep(0))
    event = envelope(producer="p", event_type="X.v1", aggregate_type="a", aggregate_id="9", payload={}, correlation_id="c")

    async def failing(session, e):
        raise RuntimeError("always")
    consumer = c.Consumer.__new__(c.Consumer)
    consumer.queue_name, consumer.handler, consumer.sessions, consumer._locks, consumer._holders = "q", failing, sessions, {}, {}
    m = _Message(event)
    run(consumer._on_message(m))
    assert m.outcome == "dead-letter"
