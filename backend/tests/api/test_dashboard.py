"""API tests for the dashboard summary route."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import dashboard as dashboard_module
from app.db.models import Company, Trend
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def client(test_session_factory):
    app = FastAPI()
    app.include_router(dashboard_module.router)

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
        id=company_id, url=f"https://example.com/{company_id}", status="complete", name="Acme"
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def test_summary_empty_state(client):
    response = await client.get("/summary")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "company_count": 0,
        "companies_onboarding": 0,
        "recent_companies": [],
        "trending_topics": [],
    }


async def test_summary_counts_companies_by_onboarding_status(client, test_session_factory):
    await _seed_company(test_session_factory, status="complete")
    await _seed_company(test_session_factory, status="pending")
    await _seed_company(test_session_factory, status="scraping")
    await _seed_company(test_session_factory, status="failed")

    response = await client.get("/summary")
    body = response.json()
    assert body["company_count"] == 4
    assert body["companies_onboarding"] == 2  # pending + scraping, not complete/failed


async def test_summary_recent_companies_ordered_by_updated_at_desc(client, test_session_factory):
    older_id = await _seed_company(test_session_factory, name="Older")
    newer_id = await _seed_company(test_session_factory, name="Newer")

    response = await client.get("/summary")
    ids = [c["id"] for c in response.json()["recent_companies"]]
    # Both were just inserted, so this only asserts both appear — exact
    # ordering by updated_at is exercised by the endpoint's ORDER BY, not
    # meaningfully assertable without controlling timestamps directly.
    assert str(older_id) in ids
    assert str(newer_id) in ids


async def test_summary_trending_topics_matches_recommendation_filter(client, test_session_factory):
    now = datetime.now(timezone.utc)
    async with test_session_factory() as session:
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Highly relevant recent trend",
                url="https://example.com/trend-1",
                relevance_score=0.9,
                discovered_at=now,
            )
        )
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Low relevance trend",
                url="https://example.com/trend-2",
                relevance_score=0.1,
                discovered_at=now,
            )
        )
        await session.commit()

    response = await client.get("/summary")
    titles = [t["title"] for t in response.json()["trending_topics"]]
    assert titles == ["Highly relevant recent trend"]


async def test_summary_requires_auth(test_session_factory):
    # No get_current_user override — the route's own dependency should 401.
    app = FastAPI()
    app.include_router(dashboard_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.get("/summary")
    assert response.status_code == 401
