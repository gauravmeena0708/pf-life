"""Database access for this service. Only this service's own database is ever used (init.md §2.4)."""
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import settings

_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        pool = {"pool_size": settings.db_pool_size, "pool_pre_ping": True} if settings.database_url.startswith("postgresql") else {"poolclass": NullPool}  # SQLite tests: no connections shared across event loops
        _engine = create_async_engine(settings.database_url, **pool)
    return _engine


def sessions() -> async_sessionmaker:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def database_ready() -> bool:
    async with engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
