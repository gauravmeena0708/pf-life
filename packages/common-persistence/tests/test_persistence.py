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
