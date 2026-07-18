"""Tests for the Competitor Research onboarding LangGraph pipeline."""

from __future__ import annotations

import uuid

from app.agents.competitor_research import graph as graph_module
from app.agents.company_analyzer.schemas import CompanyProfile, ScrapedPage
from app.db.models import Competitor


async def _stub_discover_and_scrape(base_url: str, *, max_pages: int):
    return [
        ScrapedPage(
            url=f"{base_url}/",
            title="Home",
            content="We build widgets for enterprise customers.",
        ),
    ]


async def _stub_extract_profile(content: str) -> tuple[CompanyProfile, bool]:
    return (
        CompanyProfile(
            name="Rival Widgets Inc",
            industry="Consumer goods",
            business_model="B2B subscription",
            target_audience="Enterprise buyers",
            brand_voice="Corporate and precise",
            unique_value_prop="Enterprise-grade widgets",
            summary="Rival Widgets makes enterprise widgets.",
        ),
        True,
    )


async def _stub_extract_profile_skipped(content: str) -> tuple[CompanyProfile, bool]:
    return CompanyProfile(), False


async def test_run_competitor_onboarding_persists_profile(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _stub_discover_and_scrape)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(id=competitor_id, company_id=company_id, url="https://rival.com", status="pending")
        )
        await session.commit()

    await graph_module.run_competitor_onboarding(competitor_id, "https://rival.com")

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, competitor_id)

    assert competitor.status == "complete"
    assert competitor.name == "Rival Widgets Inc"
    assert competitor.industry == "Consumer goods"


async def test_run_competitor_onboarding_marks_failed_when_no_pages_scraped(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _empty(base_url: str, *, max_pages: int):
        return []

    monkeypatch.setattr(graph_module, "discover_and_scrape", _empty)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(
                id=competitor_id, company_id=company_id, url="https://bad.example.com", status="pending"
            )
        )
        await session.commit()

    await graph_module.run_competitor_onboarding(competitor_id, "https://bad.example.com")

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, competitor_id)

    assert competitor.status == "failed"
    assert competitor.status_error is not None


async def test_run_competitor_onboarding_marks_complete_no_profile_when_extraction_skipped(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _stub_discover_and_scrape)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile_skipped)

    company_id = uuid.uuid4()
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(id=competitor_id, company_id=company_id, url="https://rival.com", status="pending")
        )
        await session.commit()

    await graph_module.run_competitor_onboarding(competitor_id, "https://rival.com")

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, competitor_id)

    assert competitor.status == "complete_no_profile"
    assert competitor.status_error is not None
    assert competitor.name is None
