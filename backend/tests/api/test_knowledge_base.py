"""API tests for the Knowledge Base search endpoint."""

from __future__ import annotations

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agents.knowledge_base.schemas import SearchHit
from app.api.v1.endpoints import knowledge_base as kb_module
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    app = FastAPI()
    app.include_router(kb_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_search_returns_hits_from_similarity_search(monkeypatch, client):
    async def fake_similarity_search(session, query, *, company_id=None, k=5):
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
