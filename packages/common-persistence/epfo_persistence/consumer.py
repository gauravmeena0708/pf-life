"""Idempotent event consumer: one durable queue per consumer, dead-letter after retries.

The handler runs in one database transaction together with the inbox insert, so an event is applied
exactly once even though RabbitMQ delivers at least once.
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


class Consumer:
    def __init__(self, engine: AsyncEngine, rabbitmq_url: str, queue: str, bindings: list[str], handler: Handler) -> None:
        self.url, self.queue_name, self.bindings, self.handler = rabbitmq_url, queue, bindings, handler
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._task: asyncio.Task | None = None

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        attempts = int((message.headers or {}).get("x-attempts", 0)) + 1
        try:
            event = json.loads(message.body)
            applied = await apply_once(self.sessions, event, self.handler)
            log.info("event_consumed", event_type=event.get("event_type"), event_id=event.get("event_id"), applied=applied)
            await message.ack()
        except Exception:
            log.exception("event_handler_failed", queue=self.queue_name, attempts=attempts)
            if attempts >= MAX_ATTEMPTS:
                await message.reject(requeue=False)  # -> dead-letter queue
            else:
                await asyncio.sleep(min(2 ** attempts, 30) / 10)
                await self._channel.default_exchange.publish(
                    aio_pika.Message(message.body, headers={**(message.headers or {}), "x-attempts": attempts},
                                     content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key=self.queue_name)
                await message.ack()

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
