"""API tests for the Company Analyzer routes.

Same in-memory-SQLite + AsyncClient/ASGITransport pattern as `test_trends.py`.
`run_onboarding` is monkey-patched to a no-op so POST /companies doesn't
try to actually scrape/embed/call Claude during tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.endpoints import companies as companies_module
from app.db.models import Company, Document
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _noop_run_onboarding(company_id, url):
        pass

    monkeypatch.setattr(companies_module, "run_onboarding", _noop_run_onboarding)

    app = FastAPI()
    app.include_router(companies_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_create_company_returns_pending_and_persists_row(client, test_session_factory):
    response = await client.post("/", json={"url": "https://example.com"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["url"].startswith("https://example.com")

    async with test_session_factory() as session:
        company = await session.get(Company, uuid.UUID(body["id"]))
    assert company is not None
    assert company.status == "pending"


async def test_create_company_rejects_invalid_url(client):
    response = await client.post("/", json={"url": "not-a-url"})
    assert response.status_code == 422


async def test_create_company_re_onboards_existing_url(client, test_session_factory):
    first = await client.post("/", json={"url": "https://example.com"})
    company_id = first.json()["id"]

    # Simulate that the first run completed
    async with test_session_factory() as session:
        company = await session.get(Company, uuid.UUID(company_id))
        company.status = "complete"
        await session.commit()

    second = await client.post("/", json={"url": "https://example.com"})
    assert second.status_code == 202
    assert second.json()["id"] == company_id
    assert second.json()["status"] == "pending"


async def test_create_company_normalizes_url_variants_to_the_same_row(client):
    first = await client.post("/", json={"url": "https://example.com"})
    second = await client.post("/", json={"url": "https://example.com/"})

    # Same normalized URL -> same Company row, not two duplicates.
    assert first.json()["id"] == second.json()["id"]


async def test_re_onboarding_deletes_stale_documents(client, test_session_factory):
    first = await client.post("/", json={"url": "https://example.com"})
    company_id = uuid.UUID(first.json()["id"])

    async with test_session_factory() as session:
        company = await session.get(Company, company_id)
        company.status = "complete"
        session.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type="website",
                source_url="https://example.com/",
                chunk_index=0,
                content="stale content from a previous onboarding run",
                raw_metadata={},
            )
        )
        await session.commit()

    await client.post("/", json={"url": "https://example.com"})

    async with test_session_factory() as session:
        docs = (
            await session.execute(select(Document).where(Document.company_id == company_id))
        ).scalars().all()
    assert docs == []


async def test_get_company_returns_404_for_unknown_id(client):
    response = await client.get(f"/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_company_returns_the_row(client, test_session_factory):
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url="https://example.com",
                status="complete",
                name="Example Co",
                niche_keywords=["widgets"],
                products_and_services=["Widget subscription box"],
            )
        )
        await session.commit()

    response = await client.get(f"/{company_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Example Co"
    assert body["niche_keywords"] == ["widgets"]
    assert body["products_and_services"] == ["Widget subscription box"]


async def test_list_companies_returns_all(client, test_session_factory):
    async with test_session_factory() as session:
        session.add(Company(id=uuid.uuid4(), url="https://a.example.com", status="complete"))
        session.add(Company(id=uuid.uuid4(), url="https://b.example.com", status="pending"))
        await session.commit()

    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
