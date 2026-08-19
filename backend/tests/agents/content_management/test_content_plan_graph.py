"""Tests for the Content Planner LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.agents.content_management import content_plan_graph as graph_module
from app.agents.content_management.schemas import GeneratedContentItem, GeneratedContentPlan
from app.db.models import (
    Company,
    CompanyTrendRelevance,
    ContentItem,
    ContentItemRevision,
    ContentPlan,
    Strategy,
    Trend,
)


async def _stub_generate_content_plan(context: str, days: int):
    return (
        GeneratedContentPlan(
            items=[
                GeneratedContentItem(
                    title="AI marketing carousel",
                    description="5 slides on AI-native marketing.",
                    content_type="carousel",
                    platform="instagram",
                    suggested_date=date.today(),
                    theme="AI trends",
                    related_trend_title="AI marketing tools trending",
                    audience_interest="tech-forward marketers",
                    seasonal_event="Christmas (2026-12-25)",
                    draft_copy="Slide 1: AI marketing tools are moving fast. Here's what to know →",
                    hashtags=["aimarketing", "smallbusiness"],
                ),
                GeneratedContentItem(
                    title="No trend tie-in post",
                    description="Evergreen tip.",
                    content_type="post",
                    platform="linkedin",
                    suggested_date=date.today(),
                    related_trend_title=None,
                ),
            ]
        ),
        True,
    )


async def _stub_generate_content_plan_failed(context: str, days: int):
    return GeneratedContentPlan(), False


async def test_run_content_plan_generation_persists_items_with_resolved_trend_id(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_content_plan", _stub_generate_content_plan)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="AI marketing tools trending",
                url="https://example.com/trend",
                relevance_score=0.9,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    async with test_session_factory() as session:
        plan = await session.get(ContentPlan, plan_id)
        items = (
            await session.execute(select(ContentItem).where(ContentItem.content_plan_id == plan_id))
        ).scalars().all()

    assert plan.status == "complete"
    assert len(items) == 2
    by_title = {item.title: item for item in items}
    assert by_title["AI marketing carousel"].source_trend_id == trend_id
    assert by_title["No trend tie-in post"].source_trend_id is None
    assert by_title["AI marketing carousel"].audience_interest == "tech-forward marketers"
    assert by_title["AI marketing carousel"].seasonal_event == "Christmas (2026-12-25)"
    assert (
        by_title["AI marketing carousel"].draft_copy
        == "Slide 1: AI marketing tools are moving fast. Here's what to know →"
    )
    assert by_title["No trend tie-in post"].draft_copy is None
    assert by_title["No trend tie-in post"].audience_interest is None
    assert by_title["AI marketing carousel"].hashtags == ["aimarketing", "smallbusiness"]
    assert by_title["No trend tie-in post"].hashtags is None
    # Every freshly generated item starts in the approval workflow's
    # default state, regardless of what Claude returned.
    assert all(item.approval_status == "pending" for item in items)


async def test_run_content_plan_generation_includes_strategy_context(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str, days: int):
        captured_context["value"] = context
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Strategy(
                id=strategy_id,
                company_id=company_id,
                status="complete",
                summary="Go all-in on AI positioning.",
                marketing_strategy="Lead with automation.",
            )
        )
        session.add(ContentPlan(id=plan_id, company_id=company_id, strategy_id=strategy_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, strategy_id)

    assert "Go all-in on AI positioning." in captured_context["value"]
    assert "Lead with automation." in captured_context["value"]


async def test_run_content_plan_generation_passes_days_override_through(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_days = {}

    async def _capturing_generate(context: str, days: int):
        captured_days["value"] = days
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None, days=30)

    assert captured_days["value"] == 30


async def test_run_content_plan_generation_defaults_days_when_not_given(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_days = {}

    async def _capturing_generate(context: str, days: int):
        captured_days["value"] = days
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    from app.config import settings

    assert captured_days["value"] == settings.CONTENT_PLAN_DAYS


async def test_run_content_plan_generation_includes_niche_keywords_context(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str, days: int):
        captured_context["value"] = context
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url="https://example.com",
                status="complete",
                niche_keywords=["parenting", "creative workshops"],
            )
        )
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    assert "parenting" in captured_context["value"]
    assert "creative workshops" in captured_context["value"]


async def test_run_content_plan_generation_prefers_per_company_trend_relevance(
    monkeypatch, test_session_factory
):
    """With more than one company onboarded, the legacy global
    Trend.relevance_score reflects whichever company was scored last — not
    necessarily this one. When this company has its own scored rows in
    CompanyTrendRelevance, those must win over the legacy column."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str, days: int):
        captured_context["value"] = context
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="Trend scored differently per company",
                url="https://example.com/trend",
                # The legacy global score belongs to some other company —
                # deliberately different from this company's own score below,
                # so the test can tell which one actually made it into context.
                relevance_score=0.10,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CompanyTrendRelevance(
                id=uuid.uuid4(), company_id=company_id, trend_id=trend_id, relevance_score=0.95
            )
        )
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    assert "relevance: 0.95" in captured_context["value"]
    assert "relevance: 0.10" not in captured_context["value"]


