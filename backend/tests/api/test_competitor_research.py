"""API tests for the Competitor Research routes.

Same in-memory-SQLite + AsyncClient/ASGITransport pattern as
`test_companies.py` (for the BackgroundTasks-driven onboarding endpoints)
and `test_content_management.py` (for the synchronous comparison
endpoint) — the graph-running functions are monkey-patched so these tests
exercise the actual endpoint logic without needing a real Anthropic key.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import competitor_research as competitor_research_module
from app.db.models import Company, Competitor
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _noop_run_competitor_onboarding(competitor_id, url):
        pass

    async def _fake_run_comparison_generation(competitor_id, company_id):
        async with test_session_factory() as session:
            competitor = await session.get(Competitor, competitor_id)
            competitor.comparison_status = "complete"
            competitor.competitive_gaps = "Fake competitive gap."
            competitor.strategic_recommendations = "Fake recommendation."
            await session.commit()

    monkeypatch.setattr(
        competitor_research_module, "run_competitor_onboarding", _noop_run_competitor_onboarding
    )
    monkeypatch.setattr(
        competitor_research_module, "run_comparison_generation", _fake_run_comparison_generation
    )

    app = FastAPI()
    app.include_router(competitor_research_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

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


# --- Competitors -----------------------------------------------------------


async def test_create_competitor_returns_pending_and_persists_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/competitors", json={"company_id": str(company_id), "url": "https://rival.com"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["company_id"] == str(company_id)

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, uuid.UUID(body["id"]))
    assert competitor is not None
    assert competitor.status == "pending"


async def test_create_competitor_404s_for_unknown_company(client):
    response = await client.post(
        "/competitors", json={"company_id": str(uuid.uuid4()), "url": "https://rival.com"}
    )
    assert response.status_code == 404


async def test_create_competitor_re_onboards_existing_url(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    first = await client.post(
        "/competitors", json={"company_id": str(company_id), "url": "https://rival.com"}
    )
    competitor_id = first.json()["id"]

    async with test_session_factory() as session:
        competitor = await session.get(Competitor, uuid.UUID(competitor_id))
        competitor.status = "complete"
        await session.commit()

    second = await client.post(
        "/competitors", json={"company_id": str(company_id), "url": "https://rival.com"}
    )
    assert second.status_code == 202
    assert second.json()["id"] == competitor_id
    assert second.json()["status"] == "pending"


async def test_get_competitor_returns_404_for_unknown_id(client):
    response = await client.get(f"/competitors/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_competitor_returns_the_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(
                id=competitor_id,
                company_id=company_id,
                url="https://rival.com",
                status="complete",
                name="Rival Co",
            )
        )
        await session.commit()

    response = await client.get(f"/competitors/{competitor_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Rival Co"


async def test_list_competitors_filters_by_company_id(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(
            Competitor(id=uuid.uuid4(), company_id=company_a, url="https://a-rival.com", status="complete")
        )
        session.add(
            Competitor(id=uuid.uuid4(), company_id=company_b, url="https://b-rival.com", status="complete")
        )
        await session.commit()

    response = await client.get("/competitors", params={"company_id": str(company_a)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == str(company_a)


# --- Comparison --------------------------------------------------------


async def test_create_comparison_returns_completed_comparison(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(
                id=competitor_id, company_id=company_id, url="https://rival.com", status="complete"
            )
        )
        await session.commit()

    response = await client.post(f"/competitors/{competitor_id}/comparison")

    assert response.status_code == 200
    body = response.json()
    assert body["comparison_status"] == "complete"
    assert body["competitive_gaps"] == "Fake competitive gap."


async def test_create_comparison_404s_for_unknown_competitor(client):
    response = await client.post(f"/competitors/{uuid.uuid4()}/comparison")
    assert response.status_code == 404


async def test_create_comparison_409s_when_competitor_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(
                id=competitor_id, company_id=company_id, url="https://rival.com", status="scraping"
            )
        )
        await session.commit()

    response = await client.post(f"/competitors/{competitor_id}/comparison")

    assert response.status_code == 409


async def test_create_comparison_409s_when_company_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="pending")
    competitor_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Competitor(
                id=competitor_id, company_id=company_id, url="https://rival.com", status="complete"
            )
        )
        await session.commit()

    response = await client.post(f"/competitors/{competitor_id}/comparison")

    assert response.status_code == 409


# --- Suggestions -------------------------------------------------------


async def test_suggestions_404s_for_unknown_company(client):
    response = await client.post("/suggestions", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_suggestions_returns_empty_without_api_key(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/suggestions", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["suggestions"] == []
