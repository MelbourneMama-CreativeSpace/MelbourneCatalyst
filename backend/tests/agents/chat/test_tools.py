"""Tests for the chat agent's read-only tools — direct DB-backed checks,
independent of the tool-use loop itself (covered in test_agent.py)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.agents.chat import tools
from app.agents.social_media_analyzer.publish import DeleteNotSupportedError
from app.db.models import Company, PlatformConnection, YouTubeUploadJob
from app.security.auth import CurrentUser

_USER = CurrentUser(id="test-user-id", email="test@example.com")


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id,
        url=f"https://example.com/{company_id}",
        status="complete",
        name="Acme",
        industry="Software",
        owner_id="test-user-id",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def test_get_company_summary_returns_profile(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)

    result = await tools.get_company_summary(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert "Acme" in result
    assert "Software" in result


async def test_get_company_summary_handles_invalid_uuid(db_session):
    result = await tools.get_company_summary(db_session, user=_USER, company_id="not-a-uuid")
    assert "isn't a valid company id" in result


async def test_get_company_summary_handles_missing_company(db_session):
    result = await tools.get_company_summary(
        db_session, user=_USER, company_id=str(uuid.uuid4())
    )
    assert "No company found" in result


async def test_get_company_summary_handles_incomplete_onboarding(test_session_factory):
    company_id = await _seed_company(test_session_factory, status="pending", name=None)
    async with test_session_factory() as session:
        result = await tools.get_company_summary(
            session, user=_USER, company_id=str(company_id)
        )
    assert "onboarding not finished" in result


async def test_get_content_pipeline_status_counts_rows(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)

    result = await tools.get_content_pipeline_status(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert "0 strategies" in result
    assert "0 content plans" in result
    assert "0 campaigns" in result


async def test_list_trending_topics_handles_empty_state(db_session):
    result, cards = await tools.list_trending_topics(db_session)
    assert "No trending topics" in result
    assert cards == []


async def test_list_trending_topics_includes_real_id_and_insight_in_text(
    test_session_factory, db_session
):
    """Regression test: the id has to be in the text Claude actually
    reads, not just the card data (cards are a UI-only side-channel never
    fed back into the model's context) — same "Invalid ... id" bug class
    already fixed for find_content_items/create_content_item. `insight`
    (why it matters) also has to be there — the actual substance worth
    writing content around, not just a bare title."""
    from datetime import datetime, timezone

    from app.db.models import Trend

    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="A real trending topic",
                insight="This matters because of a real reason.",
                url="https://example.com/trend",
                relevance_score=0.9,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    result, cards = await tools.list_trending_topics(db_session)

    assert str(trend_id) in result
    assert "This matters because of a real reason." in result
    assert len(cards) == 1


async def test_list_trending_topics_returns_weak_matches_instead_of_hiding_them(
    test_session_factory, db_session
):
    """Regression test for a real bug: this tool used to apply the same
    strict bar as the dashboard's "genuinely great" recommendation list
    (min relevance 0.75, discovered within 7 days) — so a niche with real,
    discovered trends that just weren't a *strong* match read to Claude as
    having no trend data at all, indistinguishable from trend collection
    never having run. A weak/old trend should still come back; the
    relevance score is what tells Claude (and the user) how much to trust
    it, not a hard cutoff that erases it from the conversation entirely."""
    from datetime import datetime, timedelta, timezone

    from app.db.models import Trend

    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="A weakly-related, older topic",
                url="https://example.com/weak-trend",
                relevance_score=0.12,  # well below the old 0.75 recommendation bar
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc) - timedelta(days=30),  # older than 7 days
            )
        )
        await session.commit()

    result, cards = await tools.list_trending_topics(db_session)

    assert str(trend_id) in result
    assert "0.12" in result
    assert len(cards) == 1


async def test_list_companies_handles_empty_state(db_session):
    result = await tools.list_companies(db_session, user=_USER)
    assert result == "No companies onboarded yet."


async def test_list_companies_lists_accessible_companies(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory, name="Acme")

    result = await tools.list_companies(db_session, user=_USER)

    assert "1 companies" in result
    assert "Acme" in result
    assert str(company_id) in result


async def test_list_companies_excludes_incomplete_onboarding(test_session_factory, db_session):
    await _seed_company(test_session_factory, status="pending", name=None)

    result = await tools.list_companies(db_session, user=_USER)

    assert result == "No companies onboarded yet."


async def test_create_content_item_with_explicit_company_id(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)

    item_id = uuid.uuid4()

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        item = SimpleNamespace(
            id=item_id, title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=None, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    text, cards = await tools.create_content_item(
        db_session, user=_USER, company_id=str(company_id), topic="a launch announcement"
    )

    assert "Created" in text
    # The real id must be in the text Claude reads, not just the card data
    # — cards never reach the model's own context. Without this, a
    # follow-up publish/schedule/approve call has no real id to quote (see
    # the "Invalid content item id in proposed action" bug this fixes).
    assert str(item_id) in text
    assert len(cards) == 1
    assert cards[0]["company_id"] == str(company_id)


async def test_create_content_item_passes_through_a_real_trend_id(
    test_session_factory, db_session, monkeypatch
):
    """A trend_id quoted from list_trending_topics' own result text
    (never invented — same rule as content_item_id elsewhere) should
    reach create_manual_item so that trend genuinely centers the post."""
    company_id = await _seed_company(test_session_factory)
    trend_id = uuid.uuid4()

    captured = {}

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        captured["trend_id"] = trend_id
        item = SimpleNamespace(
            id=uuid.uuid4(), title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=None, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    await tools.create_content_item(
        db_session,
        user=_USER,
        company_id=str(company_id),
        topic="a post about that trend",
        trend_id=str(trend_id),
    )

    assert captured["trend_id"] == trend_id


async def test_create_content_item_ignores_an_invalid_trend_id(
    test_session_factory, db_session, monkeypatch
):
    """An unparseable trend_id degrades to "no specific trend" rather than
    refusing the whole post — create_manual_item already treats an
    unknown-but-valid UUID the same way."""
    company_id = await _seed_company(test_session_factory)

    captured = {}

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        captured["trend_id"] = trend_id
        item = SimpleNamespace(
            id=uuid.uuid4(), title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=None, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    await tools.create_content_item(
        db_session, user=_USER, company_id=str(company_id), topic="a post", trend_id="not-a-uuid"
    )

    assert captured["trend_id"] is None


async def test_create_content_item_auto_attaches_an_image_already_in_the_message(
    test_session_factory, db_session, monkeypatch
):
    """A user attaching an image in chat and asking for a post shouldn't
    need a *second*, separate upload once the draft exists — the
    attachment markdown already in `topic` (the same `![filename](url)`
    syntax the frontend appends, see chat-attachments.ts) should carry
    straight onto the new item's media_url automatically."""
    company_id = await _seed_company(test_session_factory)

    captured = {}

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        captured["media_url"] = media_url
        item = SimpleNamespace(
            id=uuid.uuid4(), title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=media_url, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    topic = (
        "Behind the build post\n\n"
        "![ghibli.png](https://storage.example.com/chat-attachments/ghibli.png)"
    )
    await tools.create_content_item(
        db_session, user=_USER, company_id=str(company_id), topic=topic, platform="instagram"
    )

    assert captured["media_url"] == "https://storage.example.com/chat-attachments/ghibli.png"


async def test_create_content_item_leaves_media_url_unset_without_an_attachment(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)

    captured = {}

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        captured["media_url"] = media_url
        item = SimpleNamespace(
            id=uuid.uuid4(), title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=media_url, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    await tools.create_content_item(
        db_session, user=_USER, company_id=str(company_id), topic="just a text post, no image"
    )

    assert captured["media_url"] is None


async def test_create_content_item_auto_resolves_single_accessible_company(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory, name="Only Co")

    captured = {}

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        captured["company_id"] = company_id
        item = SimpleNamespace(
            id=uuid.uuid4(), title="A post", platform=platform, content_type=content_type,
            draft_copy="...", hashtags=None, media_url=None, approval_status="pending",
            scheduled_at=None, published_at=None,
        )
        return item, True

    monkeypatch.setattr(tools, "create_manual_item", _fake_create_manual_item)

    text, cards = await tools.create_content_item(
        db_session, user=_USER, company_id=None, topic="a launch announcement"
    )

    assert "Created" in text
    assert captured["company_id"] == company_id


async def test_create_content_item_no_company_available(db_session):
    text, cards = await tools.create_content_item(
        db_session, user=_USER, company_id=None, topic="a launch announcement"
    )

    assert "No onboarded company" in text
    assert cards == []


async def test_create_content_item_multiple_companies_asks_which(
    test_session_factory, db_session
):
    await _seed_company(test_session_factory, name="Acme")
    await _seed_company(test_session_factory, name="Widgets Co")

    text, cards = await tools.create_content_item(
        db_session, user=_USER, company_id=None, topic="a launch announcement"
    )

    assert "Which company" in text
    assert "Acme" in text
    assert "Widgets Co" in text
    assert cards == []


async def _seed_content_item(test_session_factory, company_id, **overrides) -> uuid.UUID:
    from datetime import date

    from app.db.models import ContentItem, ContentPlan

    item_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    defaults = dict(
        id=item_id,
        content_plan_id=plan_id,
        title="A launch post",
        description="",
        content_type="post",
        platform="linkedin",
        theme=None,
        suggested_date=date.today(),
        approval_status="pending",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete", is_manual=True))
        session.add(ContentItem(**defaults))
        await session.commit()
    return item_id


async def test_find_content_items_handles_empty_state(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)

    text, cards = await tools.find_content_items(db_session, user=_USER, company_id=str(company_id))

    assert text == "No matching content items found."
    assert cards == []


async def test_find_content_items_includes_real_id_in_text(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(test_session_factory, company_id, title="A launch post")

    text, cards = await tools.find_content_items(db_session, user=_USER, company_id=str(company_id))

    # Same bug as create_content_item: the id has to be in the text itself
    # (not just the card) or a follow-up write-tool call has nothing real
    # to quote.
    assert str(item_id) in text
    assert "A launch post" in text
    assert len(cards) == 1
    assert cards[0]["id"] == str(item_id)


async def test_find_content_items_auto_resolves_single_accessible_company(
    test_session_factory, db_session
):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(test_session_factory, company_id)

    text, cards = await tools.find_content_items(db_session, user=_USER, company_id=None)

    assert str(item_id) in text


async def _seed_youtube_connection(test_session_factory, company_id, **overrides) -> None:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=company_id,
        platform="youtube",
        status="connected",
        composio_connected_account_id="conn-yt-123",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(PlatformConnection(**defaults))
        await session.commit()


async def test_upload_youtube_video_tool_requires_a_connected_account(
    test_session_factory, db_session
):
    company_id = await _seed_company(test_session_factory)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="T",
        description="D",
    )

    assert "isn't connected" in result


async def test_upload_youtube_video_tool_reports_immediate_success(
    test_session_factory, db_session, monkeypatch
):
    """The tool now enqueues rather than uploading directly — this covers
    the common case, where the first attempt (made inside
    enqueue_youtube_upload itself) succeeds right away."""
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    captured = {}

    async def _fake_enqueue(session, connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        captured["connection"] = connection
        captured["video_url"] = video_url
        captured["title"] = title
        captured["tags"] = tags
        return SimpleNamespace(status="success", composio_execution_id="yt-video-abc123", status_error=None)

    monkeypatch.setattr(tools, "enqueue_youtube_upload", _fake_enqueue)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="My Video",
        description="D",
        tags=["yc"],
    )

    assert "Uploaded" in result
    assert "unlisted" in result
    assert captured["connection"].composio_connected_account_id == "conn-yt-123"
    assert captured["title"] == "My Video"
    assert captured["tags"] == ["yc"]


async def test_upload_youtube_video_tool_respects_explicit_privacy_status(
    test_session_factory, db_session, monkeypatch
):
    """privacy_status used to be hardcoded to 'unlisted' everywhere
    upstream even though upload_youtube_video() itself always accepted a
    real parameter — a user explicitly asking for a public upload had no
    way to actually get one. Confirmed as a real, reported gap."""
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    captured = {}

    async def _fake_enqueue(session, connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        captured["privacy_status"] = privacy_status
        return SimpleNamespace(status="success", composio_execution_id="yt-video-abc123", status_error=None)

    monkeypatch.setattr(tools, "enqueue_youtube_upload", _fake_enqueue)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="My Video",
        description="D",
        privacy_status="public",
    )

    assert captured["privacy_status"] == "public"
    assert "Uploaded" in result
    assert "public" in result
    assert "unlisted" not in result


async def test_upload_youtube_video_tool_rejects_an_invalid_privacy_status(
    test_session_factory, db_session
):
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="My Video",
        description="D",
        privacy_status="viral",
    )

    assert "isn't a valid YouTube privacy setting" in result


async def test_upload_youtube_video_tool_reports_queued_for_retry(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    async def _fake_enqueue(session, connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        return SimpleNamespace(status="pending", composio_execution_id=None, status_error="a transient network error")

    monkeypatch.setattr(tools, "enqueue_youtube_upload", _fake_enqueue)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="My Video",
        description="D",
    )

    assert "queued" in result
    assert "a transient network error" in result
    assert "No need to re-ask" in result


async def test_upload_youtube_video_tool_surfaces_a_permanent_failure(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    async def _fake_enqueue(session, connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        return SimpleNamespace(
            status="failed",
            composio_execution_id=None,
            status_error="That video isn't something uploaded through this app.",
        )

    monkeypatch.setattr(tools, "enqueue_youtube_upload", _fake_enqueue)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://evil.example.com/video.mp4",
        title="T",
        description="D",
    )

    assert "isn't something uploaded through this app" in result


async def _seed_upload_job(test_session_factory, connection_id, **overrides) -> uuid.UUID:
    job_id = uuid.uuid4()
    defaults = dict(
        id=job_id,
        platform_connection_id=connection_id,
        video_url="https://example.com/video.mp4",
        title="Our YC Fall 2026 Application Journey",
        description="D",
        status="success",
        composio_execution_id="6OnF6SGB8k8",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(YouTubeUploadJob(**defaults))
        await session.commit()
    return job_id


async def test_get_youtube_video_analytics_requires_a_connected_account(
    test_session_factory, db_session
):
    company_id = await _seed_company(test_session_factory)

    result = await tools.get_youtube_video_analytics(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert "isn't connected" in result


async def test_get_youtube_video_analytics_no_uploads_found(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                composio_connected_account_id="conn-yt-123",
            )
        )
        await session.commit()

    result = await tools.get_youtube_video_analytics(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert "No successfully uploaded YouTube videos" in result


async def test_get_youtube_video_analytics_reports_real_stats(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                composio_connected_account_id="conn-yt-123",
            )
        )
        await session.commit()
    await _seed_upload_job(test_session_factory, connection_id)

    captured = {}

    async def _fake_fetch(connection, video_ids):
        captured["video_ids"] = video_ids
        return [
            {
                "id": "6OnF6SGB8k8",
                "snippet": {"title": "Our YC Fall 2026 Application Journey", "publishedAt": "2026-08-09T08:09:00Z"},
                "statistics": {"viewCount": "142", "likeCount": "12", "commentCount": "3"},
            }
        ]

    monkeypatch.setattr(tools, "fetch_video_analytics", _fake_fetch)

    result = await tools.get_youtube_video_analytics(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert captured["video_ids"] == ["6OnF6SGB8k8"]
    assert "142 views" in result
    assert "12 likes" in result
    assert "3 comments" in result
    assert "Our YC Fall 2026 Application Journey" in result


async def test_get_youtube_video_analytics_filters_by_title(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                composio_connected_account_id="conn-yt-123",
            )
        )
        await session.commit()
    await _seed_upload_job(
        test_session_factory,
        connection_id,
        title="Our YC Fall 2026 Application Journey",
        composio_execution_id="6OnF6SGB8k8",
    )
    await _seed_upload_job(
        test_session_factory,
        connection_id,
        title="Birthday Wish To Disha",
        composio_execution_id="birthday123",
    )

    captured = {}

    async def _fake_fetch(connection, video_ids):
        captured["video_ids"] = video_ids
        return []

    monkeypatch.setattr(tools, "fetch_video_analytics", _fake_fetch)

    await tools.get_youtube_video_analytics(
        db_session, user=_USER, company_id=str(company_id), title="birthday"
    )

    assert captured["video_ids"] == ["birthday123"]


async def test_get_youtube_video_analytics_handles_fetch_failure(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                composio_connected_account_id="conn-yt-123",
            )
        )
        await session.commit()
    await _seed_upload_job(test_session_factory, connection_id)

    async def _fake_fetch(connection, video_ids):
        raise RuntimeError("Composio 500")

    monkeypatch.setattr(tools, "fetch_video_analytics", _fake_fetch)

    result = await tools.get_youtube_video_analytics(
        db_session, user=_USER, company_id=str(company_id)
    )

    assert "Couldn't fetch YouTube analytics" in result


async def _seed_published_item_with_attempt(
    test_session_factory, company_id, *, platform="linkedin", execution_id="urn:li:share:123"
):
    from datetime import datetime, timezone

    from app.db.models import PublishAttempt

    item_id = await _seed_content_item(
        test_session_factory,
        company_id,
        platform=platform,
        published_at=datetime.now(timezone.utc),
    )
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform=platform,
                status="connected",
                composio_connected_account_id="conn-123",
            )
        )
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


async def test_delete_content_item_post_deletes_and_clears_published_at(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_published_item_with_attempt(test_session_factory, company_id)

    captured = {}

    async def _fake_delete_post(connection, execution_id):
        captured["execution_id"] = execution_id

    monkeypatch.setattr(tools, "delete_post", _fake_delete_post)

    result = await tools.delete_content_item_post(db_session, content_item_id=str(item_id))

    assert "Deleted" in result
    assert captured["execution_id"] == "urn:li:share:123"

    from app.db.models import ContentItem

    refreshed = await db_session.get(ContentItem, item_id)
    assert refreshed.published_at is None


async def test_delete_content_item_post_uses_youtube_delete_for_youtube(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_published_item_with_attempt(
        test_session_factory, company_id, platform="youtube", execution_id="6OnF6SGB8k8"
    )

    captured = {}

    async def _fake_delete_youtube(connection, video_id):
        captured["video_id"] = video_id

    monkeypatch.setattr(tools, "delete_youtube_video", _fake_delete_youtube)

    result = await tools.delete_content_item_post(db_session, content_item_id=str(item_id))

    assert "Deleted" in result
    assert captured["video_id"] == "6OnF6SGB8k8"


async def test_delete_content_item_post_refuses_when_not_published(
    test_session_factory, db_session
):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(test_session_factory, company_id)  # published_at=None

    result = await tools.delete_content_item_post(db_session, content_item_id=str(item_id))

    assert "hasn't been published" in result


async def test_delete_content_item_post_surfaces_unsupported_platform(
    test_session_factory, db_session, monkeypatch
):
    """Instagram genuinely has no delete capability — confirmed live
    against Composio's real toolkit. Must surface a clear, honest
    message, not a generic failure."""
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_published_item_with_attempt(
        test_session_factory, company_id, platform="instagram", execution_id="media-1"
    )

    async def _fake_delete_post(connection, execution_id):
        raise DeleteNotSupportedError(
            "Instagram doesn't support deleting a post through this app."
        )

    monkeypatch.setattr(tools, "delete_post", _fake_delete_post)

    result = await tools.delete_content_item_post(db_session, content_item_id=str(item_id))

    assert "doesn't support deleting" in result


async def test_delete_content_item_post_without_a_successful_attempt_on_file(
    test_session_factory, db_session
):
    from datetime import datetime, timezone

    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(
        test_session_factory, company_id, published_at=datetime.now(timezone.utc)
    )

    result = await tools.delete_content_item_post(db_session, content_item_id=str(item_id))

    assert "Couldn't find a record" in result


async def test_publish_content_item_includes_the_real_post_link(
    test_session_factory, db_session, monkeypatch
):
    """A "Published" confirmation should actually link to the post, not
    just name the platform — the user has to go find it manually
    otherwise."""
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(
        test_session_factory, company_id, platform="linkedin", draft_copy="A real caption."
    )
    await _seed_youtube_connection(test_session_factory, company_id, platform="linkedin")

    async def _fake_publish_post(session, connection, text, media_url=None):
        return "urn:li:share:7493009415151738880"

    async def _fake_get_post_url(connection, execution_id):
        return f"https://www.linkedin.com/feed/update/{execution_id}/"

    monkeypatch.setattr(tools, "publish_post", _fake_publish_post)
    monkeypatch.setattr(tools, "get_post_url", _fake_get_post_url)

    result = await tools.publish_content_item(db_session, content_item_id=str(item_id))

    assert "https://www.linkedin.com/feed/update/urn:li:share:7493009415151738880/" in result


async def test_publish_content_item_still_succeeds_when_link_lookup_fails(
    test_session_factory, db_session, monkeypatch
):
    """get_post_url is best-effort by contract (never raises) — this
    confirms the tool doesn't fall over even if that contract were
    somehow violated, and a genuinely successful publish is never
    reported as a failure just because the link couldn't be found."""
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(
        test_session_factory, company_id, platform="linkedin", draft_copy="A real caption."
    )
    await _seed_youtube_connection(test_session_factory, company_id, platform="linkedin")

    async def _fake_publish_post(session, connection, text, media_url=None):
        return "urn:li:share:123"

    async def _fake_get_post_url(connection, execution_id):
        return None

    monkeypatch.setattr(tools, "publish_post", _fake_publish_post)
    monkeypatch.setattr(tools, "get_post_url", _fake_get_post_url)

    result = await tools.publish_content_item(db_session, content_item_id=str(item_id))

    assert "Published" in result
    assert "None" not in result


async def test_upload_youtube_video_tool_reports_immediate_success_with_a_real_link(
    test_session_factory, db_session, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    await _seed_youtube_connection(test_session_factory, company_id)

    async def _fake_enqueue(session, connection, video_url, title, description, tags=None, privacy_status="unlisted"):
        return SimpleNamespace(status="success", composio_execution_id="6OnF6SGB8k8", status_error=None)

    monkeypatch.setattr(tools, "enqueue_youtube_upload", _fake_enqueue)

    result = await tools.upload_youtube_video_tool(
        db_session,
        user=_USER,
        company_id=str(company_id),
        video_url="https://example.com/video.mp4",
        title="My Video",
        description="D",
    )

    assert "https://www.youtube.com/watch?v=6OnF6SGB8k8" in result