async def test_run_content_plan_generation_falls_back_to_legacy_relevance_when_uncored_for_company(
    monkeypatch, test_session_factory
):
    """A company with no rows in CompanyTrendRelevance yet (e.g. onboarded
    after the last collection run) must still see trends, via the legacy
    global score, rather than getting none at all."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str, days: int):
        captured_context["value"] = context
        return GeneratedContentPlan(), True

    monkeypatch.setattr(graph_module, "generate_content_plan", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Only has a legacy score",
                url="https://example.com/legacy-only",
                relevance_score=0.6,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    assert "Only has a legacy score" in captured_context["value"]
    assert "relevance: 0.60" in captured_context["value"]


async def test_run_content_plan_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_content_plan", _stub_generate_content_plan_failed)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_content_plan_generation(plan_id, company_id, None)

    async with test_session_factory() as session:
        plan = await session.get(ContentPlan, plan_id)
        items = (
            await session.execute(select(ContentItem).where(ContentItem.content_plan_id == plan_id))
        ).scalars().all()

    assert plan.status == "failed"
    assert plan.status_error is not None
    assert items == []


async def _stub_generate_content_item(context: str, user_input: str, platform: str, content_type: str):
    return (
        GeneratedContentItem(
            title="Generated post",
            description="A post.",
            content_type=content_type,
            platform=platform,
            suggested_date=date.today(),
            draft_copy="Ready-to-publish caption.",
        ),
        True,
    )


async def test_create_manual_item_includes_ambient_relevant_trends_in_context(
    monkeypatch, test_session_factory
):
    """Regression test for a real bug: create_manual_item — the single-
    post path both the chat agent's create_content_item tool and the
    manual-item form use — hardcoded an empty trends list, even though
    the exact same relevance-scored trend data was already being used for
    the bulk content-plan generator. A chat-written post had zero trend
    awareness as a result."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured = {}

    async def _capture(context: str, user_input: str, platform: str, content_type: str):
        captured["context"] = context
        return await _stub_generate_content_item(context, user_input, platform, content_type)

    monkeypatch.setattr(graph_module, "generate_content_item_from_input", _capture)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="AI marketing tools trending",
                insight="Marketers are automating campaign copy end to end.",
                url="https://example.com/trend",
                relevance_score=0.9,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    item, ok = await graph_module.create_manual_item(company_id, "a launch post", "linkedin", "post")

    assert ok is True
    assert "AI marketing tools trending" in captured["context"]
    assert "Marketers are automating campaign copy end to end." in captured["context"]


