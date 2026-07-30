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
from app.db.models import Company, Trend, TrendReport
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_run_trend_report_generation(report_id, company_id, period_days):
        async with test_session_factory() as session:
            trend_report = await session.get(TrendReport, report_id)
            trend_report.status = "complete"
            trend_report.summary = "Fake trend report summary."
            trend_report.key_themes = ["fake theme"]
            await session.commit()

    monkeypatch.setattr(
        trends_module, "run_trend_report_generation", _fake_run_trend_report_generation
    )

    async def _fake_generate_content_opportunities(context):
        from app.agents.trend_analyzer.schemas import GeneratedOpportunity

        if "trigger-failure" in context:
            return [], False
        return (
            [
                GeneratedOpportunity(
                    title="Fake opportunity",
                    reasoning="Fake reasoning.",
                    source="trend",
                    priority="high",
                )
            ],
            True,
        )

    monkeypatch.setattr(
        trends_module, "generate_content_opportunities", _fake_generate_content_opportunities
    )

    app = FastAPI()
    app.include_router(trends_module.router)

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


# --- Trend reports -------------------------------------------------------


async def test_create_trend_report_returns_completed_report(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/reports", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["summary"] == "Fake trend report summary."
    assert body["period_days"] == 7  # TREND_REPORT_DEFAULT_PERIOD_DAYS


async def test_create_trend_report_uses_a_custom_period(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/reports", json={"company_id": str(company_id), "period_days": 30}
    )

    assert response.json()["period_days"] == 30


async def test_create_trend_report_404s_for_unknown_company(client):
    response = await client.post("/reports", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_trend_report_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="scraping")

    response = await client.post("/reports", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_get_trend_report_404s_for_unknown_id(client):
    response = await client.get(f"/reports/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_trend_report_returns_the_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            TrendReport(
                id=report_id,
                company_id=company_id,
                status="complete",
                period_days=7,
                summary="Existing summary",
            )
        )
        await session.commit()

    response = await client.get(f"/reports/{report_id}")

    assert response.status_code == 200
    assert response.json()["summary"] == "Existing summary"


async def test_list_trend_reports_filters_by_company_id(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(TrendReport(id=uuid.uuid4(), company_id=company_a, status="complete", period_days=7))
        session.add(TrendReport(id=uuid.uuid4(), company_id=company_b, status="complete", period_days=7))
        await session.commit()

    response = await client.get("/reports", params={"company_id": str(company_a)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == str(company_a)


async def test_reports_route_is_not_captured_by_the_trend_id_catch_all(client, test_session_factory):
    """Regression check: /reports must resolve to the reports list route,
    not fall into GET /{trend_id} (which would 422 trying to parse
    "reports" as a UUID) — this only works because /reports is registered
    before /{trend_id} in trends.py."""
    response = await client.get("/reports")
    assert response.status_code == 200
    assert "items" in response.json()


# --- Recommended trends ----------------------------------------------------


async def test_recommended_route_is_not_captured_by_the_trend_id_catch_all(client):
    """Same regression class as /reports above — /recommended must resolve
    to the recommended-trends route, not 422 trying to parse "recommended"
    as a trend_id UUID."""
    response = await client.get("/recommended")
    assert response.status_code == 200
    assert "items" in response.json()


async def test_recommended_trends_includes_highly_relevant_recent_trends(
    client, test_session_factory
):
    await _seed_trend(
        test_session_factory,
        title="Highly relevant and fresh",
        url="https://example.com/fresh",
        relevance_score=0.9,
        discovered_at=datetime.now(timezone.utc),
    )

    response = await client.get("/recommended")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Highly relevant and fresh"


async def test_recommended_trends_excludes_low_relevance(client, test_session_factory):
    await _seed_trend(
        test_session_factory,
        title="Barely relevant",
        url="https://example.com/low",
        relevance_score=0.3,
        discovered_at=datetime.now(timezone.utc),
    )

    response = await client.get("/recommended")

    assert response.json()["total"] == 0


async def test_recommended_trends_excludes_stale_trends(client, test_session_factory):
    from datetime import timedelta

    await _seed_trend(
        test_session_factory,
        title="Relevant but old",
        url="https://example.com/old",
        relevance_score=0.95,
        discovered_at=datetime.now(timezone.utc) - timedelta(days=60),
    )

    response = await client.get("/recommended")

    assert response.json()["total"] == 0


async def test_recommended_trends_respects_custom_limit(client, test_session_factory):
    for i in range(5):
        await _seed_trend(
            test_session_factory,
            title=f"Recommended {i}",
            url=f"https://example.com/rec-{i}",
            relevance_score=0.9,
            discovered_at=datetime.now(timezone.utc),
        )

    response = await client.get("/recommended", params={"limit": 2})

    body = response.json()
    assert len(body["items"]) == 2
    assert body["limit"] == 2


# --- Content opportunities -------------------------------------------------


async def test_opportunities_returns_generated_list(client, test_session_factory):
    from app.db.models import CompanyTrendRelevance

    company_id = await _seed_company(test_session_factory)
    trend_id = await _seed_trend(test_session_factory)
    async with test_session_factory() as session:
        session.add(
            CompanyTrendRelevance(
                id=uuid.uuid4(), company_id=company_id, trend_id=trend_id, relevance_score=0.9
            )
        )
        await session.commit()

    response = await client.post("/opportunities", params={"company_id": str(company_id)})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Fake opportunity"
    assert items[0]["source"] == "trend"
    assert items[0]["priority"] == "high"


async def test_opportunities_404s_for_unknown_company(client):
    response = await client.post("/opportunities", params={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_opportunities_falls_back_gracefully_with_no_trends_or_seasonal_data(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/opportunities", params={"company_id": str(company_id)})

    # No CompanyTrendRelevance rows and (probably) no seasonal dates in
    # window — still succeeds, just with thinner context.
    assert response.status_code == 200


async def test_opportunities_502s_on_generation_failure(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, name="trigger-failure")

    response = await client.post("/opportunities", params={"company_id": str(company_id)})
    assert response.status_code == 502
