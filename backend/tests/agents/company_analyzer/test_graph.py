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


async def _stub_extract_profile(content: str) -> tuple[CompanyProfile, bool]:
    return (
        CompanyProfile(
            name="Widget Co",
            industry="Consumer goods",
            business_model="DTC subscription",
            target_audience="Small business marketers",
            brand_voice="Friendly and confident",
            unique_value_prop="Best widgets in the world",
            niche_keywords=["widgets", "small business", "marketing tools"],
            summary="Widget Co makes the best widgets for marketers.",
            products_and_services=["Widget subscription box", "Custom widget consulting"],
        ),
        True,
    )


async def _stub_extract_profile_skipped(content: str) -> tuple[CompanyProfile, bool]:
    return CompanyProfile(), False


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
    assert company.products_and_services == ["Widget subscription box", "Custom widget consulting"]
    assert len(docs) >= 2  # at least one chunk per page


async def test_run_onboarding_tags_product_pages_distinctly(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _pages_with_a_product_page(base_url: str, *, max_pages: int):
        return [
            ScrapedPage(url=f"{base_url}/", title="Home", content="We build widgets for everyone."),
            ScrapedPage(
                url=f"{base_url}/products",
                title="Products",
                content="Widget Pro: $49. Widget Mini: $19. Both ship worldwide.",
            ),
        ]

    monkeypatch.setattr(graph_module, "discover_and_scrape", _pages_with_a_product_page)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="pending"))
        await session.commit()

    await graph_module.run_onboarding(company_id, "https://example.com")

    async with test_session_factory() as session:
        docs = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()

    by_source = {doc.source_url: doc.source_type for doc in docs}
    assert by_source["https://example.com/"] == "website"
    assert by_source["https://example.com/products"] == "product_page"


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


async def test_run_onboarding_marks_complete_no_profile_when_extraction_is_skipped(
    monkeypatch, test_session_factory
):
    """Scraping succeeds but extraction is skipped (e.g. no ANTHROPIC_API_KEY)
    — status must say so distinctly, not silently claim "complete" with a
    blank profile."""
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _stub_discover_and_scrape)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _stub_extract_profile_skipped)

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

    assert company.status == "complete_no_profile"
    assert company.status_error is not None
    assert company.name is None
    assert len(docs) >= 2  # scraping/embedding still happened