async def test_create_manual_item_with_explicit_trend_id_links_and_steers_generation(
    monkeypatch, test_session_factory
):
    """A trend explicitly picked by the user (e.g. off list_trending_topics)
    must actually center the generation, not just ride along as one of
    several ambient trends, and the resulting item must stay linked back
    to it — same linkage run_content_plan_generation already gives its
    own trend-inspired items."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured = {}

    async def _capture(context: str, user_input: str, platform: str, content_type: str):
        captured["context"] = context
        captured["user_input"] = user_input
        return await _stub_generate_content_item(context, user_input, platform, content_type)

    monkeypatch.setattr(graph_module, "generate_content_item_from_input", _capture)

    company_id = uuid.uuid4()
    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="Niche micro-trend nobody else covers",
                insight="A small but highly engaged community is forming around this.",
                url="https://example.com/trend",
                # Deliberately low — must still be included/emphasized
                # because it was explicitly requested, not because it
                # would have made the ambient top-N cut on relevance
                # alone.
                relevance_score=0.01,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    item, ok = await graph_module.create_manual_item(
        company_id, "write something viral", "linkedin", "post", trend_id=trend_id
    )

    assert ok is True
    assert item.source_trend_id == trend_id
    assert "Niche micro-trend nobody else covers" in captured["context"]
    assert "specifically inspired by the trend" in captured["user_input"]
    assert "A small but highly engaged community is forming around this." in captured["user_input"]


async def test_create_manual_item_with_unknown_trend_id_degrades_gracefully(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_content_item_from_input", _stub_generate_content_item)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        await session.commit()

    item, ok = await graph_module.create_manual_item(
        company_id, "a post", "linkedin", "post", trend_id=uuid.uuid4()
    )

    assert ok is True
    assert item.source_trend_id is None


def test_format_context_includes_trend_insight_not_just_title():
    """Regression test: `insight` (why a trend matters, not just its
    title) used to be dropped entirely from generation context — the
    actual substance worth writing content around."""
    company = Company(id=uuid.uuid4(), url="https://example.com", name="Acme", status="complete")
    trend = Trend(
        id=uuid.uuid4(),
        source="rss",
        title="A trending topic",
        insight="This matters because of X.",
        url="https://example.com/trend",
        raw_metadata={},
        discovered_at=datetime.now(timezone.utc),
    )

    context = graph_module.format_context(company, None, [(trend, 0.8)], None)

    assert "A trending topic" in context
    assert "This matters because of X." in context


async def test_regenerate_item_draft_copy_updates_the_item(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _stub_regenerate(context: str, title: str, description: str, content_type: str, platform: str):
        return "A brand new caption ready to post.", True

    monkeypatch.setattr(graph_module, "regenerate_draft_copy", _stub_regenerate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Old title",
                description="Old brief",
                content_type="post",
                platform="instagram",
                suggested_date=date.today(),
                draft_copy="Stale draft.",
                approval_status="pending",
            )
        )
        await session.commit()

    item, ok = await graph_module.regenerate_item_draft_copy(item_id)

    assert ok is True
    assert item.draft_copy == "A brand new caption ready to post."

    async with test_session_factory() as session:
        persisted = await session.get(ContentItem, item_id)
    assert persisted.draft_copy == "A brand new caption ready to post."

    # The pre-regeneration draft is snapshotted, not silently discarded.
    async with test_session_factory() as session:
        revisions = (
            (
                await session.execute(
                    select(ContentItemRevision).where(
                        ContentItemRevision.content_item_id == item_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(revisions) == 1
    assert revisions[0].draft_copy == "Stale draft."
    assert revisions[0].edited_by == "AI regeneration"


async def test_regenerate_item_draft_copy_returns_none_for_unknown_item(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    item, ok = await graph_module.regenerate_item_draft_copy(uuid.uuid4())

    assert item is None
    assert ok is False


async def test_regenerate_item_draft_copy_leaves_item_unchanged_on_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _stub_regenerate_failing(
        context: str, title: str, description: str, content_type: str, platform: str
    ):
        return None, False

    monkeypatch.setattr(graph_module, "regenerate_draft_copy", _stub_regenerate_failing)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Title",
                description="Brief",
                content_type="post",
                platform="instagram",
                suggested_date=date.today(),
                draft_copy="Original draft, should survive a failed regeneration.",
                approval_status="pending",
            )
        )
        await session.commit()

    item, ok = await graph_module.regenerate_item_draft_copy(item_id)

    assert ok is False
    assert item.draft_copy == "Original draft, should survive a failed regeneration."


# --- inspired_by_handle: content about an external account -----------------
#
# Real bug: "give me a reel idea for @other_handle" used to pull this
# company's own profile/brand-voice/KB into the generation context and
# persist the result as indistinguishable from this company's own organic
# content — publishable through this company's own connected accounts.


def test_format_reference_context_excludes_company_profile_entirely():
    context = graph_module.format_reference_context("@melbournemamaaus", [])

    assert "@melbournemamaaus" in context
    assert "Company Profile" not in context
    assert "Brand voice" not in context
    assert "Industry" not in context


async def test_create_manual_item_with_inspired_by_handle_skips_company_kb_and_trends(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_content_item_from_input", _stub_generate_content_item)

    kb_calls = []

    async def _spy_fetch_kb_references(session, company_id, query, *, k=3):
        kb_calls.append(company_id)
        return []

    monkeypatch.setattr(graph_module, "fetch_kb_references", _spy_fetch_kb_references)

    trend_calls = []

    async def _spy_fetch_scored_trends(session, company_id, *, limit):
        trend_calls.append(company_id)
        return []

    monkeypatch.setattr(graph_module, "fetch_scored_trends", _spy_fetch_scored_trends)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url="https://example.com",
                status="complete",
                name="Mindfries",
                brand_voice="Confident and technical",
            )
        )
        await session.commit()

    item, ok = await graph_module.create_manual_item(
        company_id,
        "a reel idea",
        "youtube",
        "reel",
        inspired_by_handle="@melbournemamaaus",
    )

    assert ok is True
    assert item.inspired_by_handle == "@melbournemamaaus"
    # The real fix: this company's own KB search and ambient trend
    # scoring must not even be attempted for reference content — not
    # just "happen to return nothing useful this time".
    assert kb_calls == []
    assert trend_calls == []


async def test_create_manual_item_with_inspired_by_handle_keeps_explicit_trend_id(
    monkeypatch, test_session_factory
):
    """An explicit trend_id (the user picked a real trend off
    find_trending_topics_for_niche) is a specific choice, not ambient
    company-scoped context — it must still apply even when
    inspired_by_handle skips the ambient company trend scoring."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured = {}

    async def _capture(context: str, user_input: str, platform: str, content_type: str):
        captured["context"] = context
        return await _stub_generate_content_item(context, user_input, platform, content_type)

    monkeypatch.setattr(graph_module, "generate_content_item_from_input", _capture)

    company_id = uuid.uuid4()
    trend_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=trend_id,
                source="rss",
                title="Creator economy tools trending",
                url="https://example.com/trend",
                relevance_score=0.8,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    item, ok = await graph_module.create_manual_item(
        company_id,
        "a reel idea",
        "youtube",
        "reel",
        trend_id=trend_id,
        inspired_by_handle="@melbournemamaaus",
    )

    assert ok is True
    assert item.source_trend_id == trend_id
    assert "Creator economy tools trending" in captured["context"]
    assert "Company Profile" not in captured["context"]
