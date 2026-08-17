"""Tests for the Company Analyzer LangGraph onboarding pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.company_analyzer import graph as graph_module
from app.agents.company_analyzer.schemas import CompanyProfile, ScrapedPage
from app.db.models import Company, Document, PlatformConnection


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


async def _failing_discover_and_scrape(base_url: str, *, max_pages: int):
    raise AssertionError("scraping must not be attempted when there is no URL")


async def test_run_onboarding_uses_description_when_there_is_no_website(
    monkeypatch, test_session_factory
):
    """A business with no site still gets profiled — from its own words."""
    captured: dict[str, str] = {}

    async def _capture(content: str):
        captured["content"] = content
        return await _stub_extract_profile(content)

    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _failing_discover_and_scrape)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _capture)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=None, status="pending"))
        await session.commit()

    await graph_module.run_onboarding(
        company_id, None, "We run weekly pottery workshops in Brunswick."
    )

    async with test_session_factory() as session:
        company = await session.get(Company, company_id)
        docs = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()

    assert company.status == "complete"
    assert company.niche_keywords == ["widgets", "small business", "marketing tools"]
    assert "pottery workshops in Brunswick" in captured["content"]
    # The description is embedded like any other source, so it's searchable
    # in the knowledge base rather than being extraction-only input.
    assert [doc.source_type for doc in docs] == ["description"]


async def test_run_onboarding_feeds_connected_social_accounts_into_extraction(
    monkeypatch, test_session_factory
):
    captured: dict[str, str] = {}

    async def _capture(content: str):
        captured["content"] = content
        return await _stub_extract_profile(content)

    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "discover_and_scrape", _failing_discover_and_scrape)
    monkeypatch.setattr(graph_module, "embed_documents", _stub_embed_documents)
    monkeypatch.setattr(graph_module, "extract_company_profile", _capture)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=None, status="pending"))
        session.add(
            PlatformConnection(
                id=uuid.uuid4(),
                company_id=company_id,
                platform="instagram",
                status="connected",
                external_account_name="@brunswickclay",
            )
        )
        # A half-finished connection carries no reliable identity yet.
        session.add(
            PlatformConnection(
                id=uuid.uuid4(),
                company_id=company_id,
                platform="tiktok",
                status="pending",
                external_account_name="@notconnectedyet",
            )
        )
        await session.commit()

    await graph_module.run_onboarding(company_id, None, "Ceramics studio.")

    assert "@brunswickclay" in captured["content"]
    assert "@notconnectedyet" not in captured["content"]


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
