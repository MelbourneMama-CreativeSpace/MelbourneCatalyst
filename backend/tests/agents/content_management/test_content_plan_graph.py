"""Tests for the Content Planner LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.agents.content_management import content_plan_graph as graph_module
from app.agents.content_management.schemas import GeneratedContentItem, GeneratedContentPlan
from app.db.models import Company, ContentItem, ContentPlan, Strategy, Trend


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
    assert by_title["No trend tie-in post"].audience_interest is None
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
