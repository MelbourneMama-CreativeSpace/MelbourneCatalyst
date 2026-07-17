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

from app.api.v1.endpoints import companies as companies_module
from app.db.models import Company
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
            )
        )
        await session.commit()

    response = await client.get(f"/{company_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Example Co"
    assert body["niche_keywords"] == ["widgets"]


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
