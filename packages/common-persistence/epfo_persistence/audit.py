"""Local audit record, written in the caller's transaction (docs/architecture.md §2.2)."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from epfo_observability import correlation_id


async def audit(session: AsyncSession, *, actor_subject: str, actor_stakeholder: str, action: str,
                target_type: str, target_id: str, detail: str | None = None) -> None:
    await session.execute(text(
        "INSERT INTO audit_local (actor_subject, actor_stakeholder, action, target_type, target_id, correlation_id, detail) "
        "VALUES (:s, :st, :a, :tt, :ti, :c, :d)"),
        {"s": actor_subject, "st": actor_stakeholder, "a": action, "tt": target_type, "ti": target_id,
         "c": correlation_id() or "-", "d": detail})
