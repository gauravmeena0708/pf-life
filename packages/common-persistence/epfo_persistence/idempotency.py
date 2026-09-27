"""Idempotency keys (init.md §3.3): a retried money or filing command returns the original result.

    cached = await find_response(session, actor, operation, key, body_hash)
    if cached: return JSONResponse(cached.body, status_code=cached.status)
    ... do the work in the same transaction ...
    await store_response(session, actor, operation, key, body_hash, status, body)
"""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from epfo_observability import Problem


class IdempotencyConflict(Problem):
    def __init__(self) -> None:
        super().__init__(422, "/problems/idempotency-key-reused",
                         "Idempotency-Key was already used with a different request",
                         "Use a new Idempotency-Key for a different request, or resend the identical request.")


@dataclass(frozen=True)
class Stored:
    status: int
    body: dict[str, Any]


def request_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


async def find_response(session: AsyncSession, actor: str, operation: str, key: str, body_hash: str) -> Stored | None:
    row = (await session.execute(text(
        "SELECT request_hash, response_status, response_body FROM idempotency_keys "
        "WHERE actor_subject = :a AND operation = :o AND key = :k"), {"a": actor, "o": operation, "k": key})).first()
    if row is None:
        return None
    if row[0] != body_hash:
        raise IdempotencyConflict()
    body = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return Stored(row[1], body)


async def store_response(session: AsyncSession, actor: str, operation: str, key: str, body_hash: str,
                         status: int, body: dict[str, Any]) -> None:
    await session.execute(text(
        "INSERT INTO idempotency_keys (actor_subject, operation, key, request_hash, response_status, response_body) "
        "VALUES (:a, :o, :k, :h, :s, :b)"),
        {"a": actor, "o": operation, "k": key, "h": body_hash, "s": status, "b": json.dumps(body, default=str)})
