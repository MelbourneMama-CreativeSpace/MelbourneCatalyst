"""Tests for real per-post engagement metrics fetching."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.agents.social_media_analyzer import post_metrics
from app.db.models import (
    Company,
    ContentItem,
    ContentPlan,
    PlatformConnection,
    PostMetricSnapshot,
    PublishAttempt,
)


def _connection(platform: str, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        platform=platform,
        composio_connected_account_id="conn-123",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


async def test_fetch_facebook_post_metrics_prefers_reactions_over_plain_likes(monkeypatch):
    """Reactions (all types) is a superset of plain likes — confirmed
    against the real FACEBOOK_GET_POST output schema, which exposes both
    separately."""
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(
                data={
                    "likes": {"summary": {"total_count": 10}},
                    "comments": {"summary": {"total_count": 3}},
                    "shares": {"count": 2},
                    "reactions": {"summary": {"total_count": 15}},
                }
            )

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_facebook_post_metrics(_connection("facebook"), "page_post")

    assert result["likes"] == 15  # reactions, not the plain like count
    assert result["comments"] == 3
    assert result["shares"] == 2

    tool_slug, kwargs = calls[0]
    assert tool_slug == "FACEBOOK_GET_POST"
    assert kwargs["arguments"] == {
        "post_id": "page_post",
        "fields": "likes.summary(true),comments.summary(true),shares,reactions.summary(true)",
    }


async def test_fetch_facebook_post_metrics_falls_back_to_plain_likes_without_reactions(monkeypatch):
    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            return SimpleNamespace(data={"likes": {"summary": {"total_count": 7}}})

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_facebook_post_metrics(_connection("facebook"), "page_post")

    assert result["likes"] == 7
    assert result["comments"] is None
    assert result["shares"] is None


async def test_fetch_instagram_post_metrics_parses_the_real_insights_list_shape(monkeypatch):
    """Confirmed live against a real INSTAGRAM_GET_POST_INSIGHTS call —
    `response.data` is a *dict* wrapping the list under its own "data"
    key (`{"data": [{name, values: [{value}]}, ...]}`), not a bare list
    at the top level. That mismatch (this test previously mocked a bare
    list, matching the code's wrong assumption instead of reality) was
    the real production bug: every real insight got silently discarded
    as `None`/0, indistinguishable from genuinely-zero engagement,
    without ever raising."""
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            if kwargs["arguments"]["metric"] == "views":
                return SimpleNamespace(data={"data": [{"name": "views", "values": [{"value": 500}]}]})
            return SimpleNamespace(
                data={
                    "data": [
                        {"name": "reach", "values": [{"value": 1000}]},
                        {"name": "likes", "values": [{"value": 50}]},
                        {"name": "comments", "values": [{"value": 5}]},
                        {"name": "saved", "values": [{"value": 12}]},
                        {"name": "shares", "values": [{"value": 3}]},
                    ]
                }
            )

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_instagram_post_metrics(_connection("instagram"), "media-1")

    assert result["reach"] == 1000
    assert result["likes"] == 50
    assert result["comments"] == 5
    assert result["saves"] == 12
    assert result["shares"] == 3
    assert result["views"] == 500
    assert calls[0][1]["arguments"]["ig_post_id"] == "media-1"


async def test_fetch_instagram_post_metrics_also_tolerates_a_bare_list_shape(monkeypatch):
    """Defensive fallback only — a bare list isn't what a real call
    returns today (confirmed above), but _extract_insight_items still
    accepts it in case a future Composio version reverts the shape."""

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            if kwargs["arguments"]["metric"] == "views":
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[{"name": "likes", "values": [{"value": 9}]}])

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_instagram_post_metrics(_connection("instagram"), "media-1")

    assert result["likes"] == 9


async def test_fetch_instagram_post_metrics_tolerates_views_being_unsupported(monkeypatch):
    """Not every media type supports "views" (e.g. a plain image) — a
    400 on that specific call shouldn't take down the whole fetch."""

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            if kwargs["arguments"]["metric"] == "views":
                raise RuntimeError("Composio: 400 unsupported metric for media type")
            return SimpleNamespace(data={"data": [{"name": "likes", "values": [{"value": 20}]}]})

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_instagram_post_metrics(_connection("instagram"), "media-1")

    assert result["likes"] == 20
    assert result["views"] is None


async def test_fetch_linkedin_post_metrics_only_returns_a_reaction_count(monkeypatch):
    """Genuinely all that's available — no comment/share/impression
    metric exists anywhere in Composio's current LinkedIn toolkit for a
    specific post, confirmed live. Must not fabricate the rest."""
    calls = []

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            calls.append((tool_slug, kwargs))
            return SimpleNamespace(data={"paging": {"total": 42}})

    monkeypatch.setattr(post_metrics, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await post_metrics.fetch_linkedin_post_metrics(
        _connection("linkedin"), "urn:li:share:123"
    )

    assert result["likes"] == 42
    assert "comments" not in result
    assert "shares" not in result

    tool_slug, kwargs = calls[0]
    assert tool_slug == "LINKEDIN_LIST_REACTIONS"
    assert kwargs["arguments"] == {"entity": "urn:li:share:123", "count": 1}


async def test_fetch_youtube_post_metrics_converts_string_counts_to_int(monkeypatch):
    """YouTube's own API returns statistics as strings, not numbers —
    confirmed against the real response shape used elsewhere this
    session."""

    async def _fake_fetch_video_analytics(connection, video_ids):
        assert video_ids == ["abc123"]
        return [{"statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "5"}}]

    monkeypatch.setattr(post_metrics, "fetch_video_analytics", _fake_fetch_video_analytics)

    result = await post_metrics.fetch_youtube_post_metrics(_connection("youtube"), "abc123")

    assert result["views"] == 1000
    assert result["likes"] == 50
    assert result["comments"] == 5


async def test_fetch_post_metrics_dispatches_by_platform(monkeypatch):
    # _FETCHER_BY_PLATFORM holds function references captured at import
    # time — patching the dict entry itself, not the top-level name, is
    # what actually redirects dispatch.
    async def _fake_facebook(connection, execution_id):
        return {"likes": 5}

    monkeypatch.setitem(post_metrics._FETCHER_BY_PLATFORM, "facebook", _fake_facebook)

    result = await post_metrics.fetch_post_metrics(_connection("facebook"), "post-1")

    assert result == {"likes": 5}


async def test_fetch_post_metrics_returns_none_on_failure(monkeypatch):
    """A scheduled sync must be able to skip a failed item cleanly — same
    isolate-per-item contract as every other scheduled batch job here."""

    async def _failing(connection, execution_id):
        raise RuntimeError("Composio: rate limited")

    monkeypatch.setitem(post_metrics._FETCHER_BY_PLATFORM, "facebook", _failing)

    result = await post_metrics.fetch_post_metrics(_connection("facebook"), "post-1")

    assert result is None


async def test_fetch_post_metrics_returns_none_for_unsupported_platform():
    result = await post_metrics.fetch_post_metrics(_connection("myspace"), "post-1")
    assert result is None


# ── Scheduled sync ──────────────────────────────────────────────────────


_UNSET = object()


async def _seed_published_item(
    test_session_factory,
    *,
    platform="facebook",
    execution_id="post-1",
    with_attempt=True,
    published_at=_UNSET,
) -> uuid.UUID:
    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=f"https://example.com/{company_id}", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Item",
                description="d",
                content_type="post",
                platform=platform,
                suggested_date=date.today(),
                published_at=(
                    datetime.now(timezone.utc) if published_at is _UNSET else published_at
                ),
            )
        )
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform=platform,
                status="connected",
                composio_connected_account_id="conn-abc123",
            )
        )
        if with_attempt:
            session.add(
                PublishAttempt(
                    id=uuid.uuid4(),
                    content_item_id=item_id,
                    platform_connection_id=connection_id,
                    status="success",
                    composio_execution_id=execution_id,
                )
            )
        await session.commit()
    return item_id


