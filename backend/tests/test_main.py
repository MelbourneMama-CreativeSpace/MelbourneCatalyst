"""Tests for the app lifespan (app/main.py) — specifically that shutdown
actually disposes the DB engine's connection pool.

Real bug, confirmed live on Render: without this, pooled asyncpg
connections were only ever closed by the garbage collector, which runs
after the event loop that could await their real async close() is
already gone — surfaces in production logs as "RuntimeError: greenlet is
being finalized" plus a SAWarning every time the process exits (the
free-tier instance spinning down after inactivity, or a redeploy).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app import main as main_module


async def test_lifespan_disposes_the_db_engine_on_shutdown(monkeypatch):
    fake_dispose = AsyncMock()
    # AsyncEngine wraps the sync engine behind a slotted proxy — dispose
    # isn't settable on the instance, only on the class.
    monkeypatch.setattr(type(main_module.engine), "dispose", fake_dispose)

    async with main_module.lifespan(None):
        fake_dispose.assert_not_awaited()  # not yet — only on the way out

    fake_dispose.assert_awaited_once()
