"""Shared fixtures: an in-memory SQLite DB so tests never touch Supabase."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401 — registers Trend on Base.metadata
from app.db.session import Base


@pytest_asyncio.fixture
async def test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_session_factory) -> AsyncSession:
    async with test_session_factory() as session:
        yield session