async def test_sync_one_item_stores_a_new_snapshot(monkeypatch, test_session_factory):
    monkeypatch.setattr(post_metrics, "async_session_factory", test_session_factory)
    item_id = await _seed_published_item(test_session_factory, execution_id="post-1")

    async def _fake_fetch(connection, execution_id):
        assert execution_id == "post-1"
        return {"likes": 10, "comments": 2, "shares": 1, "raw_metadata": {"ok": True}}

    monkeypatch.setattr(post_metrics, "fetch_post_metrics", _fake_fetch)

    await post_metrics._sync_one_item(item_id)

    async with test_session_factory() as session:
        snapshots = (
            await session.execute(
                select(PostMetricSnapshot).where(PostMetricSnapshot.content_item_id == item_id)
            )
        ).scalars().all()

    assert len(snapshots) == 1
    assert snapshots[0].likes == 10
    assert snapshots[0].comments == 2
    assert snapshots[0].shares == 1


async def test_sync_one_item_skips_unpublished_items(monkeypatch, test_session_factory):
    monkeypatch.setattr(post_metrics, "async_session_factory", test_session_factory)
    item_id = await _seed_published_item(test_session_factory, published_at=None)

    called = False

    async def _fake_fetch(connection, execution_id):
        nonlocal called
        called = True
        return {"likes": 1}

    monkeypatch.setattr(post_metrics, "fetch_post_metrics", _fake_fetch)

    await post_metrics._sync_one_item(item_id)

    assert called is False


