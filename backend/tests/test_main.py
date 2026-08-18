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


async def test_lifespan_shutdown_waits_for_in_flight_jobs_before_disposing(monkeypatch):
    """Real bug, confirmed live on Render: the greenlet-finalization crash
    kept recurring even after engine.dispose() was added, because
    scheduler.shutdown(wait=False) let shutdown proceed while a job was
    still mid-execution — that job's own DB connection was still checked
    out (not pooled), so dispose() couldn't reach it. wait=True must be
    passed, and must happen before dispose()."""
    monkeypatch.setattr(type(main_module.engine), "dispose", AsyncMock())
    calls = []
    monkeypatch.setattr(main_module.scheduler, "shutdown", lambda wait: calls.append(wait))

    async with main_module.lifespan(None):
        pass

    assert calls == [True]
