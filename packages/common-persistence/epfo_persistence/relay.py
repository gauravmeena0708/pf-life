"""Outbox relay: publishes committed outbox rows to RabbitMQ and marks them published.

At-least-once: a crash between publish and mark causes a re-publish; consumers deduplicate by event_id.
"""
import asyncio
import json
from datetime import UTC, datetime

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from epfo_observability import get_logger

from .events import EXCHANGE, routing_key

log = get_logger("outbox-relay")

_SELECT = text(
    "SELECT id, payload FROM outbox WHERE published_at IS NULL ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED")
_MARK = text("UPDATE outbox SET published_at = :at, attempts = attempts + 1 WHERE id = :id")
_FAIL = text("UPDATE outbox SET attempts = attempts + 1 WHERE id = :id")


class OutboxRelay:
    def __init__(self, engine: AsyncEngine, rabbitmq_url: str, *, interval_seconds: float = 0.5, batch: int = 50) -> None:
        self.engine, self.url, self.interval, self.batch = engine, rabbitmq_url, interval_seconds, batch
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def publish_pending(self, exchange: aio_pika.abc.AbstractExchange) -> int:
        async with self.engine.begin() as conn:
            rows = (await conn.execute(_SELECT, {"limit": self.batch})).all()
            for row_id, stored in rows:
                stored = stored if isinstance(stored, dict) else json.loads(stored)
                body = stored["envelope"]
                try:
                    await exchange.publish(
                        aio_pika.Message(json.dumps(body).encode(), content_type="application/json",
                                         message_id=body["event_id"], correlation_id=body["correlation_id"],
                                         delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                        routing_key=routing_key(stored["producer"], body["event_type"]))
                    await conn.execute(_MARK, {"at": datetime.now(UTC), "id": row_id})
                except Exception:
                    log.exception("outbox_publish_failed", event_id=body["event_id"])
                    await conn.execute(_FAIL, {"id": row_id})
                    raise
            return len(rows)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                connection = await aio_pika.connect_robust(self.url)
                async with connection:
                    channel = await connection.channel(publisher_confirms=True)
                    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
                    while not self._stopping:
                        published = await self.publish_pending(exchange)
                        if not published:
                            await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("outbox_relay_error_retrying")
                await asyncio.sleep(2)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
