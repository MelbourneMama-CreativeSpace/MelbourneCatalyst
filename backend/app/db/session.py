
"""Async SQLAlchemy engine/session, targeting the Supabase Postgres instance."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# DATABASE_URL must point at Supavisor's *session*-mode port (5432), not the
# transaction-mode port (6543): transaction mode hands out a different
# backend Postgres session per query, which breaks asyncpg's server-side
# prepared statements (DuplicatePreparedStatementError — asyncpg's statement
# names collide with whatever the previous logical connection on that
# recycled backend session left behind). Session mode gives this app's
# connection pool a stable backend session per connection, like a normal
# Postgres connection, so prepared statements behave correctly.


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    # `pool_pre_ping` only catches a connection that's already dead *at
    # checkout* — it can't catch one Supavisor's own server-side idle
    # reaping kills in the gap between that ping succeeding and the real
    # query landing, which is exactly what
    # `ConnectionDoesNotExistError: connection was closed in the middle of
    # operation` looks like (confirmed live). Recycling anything older than
    # 30 minutes discards connections proactively, well under Supavisor's
    # own idle timeout, so the pool never hands out one old enough to have
    # been reaped server-side in the first place.
    pool_recycle=1800,
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with async_session_factory() as session:
        yield session
