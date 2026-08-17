"""API tests for the Analysis overview route."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import analysis as analysis_module
from app.db.models import Company, ContentItem, ContentPlan, PostMetricSnapshot
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user

_NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def client(test_session_factory):
    app = FastAPI()
    app.include_router(analysis_module.router)

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


async def _seed_published_item(test_session_factory, company_id, **overrides) -> uuid.UUID:
    async with test_session_factory() as session:
        plan_id = uuid.uuid4()
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        item_id = uuid.uuid4()
        defaults = dict(
            id=item_id,
            content_plan_id=plan_id,
            title="Item",
            description="Desc",
            content_type="image_post",
            platform="instagram",
            theme="launch",
            suggested_date=date.today(),
            approval_status="approved",
            published_at=_NOW,
        )
        defaults.update(overrides)
        session.add(ContentItem(**defaults))
        await session.flush()
        session.add(PostMetricSnapshot(content_item_id=item_id, likes=50, comments=5))
        await session.commit()
    return item_id


async def test_overview_requires_auth(test_session_factory):
    app = FastAPI()
    app.include_router(analysis_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.get(f"/overview?company_id={uuid.uuid4()}")
    assert response.status_code == 401


async def test_overview_404_for_unknown_company(client):
    response = await client.get(f"/overview?company_id={uuid.uuid4()}")
    assert response.status_code == 404


async def test_overview_returns_real_aggregated_numbers(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    await _seed_published_item(test_session_factory, company_id)

    with patch.object(analysis_module, "get_or_generate_insight", new=AsyncMock(return_value=(None, []))):
        response = await client.get(f"/overview?company_id={company_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["posts_published"] == 1
    assert body["current_totals"]["engagement"] == 55
    assert body["metrics_available"] is True
    assert body["ai_why"] is None
    assert body["ai_recommendations"] == []


async def test_overview_includes_ai_insight_when_available(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    await _seed_published_item(test_session_factory, company_id)

    with patch.object(
        analysis_module,
        "get_or_generate_insight",
        new=AsyncMock(return_value=("Instagram drove it", ["Post more reels"])),
    ):
        response = await client.get(f"/overview?company_id={company_id}")

    body = response.json()
    assert body["ai_why"] == "Instagram drove it"
    assert body["ai_recommendations"] == ["Post more reels"]


async def test_overview_scopes_to_requested_company(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    await _seed_published_item(test_session_factory, company_a)

    with patch.object(analysis_module, "get_or_generate_insight", new=AsyncMock(return_value=(None, []))):
        response = await client.get(f"/overview?company_id={company_b}")

    assert response.status_code == 200
    assert response.json()["posts_published"] == 0
