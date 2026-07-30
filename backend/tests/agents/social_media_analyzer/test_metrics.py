"""Tests for Composio-backed platform metrics fetching. Deliberately does
NOT test parsing a specific real response shape (that's the whole point —
no real connected account exists to know what one looks like); tests the
graceful-degradation contract and the "store as-is, best-effort top-level
extraction" behavior instead.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.agents.social_media_analyzer import metrics


def _configure(monkeypatch, **overrides):
    monkeypatch.setattr(metrics.settings, "COMPOSIO_API_KEY", "test-composio-key")
    monkeypatch.setattr(metrics.settings, "COMPOSIO_LINKEDIN_AUTH_CONFIG_ID", "ac_linkedin_123")
    monkeypatch.setattr(
        metrics.settings, "COMPOSIO_LINKEDIN_METRICS_TOOL_SLUG", "LINKEDIN_GET_PROFILE_INSIGHTS"
    )
    for setting_name, value in overrides.items():
        monkeypatch.setattr(metrics.settings, setting_name, value)


async def test_fetch_platform_metrics_raises_when_api_key_not_set(monkeypatch):
    _configure(monkeypatch, COMPOSIO_API_KEY="")

    with pytest.raises(metrics.MetricsNotConfiguredError):
        await metrics.fetch_platform_metrics(uuid.uuid4(), "linkedin", "conn-123")


async def test_fetch_platform_metrics_raises_when_metrics_tool_slug_not_set(monkeypatch):
    # The real, current state of this environment — no metrics tool slug
    # has been confirmed against a live Composio account yet.
    _configure(monkeypatch, COMPOSIO_LINKEDIN_METRICS_TOOL_SLUG="")

    with pytest.raises(metrics.MetricsNotConfiguredError):
        await metrics.fetch_platform_metrics(uuid.uuid4(), "linkedin", "conn-123")


async def test_fetch_platform_metrics_calls_composio_execute_with_the_right_arguments(
    monkeypatch,
):
    _configure(monkeypatch)
    captured = {}

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            captured["tool_slug"] = tool_slug
            captured["kwargs"] = kwargs
            return SimpleNamespace(data={"follower_count": 1200, "engagement_rate": 0.042})

    monkeypatch.setattr(metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    connection_id = uuid.uuid4()
    snapshot = await metrics.fetch_platform_metrics(connection_id, "linkedin", "conn-123")

    assert captured["tool_slug"] == "LINKEDIN_GET_PROFILE_INSIGHTS"
    assert captured["kwargs"]["connected_account_id"] == "conn-123"
    assert snapshot.platform_connection_id == connection_id
    assert snapshot.follower_count == 1200
    assert snapshot.engagement_rate == 0.042
    assert snapshot.raw_metadata == {"follower_count": 1200, "engagement_rate": 0.042}


async def test_fetch_platform_metrics_stores_unrecognized_response_without_crashing(monkeypatch):
    """A real platform's actual response shape is unknown in this
    environment — this asserts the graceful "store what came back, leave
    the typed fields null" behavior for a response that doesn't match the
    optimistic top-level-key guess, rather than crashing or fabricating
    values."""
    _configure(monkeypatch)

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"weird_nested": {"stats": {"followers": 500}}})

    monkeypatch.setattr(metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    snapshot = await metrics.fetch_platform_metrics(uuid.uuid4(), "linkedin", "conn-123")

    assert snapshot.follower_count is None
    assert snapshot.engagement_rate is None
    assert snapshot.raw_metadata == {"weird_nested": {"stats": {"followers": 500}}}


async def test_fetch_platform_metrics_propagates_a_real_composio_failure(monkeypatch):
    _configure(monkeypatch)

    class _FailingTools:
        def execute(self, tool_slug, **kwargs):
            raise RuntimeError("Composio: connected account is expired")

    monkeypatch.setattr(metrics, "_client", lambda: SimpleNamespace(tools=_FailingTools()))

    with pytest.raises(RuntimeError, match="expired"):
        await metrics.fetch_platform_metrics(uuid.uuid4(), "linkedin", "conn-123")


# --- run_scheduled_metrics_sync (batch job) -------------------------------


async def test_scheduled_metrics_sync_skips_connections_without_a_composio_account(
    monkeypatch, test_session_factory
):
    from app.db.models import PlatformConnection

    monkeypatch.setattr(metrics, "async_session_factory", test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=uuid.uuid4(),
                platform="linkedin",
                status="connected",
                composio_connected_account_id=None,
            )
        )
        await session.commit()

    # Should not raise even though there's nothing valid to sync.
    await metrics.run_scheduled_metrics_sync()

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                select(metrics.PlatformMetricSnapshot).where(
                    metrics.PlatformMetricSnapshot.platform_connection_id == connection_id
                )
            )
        ).scalars().all()
    assert rows == []


async def test_scheduled_metrics_sync_persists_a_snapshot_for_a_configured_connection(
    monkeypatch, test_session_factory
):
    from app.db.models import PlatformConnection

    monkeypatch.setattr(metrics, "async_session_factory", test_session_factory)
    _configure(monkeypatch)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=uuid.uuid4(),
                platform="linkedin",
                status="connected",
                composio_connected_account_id="conn-real",
            )
        )
        await session.commit()

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"follower_count": 42})

    monkeypatch.setattr(metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    await metrics.run_scheduled_metrics_sync()

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                select(metrics.PlatformMetricSnapshot).where(
                    metrics.PlatformMetricSnapshot.platform_connection_id == connection_id
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].follower_count == 42


async def test_scheduled_metrics_sync_isolates_one_connections_failure(
    monkeypatch, test_session_factory
):
    from app.db.models import PlatformConnection

    monkeypatch.setattr(metrics, "async_session_factory", test_session_factory)
    _configure(monkeypatch)
    failing_id = uuid.uuid4()
    ok_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add_all(
            [
                PlatformConnection(
                    id=failing_id,
                    company_id=uuid.uuid4(),
                    platform="linkedin",
                    status="connected",
                    composio_connected_account_id="conn-fail",
                ),
                PlatformConnection(
                    id=ok_id,
                    company_id=uuid.uuid4(),
                    platform="linkedin",
                    status="connected",
                    composio_connected_account_id="conn-ok",
                ),
            ]
        )
        await session.commit()

    class _FlakyTools:
        def execute(self, tool_slug, **kwargs):
            if kwargs["connected_account_id"] == "conn-fail":
                raise RuntimeError("boom")
            return SimpleNamespace(data={"follower_count": 10})

    monkeypatch.setattr(metrics, "_client", lambda: SimpleNamespace(tools=_FlakyTools()))

    await metrics.run_scheduled_metrics_sync()  # should not raise

    async with test_session_factory() as session:
        ok_rows = (
            await session.execute(
                select(metrics.PlatformMetricSnapshot).where(
                    metrics.PlatformMetricSnapshot.platform_connection_id == ok_id
                )
            )
        ).scalars().all()
    assert len(ok_rows) == 1
