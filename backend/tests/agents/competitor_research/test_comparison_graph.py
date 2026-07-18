"""Tests for the Comparison LangGraph pipeline."""

from __future__ import annotations

import uuid

from app.agents.competitor_research import comparison_graph as graph_module
from app.agents.competitor_research.schemas import GeneratedComparison
from app.db.models import Company, Competitor


async def _stub_generate_comparison(context: str):
    return (
        GeneratedComparison(
            product_pricing_comparison="Comparable pricing.",
            marketing_strategy_analysis="Competitor leans on case studies.",
            competitive_gaps="No enterprise tier yet.",
            strategic_recommendations="Build an enterprise tier.",
        ),
        True,
    )


async def _stub_generate_comparison_failed(context: str):
    return GeneratedComparison(), False


async def test_run_comparison_generation_persists_a_complete_comparison(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_comparison", _stub_generate_comparison)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Competitor(
                id=competitor_id,
                company_id=company_id,
                url="https://rival.com",
                status="complete",
                name="Rival Co",
            )
        )
        await session.commit()

    await graph_module.run_comparison_generation(competitor_id, company_id)

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, competitor_id)

    assert competitor.comparison_status == "complete"
    assert competitor.competitive_gaps == "No enterprise tier yet."


async def test_run_comparison_generation_includes_both_profiles_in_context(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str):
        captured_context["value"] = context
        return GeneratedComparison(), True

    monkeypatch.setattr(graph_module, "generate_comparison", _capturing_generate)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url="https://example.com",
                status="complete",
                name="Acme",
                summary="Acme makes widgets.",
            )
        )
        session.add(
            Competitor(
                id=competitor_id,
                company_id=company_id,
                url="https://rival.com",
                status="complete",
                name="Rival Co",
                summary="Rival makes enterprise widgets.",
            )
        )
        await session.commit()

    await graph_module.run_comparison_generation(competitor_id, company_id)

    assert "Acme makes widgets." in captured_context["value"]
    assert "Rival makes enterprise widgets." in captured_context["value"]


async def test_run_comparison_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_comparison", _stub_generate_comparison_failed)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(
            Competitor(id=competitor_id, company_id=company_id, url="https://rival.com", status="complete")
        )
        await session.commit()

    await graph_module.run_comparison_generation(competitor_id, company_id)

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, competitor_id)

    assert competitor.comparison_status == "failed"
    assert competitor.comparison_status_error is not None


async def test_run_comparison_generation_marks_failed_when_competitor_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_comparison", _stub_generate_comparison)

    company_id = uuid.uuid4()
    missing_competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        await session.commit()

    # Should not raise — persist node handles the missing row defensively.
    await graph_module.run_comparison_generation(missing_competitor_id, company_id)
