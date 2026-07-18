"""API tests for the Trend Analyzer routes.

Mounted as a standalone FastAPI app (router only, no `lifespan`) rather than
importing the real `app.main:app` — the real app's lifespan starts an
APScheduler job that would fire a live collection run (real network calls,
real Anthropic call) shortly after startup, which is exactly what we don't
want in a test.

Uses `httpx.AsyncClient` + `ASGITransport` rather than Starlette's sync
`TestClient`: calling the sync client from inside `async def` tests risks an
event-loop mismatch against the async DB fixtures below (they share one
event loop; the sync client manages its own).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import trends as trends_module
from app.db.models import Trend
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(test_session_factory):
    app = FastAPI()
    app.include_router(trends_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_trend(test_session_factory, **overrides) -> uuid.UUID:
    defaults = dict(
        id=uuid.uuid4(),
        source="reddit",
        title="Seeded trend",
        description=None,
        url="https://example.com/seed",
        score=10.0,
        category="marketing",
        insight="Because reasons",
        raw_metadata={},
        discovered_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Trend(**defaults))
        await session.commit()
    return defaults["id"]


async def test_list_trends_returns_seeded_rows(test_session_factory, client):
    await _seed_trend(test_session_factory)

    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Seeded trend"


async def test_list_trends_filters_by_source(test_session_factory, client):
    await _seed_trend(test_session_factory, source="reddit", url="https://example.com/r")
    await _seed_trend(test_session_factory, source="rss", url="https://example.com/rss")

    response = await client.get("/", params={"source": "rss"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "rss"


async def test_list_trends_filters_by_ids(test_session_factory, client):
    id_a = await _seed_trend(test_session_factory, url="https://example.com/a")
    id_b = await _seed_trend(test_session_factory, url="https://example.com/b")
    await _seed_trend(test_session_factory, url="https://example.com/c")

    response = await client.get("/", params={"ids": [str(id_a), str(id_b)]})

    body = response.json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {str(id_a), str(id_b)}


async def test_get_trend_returns_404_for_unknown_id(client):
    response = await client.get(f"/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_trend_returns_the_row(test_session_factory, client):
    trend_id = await _seed_trend(test_session_factory)

    response = await client.get(f"/{trend_id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(trend_id)


async def test_collect_endpoint_invokes_run_collection(monkeypatch, client):
    from app.agents.trend_analyzer.schemas import RunResult, SourceResult, TrendSource

    async def fake_run_collection():
        return RunResult(
            new_item_count=2,
            source_results=[
                SourceResult(source=TrendSource.REDDIT, item_count=5, new_item_count=2)
            ],
        )

    monkeypatch.setattr(trends_module, "run_collection", fake_run_collection)

    response = await client.post("/collect")

    assert response.status_code == 200
    body = response.json()
    assert body["new_item_count"] == 2
    assert body["source_results"][0]["source"] == "reddit"
    # Collected 5 raw items but only 2 were genuinely new — both numbers
    # must survive the API boundary distinctly, not collapse into one.
    assert body["source_results"][0]["collected_count"] == 5
    assert body["source_results"][0]["new_item_count"] == 2
