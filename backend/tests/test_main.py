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

import asyncio
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


async def test_lifespan_shutdown_awaits_a_genuinely_in_flight_job_before_disposing(
    monkeypatch,
):
    """Real bug, confirmed live on Render: the greenlet-finalization crash
    kept recurring even after switching to scheduler.shutdown(wait=True),
    because AsyncIOExecutor.shutdown() cannot actually honor wait=True at
    all — confirmed by reading the installed apscheduler source directly
    (its own comment: "There is no way to honor wait=True without
    converting this method into a coroutine method"). It unconditionally
    CANCELS every in-flight job task regardless of what `wait` was
    passed, so a job's own `async with session:` never gets a clean
    chance to return its connection to the pool.

    The real fix bypasses scheduler.shutdown()'s (broken) wait mechanism
    entirely and awaits the executor's own pending futures directly —
    this test proves that with a genuine asyncio task actually injected
    into the real, module-level scheduler's real executor (not a
    replacement double for it — this scheduler is a shared singleton
    other tests in this file also start/stop, and swapping out its real
    executor for a fake one left it unable to clean up its own job
    store, breaking every test that ran after it)."""
    monkeypatch.setattr(type(main_module.engine), "dispose", AsyncMock())

    completed = False

    async def _slow_job():
        nonlocal completed
        await asyncio.sleep(0.05)
        completed = True

    task_holder: dict = {}
    real_start = main_module.scheduler.start

    def _start_then_inject(*args, **kwargs):
        real_start(*args, **kwargs)
        # Only after start() does the real AsyncIOExecutor exist to
        # inject into — same object lifespan()'s own shutdown code reads
        # _pending_futures off of.
        task_holder["task"] = asyncio.ensure_future(_slow_job())
        main_module.scheduler._executors["default"]._pending_futures.add(task_holder["task"])

    monkeypatch.setattr(main_module.scheduler, "start", _start_then_inject)

    async with main_module.lifespan(None):
        pass

    # The real assertion: the job actually ran to completion, not just
    # that some call happened with some argument.
    assert completed is True
    assert task_holder["task"].done() and not task_holder["task"].cancelled()
