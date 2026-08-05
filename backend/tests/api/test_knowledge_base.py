"""API tests for the Knowledge Base search, freshness, and audit-report
endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agents.knowledge_base.schemas import SearchHit
from app.api.v1.endpoints import knowledge_base as kb_module
from app.db.models import Company, Document, KnowledgeAuditReport
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_run_knowledge_audit_generation(report_id, company_id):
        async with test_session_factory() as session:
            audit_report = await session.get(KnowledgeAuditReport, report_id)
            audit_report.status = "complete"
            audit_report.coverage_summary = "Fake coverage summary."
            await session.commit()

    monkeypatch.setattr(
        kb_module, "run_knowledge_audit_generation", _fake_run_knowledge_audit_generation
    )
    # ingest_raw_document calls embed_documents internally — stub it so
    # these tests don't need a real VOYAGE_API_KEY, same pattern as the
    # ingestion-module tests.
    import app.agents.knowledge_base.ingestion as ingestion_module

    async def _fake_embed_documents(texts):
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed_documents)

    app = FastAPI()
    app.include_router(kb_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id,
        url=f"https://example.com/{company_id}",
        status="complete",
        name="Acme",
        owner_id="test-user-id",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def test_search_returns_hits_from_similarity_search(monkeypatch, client):
    async def fake_similarity_search(session, query, *, company_id=None, company_ids=None, k=5):
        return [
            SearchHit(
                document_id="doc-1",
                source_type="website",
                source_url="https://example.com/about",
                content="We build widgets.",
                similarity=0.87,
            )
        ]

    monkeypatch.setattr(kb_module, "similarity_search", fake_similarity_search)

    response = await client.get("/search", params={"q": "widgets"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "widgets"
    assert len(body["hits"]) == 1
    assert body["hits"][0]["source_url"] == "https://example.com/about"
    assert body["hits"][0]["similarity"] == 0.87


async def test_search_requires_non_empty_query(client):
    response = await client.get("/search", params={"q": ""})
    assert response.status_code == 422


async def test_search_rejects_out_of_range_k(client):
    response = await client.get("/search", params={"q": "widgets", "k": 0})
    assert response.status_code == 422

    response = await client.get("/search", params={"q": "widgets", "k": 51})
    assert response.status_code == 422


# --- Freshness ---------------------------------------------------------


async def test_freshness_returns_zero_for_a_company_with_no_documents(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.get("/freshness", params={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] == 0
    assert body["last_ingested_at"] is None
    assert body["staleness_days"] is None


async def test_freshness_reports_real_counts_and_staleness(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    old_time = datetime.now(timezone.utc) - timedelta(days=10)
    async with test_session_factory() as session:
        session.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type="website",
                source_url="https://example.com/",
                chunk_index=0,
                content="content",
                raw_metadata={},
                created_at=old_time,
            )
        )
        session.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type="website",
                source_url="https://example.com/about",
                chunk_index=0,
                content="content",
                raw_metadata={},
            )
        )
        await session.commit()

    response = await client.get("/freshness", params={"company_id": str(company_id)})

    body = response.json()
    assert body["document_count"] == 2
    # The second document has no explicit created_at override — it gets
    # the server default (now), so last_ingested_at should reflect that
    # recent row, not the 10-day-old one.
    assert body["staleness_days"] == 0


async def test_freshness_404s_for_unknown_company(client):
    response = await client.get("/freshness", params={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_freshness_does_not_require_company_status_complete(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="scraping")

    response = await client.get("/freshness", params={"company_id": str(company_id)})

    assert response.status_code == 200


# --- Audit reports -------------------------------------------------------


async def test_create_audit_report_returns_completed_report(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/audit-reports", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["coverage_summary"] == "Fake coverage summary."


async def test_create_audit_report_404s_for_unknown_company(client):
    response = await client.post("/audit-reports", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_audit_report_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="pending")

    response = await client.post("/audit-reports", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_get_audit_report_404s_for_unknown_id(client):
    response = await client.get(f"/audit-reports/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_audit_report_returns_the_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            KnowledgeAuditReport(
                id=report_id, company_id=company_id, status="complete", coverage_summary="Existing"
            )
        )
        await session.commit()

    response = await client.get(f"/audit-reports/{report_id}")

    assert response.status_code == 200
    assert response.json()["coverage_summary"] == "Existing"


async def test_list_audit_reports_filters_by_company_id(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(KnowledgeAuditReport(id=uuid.uuid4(), company_id=company_a, status="complete"))
        session.add(KnowledgeAuditReport(id=uuid.uuid4(), company_id=company_b, status="complete"))
        await session.commit()

    response = await client.get("/audit-reports", params={"company_id": str(company_a)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == str(company_a)


# --- Documents: list/detail/delete ----------------------------------------


async def _seed_document(test_session_factory, company_id, **overrides) -> uuid.UUID:
    document_id = uuid.uuid4()
    defaults = dict(
        id=document_id,
        company_id=company_id,
        source_type="website",
        source_url=f"https://example.com/{document_id}",
        chunk_index=0,
        content="Some ingested content long enough to preview.",
        raw_metadata={},
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Document(**defaults))
        await session.commit()
    return document_id


async def test_list_documents_returns_previews_for_a_company(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    await _seed_document(test_session_factory, company_id, content="x" * 500)

    response = await client.get("/documents", params={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"][0]["content_preview"]) <= 240


async def test_list_documents_filters_by_source_type(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    await _seed_document(test_session_factory, company_id, source_type="website")
    await _seed_document(test_session_factory, company_id, source_type="manual")

    response = await client.get(
        "/documents", params={"company_id": str(company_id), "source_type": "manual"}
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source_type"] == "manual"


async def test_list_documents_only_returns_the_requested_company(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    await _seed_document(test_session_factory, company_a)
    await _seed_document(test_session_factory, company_b)

    response = await client.get("/documents", params={"company_id": str(company_a)})

    assert response.json()["total"] == 1


async def test_get_document_returns_full_content(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    document_id = await _seed_document(test_session_factory, company_id, content="Full content here.")

    response = await client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    assert response.json()["content"] == "Full content here."


async def test_get_document_404s_for_unknown_id(client):
    response = await client.get(f"/documents/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_document_removes_it(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    document_id = await _seed_document(test_session_factory, company_id, content="Doomed content.")

    response = await client.delete(f"/documents/{document_id}")
    assert response.status_code == 200
    assert response.json()["content"] == "Doomed content."

    follow_up = await client.get(f"/documents/{document_id}")
    assert follow_up.status_code == 404


async def test_delete_document_404s_for_unknown_id(client):
    response = await client.delete(f"/documents/{uuid.uuid4()}")
    assert response.status_code == 404


# --- Documents: manual entry ------------------------------------------------


async def test_create_manual_document_persists_chunks(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/manual",
        json={"company_id": str(company_id), "title": "Our story", "content": "We started in 2020."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_processed"] == 1
    assert body["chunks_persisted"] == 1

    listing = await client.get("/documents", params={"company_id": str(company_id)})
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["source_type"] == "manual"


async def test_create_manual_document_404s_for_unknown_company(client):
    response = await client.post(
        "/documents/manual",
        json={"company_id": str(uuid.uuid4()), "title": "x", "content": "y"},
    )
    assert response.status_code == 404


async def test_create_manual_document_does_not_require_company_status_complete(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory, status="pending")

    response = await client.post(
        "/documents/manual",
        json={"company_id": str(company_id), "title": "x", "content": "Some content."},
    )

    assert response.status_code == 200


# --- Documents: file upload --------------------------------------------------


async def test_upload_document_extracts_and_persists_txt(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/upload",
        data={"company_id": str(company_id)},
        files={"file": ("notes.txt", b"Uploaded plain text content for the knowledge base.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chunks_persisted"] == 1

    listing = await client.get("/documents", params={"company_id": str(company_id)})
    assert listing.json()["items"][0]["source_type"] == "doc_upload"


async def test_upload_document_rejects_unsupported_file_type(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/upload",
        data={"company_id": str(company_id)},
        files={"file": ("archive.zip", b"not a real zip", "application/zip")},
    )

    assert response.status_code == 400


async def test_upload_document_404s_for_unknown_company(client):
    response = await client.post(
        "/documents/upload",
        data={"company_id": str(uuid.uuid4())},
        files={"file": ("notes.txt", b"content", "text/plain")},
    )
    assert response.status_code == 404


async def test_upload_document_rejects_oversized_file(monkeypatch, client, test_session_factory):
    monkeypatch.setattr(kb_module.settings, "KB_UPLOAD_MAX_BYTES", 10)
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/upload",
        data={"company_id": str(company_id)},
        files={"file": ("notes.txt", b"this file is definitely over ten bytes", "text/plain")},
    )

    assert response.status_code == 413


# --- Documents: blog indexing ------------------------------------------------


async def test_index_blog_persists_returned_articles(monkeypatch, client, test_session_factory):
    from app.agents.knowledge_base.schemas import RawDocument

    async def _fake_index_blog_feeds(feed_urls, *, max_articles):
        return [
            RawDocument(
                source_type="blog", source_url="https://example.com/post-1", content="Article content."
            )
        ]

    monkeypatch.setattr(kb_module, "index_blog_feeds", _fake_index_blog_feeds)
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/blog-index",
        json={"company_id": str(company_id), "feed_urls": ["https://example.com/feed"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_processed"] == 1
    assert body["chunks_persisted"] == 1


async def test_index_blog_handles_no_articles_found(monkeypatch, client, test_session_factory):
    async def _fake_index_blog_feeds(feed_urls, *, max_articles):
        return []

    monkeypatch.setattr(kb_module, "index_blog_feeds", _fake_index_blog_feeds)
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/documents/blog-index",
        json={"company_id": str(company_id), "feed_urls": ["https://example.com/feed"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources_processed"] == 0
    assert body["chunks_persisted"] == 0


async def test_index_blog_404s_for_unknown_company(client):
    response = await client.post(
        "/documents/blog-index",
        json={"company_id": str(uuid.uuid4()), "feed_urls": ["https://example.com/feed"]},
    )
    assert response.status_code == 404
