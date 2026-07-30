"""Tests for the scheduled Knowledge Base re-index job."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.company_analyzer.schemas import ScrapedPage
from app.agents.knowledge_base import reindex as reindex_module
from app.db.models import Company, Document


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(id=company_id, url=f"https://example.com/{company_id}", status="complete")
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def _fake_embed(texts):
    return [[0.1] * 1024 for _ in texts]


def _pages_for(base_url: str) -> list[ScrapedPage]:
    return [
        ScrapedPage(url=f"{base_url}/", title="Home", content="We build the best widgets."),
        ScrapedPage(url=f"{base_url}/products", title="Products", content="Widget Pro: $49."),
    ]


async def _fake_discover_and_scrape(url: str, *, max_pages: int) -> list[ScrapedPage]:
    return _pages_for(url)


async def test_reindex_company_persists_scraped_pages_with_classification(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(reindex_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(reindex_module, "discover_and_scrape", _fake_discover_and_scrape)
    import app.agents.knowledge_base.ingestion as ingestion_module

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)

    company_id = await _seed_company(test_session_factory)

    result = await reindex_module.reindex_company(company_id, "https://example.com")

    assert result["pages_scraped"] == 2
    assert result["pages_changed"] == 2

    async with test_session_factory() as session:
        docs = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()
    by_url = {d.source_url: d.source_type for d in docs}
    assert by_url["https://example.com/"] == "website"
    assert by_url["https://example.com/products"] == "product_page"


async def test_reindex_company_skips_unchanged_pages_on_second_run(monkeypatch, test_session_factory):
    monkeypatch.setattr(reindex_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(reindex_module, "discover_and_scrape", _fake_discover_and_scrape)
    import app.agents.knowledge_base.ingestion as ingestion_module

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)

    company_id = await _seed_company(test_session_factory)

    await reindex_module.reindex_company(company_id, "https://example.com")
    second_result = await reindex_module.reindex_company(company_id, "https://example.com")

    assert second_result["pages_scraped"] == 2
    assert second_result["pages_changed"] == 0
    assert second_result["chunks_persisted"] == 0


async def test_reindex_company_isolates_scrape_failure(monkeypatch, test_session_factory):
    monkeypatch.setattr(reindex_module, "async_session_factory", test_session_factory)

    async def _boom(url, *, max_pages):
        raise RuntimeError("site unreachable")

    monkeypatch.setattr(reindex_module, "discover_and_scrape", _boom)

    result = await reindex_module.reindex_company(uuid.uuid4(), "https://example.com")

    assert result == {"pages_scraped": 0, "pages_changed": 0, "chunks_persisted": 0}


async def test_run_scheduled_reindex_only_processes_complete_companies(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(reindex_module, "async_session_factory", test_session_factory)

    processed_urls = []

    async def _fake_reindex_company(company_id, url):
        processed_urls.append(url)
        return {"pages_scraped": 0, "pages_changed": 0, "chunks_persisted": 0}

    monkeypatch.setattr(reindex_module, "reindex_company", _fake_reindex_company)

    await _seed_company(test_session_factory, url="https://complete.example.com", status="complete")
    await _seed_company(test_session_factory, url="https://pending.example.com", status="pending")
    await _seed_company(test_session_factory, url="https://failed.example.com", status="failed")

    await reindex_module.run_scheduled_reindex()

    assert processed_urls == ["https://complete.example.com"]


async def test_run_scheduled_reindex_isolates_per_company_failures(monkeypatch, test_session_factory):
    monkeypatch.setattr(reindex_module, "async_session_factory", test_session_factory)

    processed_urls = []

    async def _flaky_reindex_company(company_id, url):
        if "broken" in url:
            raise RuntimeError("boom")
        processed_urls.append(url)
        return {"pages_scraped": 0, "pages_changed": 0, "chunks_persisted": 0}

    monkeypatch.setattr(reindex_module, "reindex_company", _flaky_reindex_company)

    await _seed_company(test_session_factory, url="https://broken.example.com", status="complete")
    await _seed_company(test_session_factory, url="https://fine.example.com", status="complete")

    await reindex_module.run_scheduled_reindex()

    assert processed_urls == ["https://fine.example.com"]