async def test_sync_one_item_skips_items_with_no_successful_attempt(monkeypatch, test_session_factory):
    monkeypatch.setattr(post_metrics, "async_session_factory", test_session_factory)
    item_id = await _seed_published_item(test_session_factory, with_attempt=False)

    called = False

    async def _fake_fetch(connection, execution_id):
        nonlocal called
        called = True
        return {"likes": 1}

    monkeypatch.setattr(post_metrics, "fetch_post_metrics", _fake_fetch)

    await post_metrics._sync_one_item(item_id)

    assert called is False


async def test_sync_one_item_stores_nothing_when_fetch_returns_none(monkeypatch, test_session_factory):
    """fetch_post_metrics returning None (unsupported platform, or a
    genuine failure already logged internally) must not create an empty
    snapshot row."""
    monkeypatch.setattr(post_metrics, "async_session_factory", test_session_factory)
    item_id = await _seed_published_item(test_session_factory)

    async def _fake_fetch(connection, execution_id):
        return None

    monkeypatch.setattr(post_metrics, "fetch_post_metrics", _fake_fetch)

    await post_metrics._sync_one_item(item_id)

    async with test_session_factory() as session:
        snapshots = (
            await session.execute(
                select(PostMetricSnapshot).where(PostMetricSnapshot.content_item_id == item_id)
            )
        ).scalars().all()

    assert snapshots == []


async def test_run_scheduled_post_metrics_sync_isolates_per_item_failures(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(post_metrics, "async_session_factory", test_session_factory)
    ok_id = await _seed_published_item(test_session_factory, execution_id="ok-post")
    broken_id = await _seed_published_item(test_session_factory, execution_id="broken-post")

    async def _fake_fetch(connection, execution_id):
        if execution_id == "broken-post":
            raise RuntimeError("boom")
        return {"likes": 5}

    monkeypatch.setattr(post_metrics, "fetch_post_metrics", _fake_fetch)

    # Should not raise despite one item failing.
    await post_metrics.run_scheduled_post_metrics_sync()

    async with test_session_factory() as session:
        ok_snapshots = (
            await session.execute(
                select(PostMetricSnapshot).where(PostMetricSnapshot.content_item_id == ok_id)
            )
        ).scalars().all()
        broken_snapshots = (
            await session.execute(
                select(PostMetricSnapshot).where(PostMetricSnapshot.content_item_id == broken_id)
            )
        ).scalars().all()

    assert len(ok_snapshots) == 1
    assert broken_snapshots == []
