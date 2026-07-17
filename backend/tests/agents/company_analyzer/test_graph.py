"""Tests for the Company Analyzer LangGraph onboarding pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.company_analyzer import graph as graph_module
from app.agents.company_analyzer.schemas import CompanyProfile, ScrapedPage
from app.db.models import Company, Document


async def _stub_discover_and_scrape(base_url: str, *, max_pages: int):
    return [
        ScrapedPage(
            url=f"{base_url}/",
            title="Home",
            content="We build widgets. Our team of experts serves marketers.",
        ),
        ScrapedPage(
            url=f"{base_url}/about",
            title="About",
            content="Founded 2020. Based in Melbourne. Our mission is quality widgets.",
        ),
    ]


async def _stub_embed_documents(texts):
    # 1024-dim to match EMBEDDING_DIM; content of the vector doesn't matter
    # here — the ORM just stores it.
    return [[0.1] * 1024 for _ in texts]


async def _stub_extract_profile(content: str) -> CompanyProfile:
    return CompanyProfile(
        name="Widget Co",
        industry="Consumer goods",
        business_model="DTC subscription",
        target_audience="Small business marketers",
        brand_voice="Friendly and confident",
        unique_value_prop="Best widgets in the world",
        niche_keywords=["widgets", "small business", "marketing tools"],
        summary="Widget Co makes the best widgets for marketers.",
    )


async def test_run_onboarding_persists_company_profile_and_documents(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _stub_discover_and_scrape)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="pending"))
        await session.commit()

    await graph_module.run_onboarding(company_id, "https://example.com")

    async with test_session_factory() as session:
        company = await session.get(Company, company_id)
        docs = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()

    assert company.status == "complete"
    assert company.name == "Widget Co"
    assert company.niche_keywords == ["widgets", "small business", "marketing tools"]
    assert len(docs) >= 2  # at least one chunk per page


async def test_run_onboarding_marks_failed_when_no_pages_scraped(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _empty(base_url: str, *, max_pages: int):
        return []

    monkeypatch.setattr(graph_module, "discover_and_scrape", _empty)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://bad.example.com", status="pending"))
        await session.commit()

    await graph_module.run_onboarding(company_id, "https://bad.example.com")

    async with test_session_factory() as session:
        company = await session.get(Company, company_id)

    assert company.status == "failed"
    assert company.status_error is not None
