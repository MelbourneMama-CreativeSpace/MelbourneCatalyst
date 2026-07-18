"""Tests for the Strategy Consultant LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.agents.content_management import strategy_graph as graph_module
from app.agents.content_management.schemas import GeneratedStrategy
from app.db.models import Company, Strategy, Trend


async def _stub_generate_strategy(context: str):
    return (
        GeneratedStrategy(
            summary="Focus on AI-native positioning.",
            marketing_strategy="Lead with automation benefits.",
            campaign_direction="Short-form demo videos.",
            growth_recommendations="Invest in SEO content.",
            business_suggestions="Consider a freemium tier.",
        ),
        True,
    )


async def _stub_generate_strategy_failed(context: str):
    return GeneratedStrategy(), False


async def test_run_strategy_generation_persists_a_complete_strategy(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_strategy", _stub_generate_strategy)

    company_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url="https://example.com",
                status="complete",
                name="Example Co",
                niche_keywords=["widgets"],
            )
        )
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="AI marketing tools trending",
                url="https://example.com/trend",
                relevance_score=0.9,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        session.add(Strategy(id=strategy_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_strategy_generation(strategy_id, company_id)

    async with test_session_factory() as session:
        strategy = await session.get(Strategy, strategy_id)

    assert strategy.status == "complete"
    assert strategy.summary == "Focus on AI-native positioning."
    assert strategy.business_suggestions == "Consider a freemium tier."


async def test_run_strategy_generation_marks_failed_when_generation_fails(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_strategy", _stub_generate_strategy_failed)

    company_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(Strategy(id=strategy_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_strategy_generation(strategy_id, company_id)

    async with test_session_factory() as session:
        strategy = await session.get(Strategy, strategy_id)

    assert strategy.status == "failed"
    assert strategy.status_error is not None


async def test_run_strategy_generation_marks_failed_when_company_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_strategy", _stub_generate_strategy)

    strategy_id = uuid.uuid4()
    missing_company_id = uuid.uuid4()
    async with test_session_factory() as session:
        # Strategy row exists (created by the API layer) but points at a
        # company that's gone — the graph's defensive check should handle
        # this rather than crashing.
        session.add(Strategy(id=strategy_id, company_id=missing_company_id, status="pending"))
        await session.commit()

    await graph_module.run_strategy_generation(strategy_id, missing_company_id)

    async with test_session_factory() as session:
        strategy = await session.get(Strategy, strategy_id)

    assert strategy.status == "failed"
    assert strategy.status_error == "Company not found"


async def test_gather_context_includes_top_relevant_trends(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Relevant trend",
                url="https://example.com/a",
                relevance_score=0.8,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Irrelevant trend",
                url="https://example.com/b",
                relevance_score=None,
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    update = await graph_module._gather_context_node(
        {"company_id": company_id, "strategy_id": uuid.uuid4(), "context": "", "generated": None, "status": "pending", "status_error": None}
    )

    assert "Relevant trend" in update["context"]
    assert "Irrelevant trend" not in update["context"]
    assert "Acme" in update["context"]
