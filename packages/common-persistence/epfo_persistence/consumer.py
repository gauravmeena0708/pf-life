"""Idempotent event consumer: one durable queue per consumer, dead-letter after retries.

The handler runs in one database transaction together with the inbox insert, so an event is applied
exactly once even though RabbitMQ delivers at least once.

Order (P2.30): up to ten messages are handled at once, but events about the same record — the same aggregate — are
applied one after another in the order they arrived (a first-in-first-out lock per aggregate), and a failed event is
retried in place rather than re-queued behind later ones. A producer publishes its outbox in order, so a copy kept from
one producer's events sees them in the order they happened.
"""
import asyncio
import json
from typing import Any, Awaitable, Callable

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from epfo_observability import get_logger

from .events import DLX, EXCHANGE

log = get_logger("consumer")
Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]
MAX_ATTEMPTS = 5
_INBOX = text("INSERT INTO inbox (event_id, event_type) VALUES (:event_id, :event_type) ON CONFLICT DO NOTHING")


async def apply_once(sessions: async_sessionmaker, event: dict[str, Any], handler: Handler) -> bool:
    """Run `handler` for `event` unless its event_id was already processed. Returns True if applied."""
    async with sessions() as session:
        async with session.begin():
            inserted = (await session.execute(_INBOX, {"event_id": event["event_id"], "event_type": event["event_type"]})).rowcount
            if not inserted:
                return False
            await handler(session, event)
    return True


def order_key(event: dict[str, Any]) -> str:
    """The record an event is about: its aggregate (an event without one is ordered by nothing but itself)."""
    if event.get("aggregate_id"):
        return f"{event.get('aggregate_type', '')}:{event['aggregate_id']}"
    return f"event:{event.get('event_id')}"


class Consumer:
    def __init__(self, engine: AsyncEngine, rabbitmq_url: str, queue: str, bindings: list[str], handler: Handler) -> None:
        self.url, self.queue_name, self.bindings, self.handler = rabbitmq_url, queue, bindings, handler
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._task: asyncio.Task | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, int] = {}

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        self._holders[key] = self._holders.get(key, 0) + 1
        return lock

    def _release(self, key: str) -> None:
        self._holders[key] -= 1
        if not self._holders[key]:                       # nobody waiting: forget the lock
            del self._holders[key], self._locks[key]

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        try:
            event = json.loads(message.body)
        except (ValueError, TypeError):
            log.exception("event_unreadable", queue=self.queue_name)
            await message.reject(requeue=False)          # -> dead-letter queue
            return
        key = order_key(event)
        lock = self._lock_for(key)
        try:
            async with lock:                             # the same record's events, one at a time, in arrival order
                await self._apply_with_retries(message, event)
        finally:
            self._release(key)

    async def _apply_with_retries(self, message: aio_pika.abc.AbstractIncomingMessage, event: dict[str, Any]) -> None:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                applied = await apply_once(self.sessions, event, self.handler)
                log.info("event_consumed", event_type=event.get("event_type"), event_id=event.get("event_id"), applied=applied)
                await message.ack()
                return
            except Exception:
                log.exception("event_handler_failed", queue=self.queue_name, attempts=attempt)
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(min(2 ** attempt, 30) / 10)   # retried here, not behind later events
        await message.reject(requeue=False)              # -> dead-letter queue

    async def _run(self) -> None:
        while True:
            try:
                connection = await aio_pika.connect_robust(self.url)
                async with connection:
                    self._channel = await connection.channel()
                    await self._channel.set_qos(prefetch_count=10)
                    exchange = await self._channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
                    dlx = await self._channel.declare_exchange(DLX, aio_pika.ExchangeType.TOPIC, durable=True)
                    dlq = await self._channel.declare_queue(f"{self.queue_name}.dlq", durable=True)
                    await dlq.bind(dlx, routing_key=self.queue_name)
                    queue = await self._channel.declare_queue(self.queue_name, durable=True, arguments={
                        "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": self.queue_name})
                    for key in self.bindings:
                        await queue.bind(exchange, routing_key=key)
                    await queue.consume(self._on_message)
                    await asyncio.Future()  # run until cancelled
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("consumer_error_retrying", queue=self.queue_name)
                await asyncio.sleep(2)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"consumer-{self.queue_name}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
