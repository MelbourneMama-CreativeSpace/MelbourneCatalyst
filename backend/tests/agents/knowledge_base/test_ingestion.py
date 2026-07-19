"""Tests for the shared RawDocument -> Document ingestion primitive."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.knowledge_base import ingestion as ingestion_module
from app.agents.knowledge_base.schemas import RawDocument
from app.db.models import Company, Document


async def _seed_company(test_session_factory) -> uuid.UUID:
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=f"https://example.com/{company_id}", status="complete"))
        await session.commit()
    return company_id


async def test_ingest_raw_document_persists_chunks_with_embeddings(monkeypatch, test_session_factory):
    monkeypatch.setattr(
        ingestion_module, "embed_documents", lambda texts: _fake_embed(texts)
    )
    company_id = await _seed_company(test_session_factory)

    raw = RawDocument(
        source_type="manual", source_url="manual://abc", content="a" * 2500, raw_metadata={"title": "Note"}
    )

    async with test_session_factory() as session:
        count = await ingestion_module.ingest_raw_document(session, company_id, raw)
        await session.commit()

    assert count > 1  # long content chunks into multiple pieces
    async with test_session_factory() as session:
        rows = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()
    assert len(rows) == count
    assert all(row.source_type == "manual" for row in rows)
    assert all(row.source_url == "manual://abc" for row in rows)
    assert all(row.embedding is not None for row in rows)
    assert {row.chunk_index for row in rows} == set(range(count))


async def test_ingest_raw_document_empty_content_persists_nothing(monkeypatch, test_session_factory):
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    raw = RawDocument(source_type="manual", source_url="manual://empty", content="   ")

    async with test_session_factory() as session:
        count = await ingestion_module.ingest_raw_document(session, company_id, raw)
        await session.commit()

    assert count == 0


async def test_ingest_raw_document_replaces_existing_rows_for_same_source_url(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    raw_v1 = RawDocument(source_type="blog", source_url="https://example.com/post", content="old content")
    raw_v2 = RawDocument(
        source_type="blog", source_url="https://example.com/post", content="new content, freshly re-indexed"
    )

    async with test_session_factory() as session:
        await ingestion_module.ingest_raw_document(session, company_id, raw_v1)
        await session.commit()
    async with test_session_factory() as session:
        await ingestion_module.ingest_raw_document(session, company_id, raw_v2)
        await session.commit()

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                select(Document).where(
                    Document.company_id == company_id, Document.source_url == "https://example.com/post"
                )
            )
        ).scalars().all()

    # Re-ingesting the same source_url replaced the old chunk(s), not accumulated.
    assert len(rows) == 1
    assert "new content" in rows[0].content


async def test_ingest_raw_document_does_not_touch_other_sources(monkeypatch, test_session_factory):
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    async with test_session_factory() as session:
        await ingestion_module.ingest_raw_document(
            session, company_id, RawDocument(source_type="blog", source_url="url-a", content="content a")
        )
        await ingestion_module.ingest_raw_document(
            session, company_id, RawDocument(source_type="blog", source_url="url-b", content="content b")
        )
        await session.commit()

    async with test_session_factory() as session:
        rows = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()

    assert {row.source_url for row in rows} == {"url-a", "url-b"}


async def _fake_embed(texts):
    return [[0.1] * 1024 for _ in texts]
