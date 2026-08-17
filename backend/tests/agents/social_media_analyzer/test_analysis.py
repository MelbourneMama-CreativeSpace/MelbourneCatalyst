"""Tests for the Analysis aggregation layer (build_overview / generate_insight)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.agents.social_media_analyzer import analysis as analysis_module
from app.agents.social_media_analyzer.analysis import (
    build_overview,
    generate_insight,
    get_or_generate_insight,
)
from app.db.models import AnalysisInsightCache, Company, ContentItem, ContentPlan, PostMetricSnapshot

_NOW = datetime.now(timezone.utc)


async def _seed_company(session, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id,
        url=f"https://example.com/{company_id}",
        status="complete",
        name="Acme",
        owner_id="test-user-id",
    )
    defaults.update(overrides)
    session.add(Company(**defaults))
    await session.flush()
    return company_id


async def _seed_plan(session, company_id: uuid.UUID) -> uuid.UUID:
    plan_id = uuid.uuid4()
    session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
    await session.flush()
    return plan_id


async def _seed_item(
    session,
    plan_id: uuid.UUID,
    *,
    platform: str = "instagram",
    content_type: str = "image_post",
    theme: str | None = "launch",
    published_at: datetime | None = _NOW,
    approval_status: str = "approved",
) -> uuid.UUID:
    item_id = uuid.uuid4()
    session.add(
        ContentItem(
            id=item_id,
            content_plan_id=plan_id,
            title="Item",
            description="Desc",
            content_type=content_type,
            platform=platform,
            theme=theme,
            suggested_date=date.today(),
            approval_status=approval_status,
            published_at=published_at,
        )
    )
    await session.flush()
    return item_id


async def _seed_snapshot(
    session,
    item_id: uuid.UUID,
    *,
    likes: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
    saves: int | None = None,
    views: int | None = None,
    reach: int | None = None,
) -> None:
    session.add(
        PostMetricSnapshot(
            content_item_id=item_id,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            views=views,
            reach=reach,
        )
    )
    await session.flush()


async def test_build_overview_empty_company_has_no_metrics(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.posts_published == 0
    assert overview.metrics_available is False
    assert overview.current_totals.engagement == 0
    assert overview.by_platform == []
    assert overview.best_platform is None


async def test_build_overview_totals_and_breakdowns(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        plan_id = await _seed_plan(session, company_id)

        ig_item = await _seed_item(session, plan_id, platform="instagram", content_type="reel")
        fb_item = await _seed_item(session, plan_id, platform="facebook", content_type="image_post")
        await _seed_snapshot(session, ig_item, likes=100, comments=10, shares=5, saves=20, reach=1000)
        await _seed_snapshot(session, fb_item, likes=10, comments=1, shares=0)
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.posts_published == 2
    assert overview.metrics_available is True
    # instagram: 100+10+5+20 = 135, facebook: 10+1+0 = 11
    assert overview.current_totals.engagement == 146
    assert overview.current_totals.reach == 1000

    by_platform = {row.key: row for row in overview.by_platform}
    assert by_platform["instagram"].total_engagement == 135
    assert by_platform["facebook"].total_engagement == 11
    assert overview.best_platform == "instagram"
    assert overview.worst_platform == "facebook"


async def test_build_overview_ignores_unpublished_and_out_of_window_items(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        plan_id = await _seed_plan(session, company_id)

        # Unpublished — must not count at all.
        await _seed_item(session, plan_id, published_at=None, approval_status="pending")
        # Published, but 60 days ago — outside a 30-day window entirely.
        old_item = await _seed_item(session, plan_id, published_at=_NOW - timedelta(days=60))
        await _seed_snapshot(session, old_item, likes=500)
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.posts_published == 0
    assert overview.current_totals.posts == 0


async def test_build_overview_previous_period_and_pct_change(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        plan_id = await _seed_plan(session, company_id)

        current_item = await _seed_item(session, plan_id, published_at=_NOW - timedelta(days=5))
        await _seed_snapshot(session, current_item, likes=200)

        previous_item = await _seed_item(session, plan_id, published_at=_NOW - timedelta(days=40))
        await _seed_snapshot(session, previous_item, likes=100)
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.current_totals.engagement == 200
    assert overview.previous_totals.engagement == 100
    assert overview.engagement_change_pct == 100.0


async def test_build_overview_counts_rejected_unpublished_items_as_failed(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        plan_id = await _seed_plan(session, company_id)
        await _seed_item(session, plan_id, published_at=None, approval_status="rejected")
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.posts_failed == 1


async def test_build_overview_uses_latest_snapshot_only(test_session_factory):
    """Multiple snapshots accumulate for one item — only the most recent
    should feed the totals, never a sum across every historical fetch."""
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        plan_id = await _seed_plan(session, company_id)
        item_id = await _seed_item(session, plan_id)

        session.add(
            PostMetricSnapshot(
                content_item_id=item_id,
                likes=10,
                captured_at=_NOW - timedelta(hours=2),
            )
        )
        session.add(
            PostMetricSnapshot(
                content_item_id=item_id,
                likes=50,
                captured_at=_NOW,
            )
        )
        await session.commit()

        overview = await build_overview(session, company_id, period_days=30)

    assert overview.current_totals.engagement == 50


async def test_generate_insight_returns_empty_without_api_key(test_session_factory, monkeypatch):
    monkeypatch.setattr(analysis_module.settings, "ANTHROPIC_API_KEY", "")
    overview = analysis_module.AnalysisOverview(
        company_id=uuid.uuid4(),
        period_days=30,
        posts_published=5,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(),
        previous_totals=analysis_module.MetricTotals(),
        reach_change_pct=None,
        engagement_change_pct=None,
    )
    why, recommendations = await generate_insight(overview)
    assert why is None
    assert recommendations == []


async def test_generate_insight_returns_empty_when_no_posts(monkeypatch):
    monkeypatch.setattr(analysis_module.settings, "ANTHROPIC_API_KEY", "test-key")
    overview = analysis_module.AnalysisOverview(
        company_id=uuid.uuid4(),
        period_days=30,
        posts_published=0,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(),
        previous_totals=analysis_module.MetricTotals(),
        reach_change_pct=None,
        engagement_change_pct=None,
    )
    why, recommendations = await generate_insight(overview)
    assert why is None
    assert recommendations == []


async def test_generate_insight_parses_forced_tool_call(monkeypatch):
    monkeypatch.setattr(analysis_module.settings, "ANTHROPIC_API_KEY", "test-key")
    overview = analysis_module.AnalysisOverview(
        company_id=uuid.uuid4(),
        period_days=30,
        posts_published=3,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(posts=3, engagement=100),
        previous_totals=analysis_module.MetricTotals(posts=1, engagement=50),
        reach_change_pct=None,
        engagement_change_pct=100.0,
    )

    tool_block = type(
        "ToolBlock", (), {"type": "tool_use", "input": {"why": "Reels outperformed", "recommendations": ["Post more reels"]}}
    )()
    fake_response = type("Resp", (), {"stop_reason": "tool_use", "content": [tool_block]})()

    with patch.object(analysis_module, "_client") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(return_value=fake_response)
        why, recommendations = await generate_insight(overview)

    assert why == "Reels outperformed"
    assert recommendations == ["Post more reels"]


async def test_generate_insight_returns_empty_on_max_tokens_truncation(monkeypatch):
    monkeypatch.setattr(analysis_module.settings, "ANTHROPIC_API_KEY", "test-key")
    overview = analysis_module.AnalysisOverview(
        company_id=uuid.uuid4(),
        period_days=30,
        posts_published=3,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(posts=3, engagement=100),
        previous_totals=analysis_module.MetricTotals(),
        reach_change_pct=None,
        engagement_change_pct=None,
    )
    fake_response = type("Resp", (), {"stop_reason": "max_tokens", "content": []})()

    with patch.object(analysis_module, "_client") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(return_value=fake_response)
        why, recommendations = await generate_insight(overview)

    assert why is None
    assert recommendations == []


async def test_generate_insight_never_raises_on_api_failure(monkeypatch):
    monkeypatch.setattr(analysis_module.settings, "ANTHROPIC_API_KEY", "test-key")
    overview = analysis_module.AnalysisOverview(
        company_id=uuid.uuid4(),
        period_days=30,
        posts_published=3,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(posts=3, engagement=100),
        previous_totals=analysis_module.MetricTotals(),
        reach_change_pct=None,
        engagement_change_pct=None,
    )

    with patch.object(analysis_module, "_client") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        why, recommendations = await generate_insight(overview)

    assert why is None
    assert recommendations == []


# --- get_or_generate_insight — memoized per (company, period_days) --------


def _overview_for(company_id: uuid.UUID, period_days: int = 30) -> analysis_module.AnalysisOverview:
    return analysis_module.AnalysisOverview(
        company_id=company_id,
        period_days=period_days,
        posts_published=3,
        posts_failed=0,
        current_totals=analysis_module.MetricTotals(posts=3, engagement=100),
        previous_totals=analysis_module.MetricTotals(),
        reach_change_pct=None,
        engagement_change_pct=None,
    )


async def test_get_or_generate_insight_generates_and_persists_on_first_call(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        await session.commit()

        overview = _overview_for(company_id)
        fake_generate = AsyncMock(return_value=("Why it happened", ["Do this next"]))
        with patch.object(analysis_module, "generate_insight", fake_generate):
            why, recommendations = await get_or_generate_insight(session, overview)

        assert why == "Why it happened"
        assert recommendations == ["Do this next"]
        fake_generate.assert_awaited_once()

        rows = (
            (await session.execute(select(AnalysisInsightCache)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].company_id == company_id
        assert rows[0].period_days == 30
        assert rows[0].ai_why == "Why it happened"


async def test_get_or_generate_insight_returns_cached_value_within_ttl(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        await session.commit()

        overview = _overview_for(company_id)
        first_call = AsyncMock(return_value=("First answer", ["First rec"]))
        with patch.object(analysis_module, "generate_insight", first_call):
            await get_or_generate_insight(session, overview)

        second_call = AsyncMock(return_value=("Second answer", ["Second rec"]))
        with patch.object(analysis_module, "generate_insight", second_call):
            why, recommendations = await get_or_generate_insight(session, overview)

        # Still the first answer — the second (mocked) Claude call never
        # actually ran, since the cache was fresh.
        assert why == "First answer"
        assert recommendations == ["First rec"]
        second_call.assert_not_awaited()


async def test_get_or_generate_insight_regenerates_after_ttl_expires(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        await session.commit()

        session.add(
            AnalysisInsightCache(
                company_id=company_id,
                period_days=30,
                ai_why="Stale answer",
                ai_recommendations=["Stale rec"],
                generated_at=_NOW - timedelta(minutes=analysis_module.settings.POST_METRICS_SYNC_INTERVAL_MINUTES + 1),
            )
        )
        await session.commit()

        overview = _overview_for(company_id)
        fresh_call = AsyncMock(return_value=("Fresh answer", ["Fresh rec"]))
        with patch.object(analysis_module, "generate_insight", fresh_call):
            why, recommendations = await get_or_generate_insight(session, overview)

        assert why == "Fresh answer"
        assert recommendations == ["Fresh rec"]
        fresh_call.assert_awaited_once()

        # Overwritten in place — still exactly one row for this company/period.
        rows = (
            (await session.execute(select(AnalysisInsightCache)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].ai_why == "Fresh answer"


async def test_get_or_generate_insight_scopes_cache_by_period_days(test_session_factory):
    async with test_session_factory() as session:
        company_id = await _seed_company(session)
        await session.commit()

        with patch.object(
            analysis_module, "generate_insight", AsyncMock(return_value=("30-day answer", []))
        ):
            await get_or_generate_insight(session, _overview_for(company_id, period_days=30))

        # A different period_days for the same company is a cache miss,
        # not accidentally served the 30-day answer.
        ninety_day_call = AsyncMock(return_value=("90-day answer", []))
        with patch.object(analysis_module, "generate_insight", ninety_day_call):
            why, _ = await get_or_generate_insight(session, _overview_for(company_id, period_days=90))

        assert why == "90-day answer"
        ninety_day_call.assert_awaited_once()
