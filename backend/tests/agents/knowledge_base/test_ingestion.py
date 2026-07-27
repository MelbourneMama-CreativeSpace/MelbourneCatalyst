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


async def test_ingest_if_changed_persists_and_tags_hash_on_first_run(monkeypatch, test_session_factory):
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    raw = RawDocument(source_type="website", source_url="https://example.com/", content="original content")

    async with test_session_factory() as session:
        count, skipped = await ingestion_module.ingest_raw_document_if_changed(session, company_id, raw)
        await session.commit()

    assert skipped is False
    assert count == 1
    async with test_session_factory() as session:
        row = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalar_one()
    assert "content_hash" in row.raw_metadata


async def test_ingest_if_changed_skips_unchanged_content_without_embedding(monkeypatch, test_session_factory):
    embed_calls = []

    async def _counting_embed(texts):
        embed_calls.append(texts)
        return await _fake_embed(texts)

    monkeypatch.setattr(ingestion_module, "embed_documents", _counting_embed)
    company_id = await _seed_company(test_session_factory)
    raw = RawDocument(source_type="website", source_url="https://example.com/", content="same content")

    async with test_session_factory() as session:
        await ingestion_module.ingest_raw_document_if_changed(session, company_id, raw)
        await session.commit()
    assert len(embed_calls) == 1

    # Re-run with identical content: should skip entirely, no second embed call.
    raw_again = RawDocument(source_type="website", source_url="https://example.com/", content="same content")
    async with test_session_factory() as session:
        count, skipped = await ingestion_module.ingest_raw_document_if_changed(
            session, company_id, raw_again
        )
        await session.commit()

    assert skipped is True
    assert count == 0
    assert len(embed_calls) == 1  # no additional embedding call happened


async def test_ingest_if_changed_re_ingests_when_content_differs(monkeypatch, test_session_factory):
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    async with test_session_factory() as session:
        await ingestion_module.ingest_raw_document_if_changed(
            session,
            company_id,
            RawDocument(source_type="website", source_url="https://example.com/", content="version one"),
        )
        await session.commit()

    async with test_session_factory() as session:
        count, skipped = await ingestion_module.ingest_raw_document_if_changed(
            session,
            company_id,
            RawDocument(source_type="website", source_url="https://example.com/", content="version two, changed"),
        )
        await session.commit()

    assert skipped is False
    assert count == 1
    async with test_session_factory() as session:
        row = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalar_one()
    assert "version two" in row.content


async def test_ingest_if_changed_treats_missing_prior_hash_as_changed(monkeypatch, test_session_factory):
    """Documents persisted before this feature existed (e.g. by the plain
    onboarding pipeline) have no content_hash in raw_metadata at all —
    that must be treated as "changed", not silently trusted as unchanged."""
    monkeypatch.setattr(ingestion_module, "embed_documents", lambda texts: _fake_embed(texts))
    company_id = await _seed_company(test_session_factory)

    async with test_session_factory() as session:
        session.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type="website",
                source_url="https://example.com/",
                chunk_index=0,
                content="pre-existing content, no hash tag",
                raw_metadata={"page_title": "Home"},
            )
        )
        await session.commit()

    async with test_session_factory() as session:
        count, skipped = await ingestion_module.ingest_raw_document_if_changed(
            session,
            company_id,
            RawDocument(
                source_type="website", source_url="https://example.com/", content="pre-existing content, no hash tag"
            ),
        )
        await session.commit()

    assert skipped is False
    assert count == 1
