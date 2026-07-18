"""API tests for the Content Management routes.

Same in-memory-SQLite + AsyncClient/ASGITransport pattern as
`test_companies.py`. The graph-running functions are monkey-patched to
write plausible data directly (rather than calling Claude), so these
tests exercise the actual endpoint logic (404s, request validation,
selectinload of items) without needing a real Anthropic key.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import content_management as content_management_module
from app.db.models import Campaign, Collaboration, CollaborationIdea, Company, ContentItem, ContentPlan, Strategy
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_run_strategy_generation(strategy_id, company_id):
        async with test_session_factory() as session:
            strategy = await session.get(Strategy, strategy_id)
            strategy.status = "complete"
            strategy.summary = "Fake strategy summary."
            strategy.marketing_strategy = "Fake marketing strategy."
            await session.commit()

    async def _fake_run_content_plan_generation(content_plan_id, company_id, strategy_id):
        async with test_session_factory() as session:
            plan = await session.get(ContentPlan, content_plan_id)
            plan.status = "complete"
            session.add(
                ContentItem(
                    id=uuid.uuid4(),
                    content_plan_id=content_plan_id,
                    title="Fake content item",
                    description="Fake description.",
                    content_type="post",
                    platform="linkedin",
                    suggested_date=date.today(),
                )
            )
            await session.commit()

    async def _fake_run_campaign_generation(campaign_id, company_id, content_plan_id, strategy_id):
        async with test_session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            campaign.status = "complete"
            campaign.name = "Fake campaign name."
            campaign.objective = "Fake objective."
            await session.commit()

    async def _fake_run_collaboration_generation(collaboration_id, company_id, strategy_id):
        async with test_session_factory() as session:
            collaboration = await session.get(Collaboration, collaboration_id)
            collaboration.status = "complete"
            session.add(
                CollaborationIdea(
                    id=uuid.uuid4(),
                    collaboration_id=collaboration_id,
                    collaborator_archetype="Fake archetype.",
                    partnership_angle="Fake angle.",
                    outreach_template="Fake template.",
                    priority="medium",
                )
            )
            await session.commit()

    monkeypatch.setattr(
        content_management_module, "run_strategy_generation", _fake_run_strategy_generation
    )
    monkeypatch.setattr(
        content_management_module,
        "run_content_plan_generation",
        _fake_run_content_plan_generation,
    )
    monkeypatch.setattr(
        content_management_module, "run_campaign_generation", _fake_run_campaign_generation
    )
    monkeypatch.setattr(
        content_management_module,
        "run_collaboration_generation",
        _fake_run_collaboration_generation,
    )

    app = FastAPI()
    app.include_router(content_management_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    # url is unique per Company — default to one derived from the id so
    # multiple calls within a single test don't collide.
    defaults = dict(
        id=company_id, url=f"https://example.com/{company_id}", status="complete", name="Acme"
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


# --- Strategies ----------------------------------------------------------


async def test_create_strategy_returns_completed_strategy(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/strategies", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["summary"] == "Fake strategy summary."
    assert body["company_id"] == str(company_id)


async def test_create_strategy_404s_for_unknown_company(client):
    response = await client.post("/strategies", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_strategy_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="scraping")

    response = await client.post("/strategies", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_get_strategy_404s_for_unknown_id(client):
    response = await client.get(f"/strategies/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_strategy_returns_the_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Strategy(id=strategy_id, company_id=company_id, status="complete", summary="Existing summary")
        )
        await session.commit()

    response = await client.get(f"/strategies/{strategy_id}")

    assert response.status_code == 200
    assert response.json()["summary"] == "Existing summary"


async def test_list_strategies_filters_by_company_id(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(Strategy(id=uuid.uuid4(), company_id=company_a, status="complete"))
        session.add(Strategy(id=uuid.uuid4(), company_id=company_b, status="complete"))
        await session.commit()

    response = await client.get("/strategies", params={"company_id": str(company_a)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == str(company_a)


# --- Content plans ---------------------------------------------------------


async def test_create_content_plan_returns_completed_plan_with_items(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/content-plans", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Fake content item"


async def test_create_content_plan_404s_for_unknown_company(client):
    response = await client.post("/content-plans", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_content_plan_404s_for_unknown_strategy(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/content-plans",
        json={"company_id": str(company_id), "strategy_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


async def test_create_content_plan_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="failed")

    response = await client.post("/content-plans", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_create_content_plan_400s_when_strategy_belongs_to_a_different_company(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_b, status="complete"))
        await session.commit()

    response = await client.post(
        "/content-plans",
        json={"company_id": str(company_a), "strategy_id": str(strategy_id)},
    )

    assert response.status_code == 400


async def test_get_content_plan_includes_items(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Existing item",
                description="d",
                content_type="post",
                platform="instagram",
                suggested_date=date.today(),
            )
        )
        await session.commit()

    response = await client.get(f"/content-plans/{plan_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Existing item"


async def test_get_content_plan_404s_for_unknown_id(client):
    response = await client.get(f"/content-plans/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_content_plans_does_not_include_items(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Item",
                description="d",
                content_type="post",
                platform="instagram",
                suggested_date=date.today(),
            )
        )
        await session.commit()

    response = await client.get("/content-plans", params={"company_id": str(company_id)})

    body = response.json()
    assert body["total"] == 1
    assert "items" not in body["items"][0]  # list view is a summary, no nested content items


# --- Campaigns ---------------------------------------------------------


async def test_create_campaign_returns_completed_campaign(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/campaigns", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["name"] == "Fake campaign name."
    assert body["lifecycle_stage"] == "draft"


async def test_create_campaign_404s_for_unknown_company(client):
    response = await client.post("/campaigns", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_campaign_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="pending")

    response = await client.post("/campaigns", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_create_campaign_400s_when_content_plan_belongs_to_a_different_company(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_b, status="complete"))
        await session.commit()

    response = await client.post(
        "/campaigns", json={"company_id": str(company_a), "content_plan_id": str(plan_id)}
    )

    assert response.status_code == 400


async def test_create_campaign_400s_when_strategy_belongs_to_a_different_company(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_b, status="complete"))
        await session.commit()

    response = await client.post(
        "/campaigns", json={"company_id": str(company_a), "strategy_id": str(strategy_id)}
    )

    assert response.status_code == 400


async def test_get_campaign_404s_for_unknown_id(client):
    response = await client.get(f"/campaigns/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_campaigns_filters_by_company_id(client, test_session_factory):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(Campaign(id=uuid.uuid4(), company_id=company_a, status="complete"))
        session.add(Campaign(id=uuid.uuid4(), company_id=company_b, status="complete"))
        await session.commit()

    response = await client.get("/campaigns", params={"company_id": str(company_a)})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == str(company_a)


async def test_update_campaign_lifecycle_persists_new_stage(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    campaign_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Campaign(id=campaign_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/campaigns/{campaign_id}/lifecycle", json={"lifecycle_stage": "active"}
    )

    assert response.status_code == 200
    assert response.json()["lifecycle_stage"] == "active"

    get_response = await client.get(f"/campaigns/{campaign_id}")
    assert get_response.json()["lifecycle_stage"] == "active"


async def test_update_campaign_lifecycle_404s_for_unknown_id(client):
    response = await client.patch(
        f"/campaigns/{uuid.uuid4()}/lifecycle", json={"lifecycle_stage": "active"}
    )
    assert response.status_code == 404


async def test_update_campaign_lifecycle_422s_for_invalid_stage(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    campaign_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Campaign(id=campaign_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/campaigns/{campaign_id}/lifecycle", json={"lifecycle_stage": "not-a-real-stage"}
    )

    assert response.status_code == 422


# --- Collaborations ---------------------------------------------------------


async def test_create_collaboration_returns_completed_collaboration_with_ideas(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/collaborations", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert len(body["ideas"]) == 1
    assert body["ideas"][0]["collaborator_archetype"] == "Fake archetype."


async def test_create_collaboration_404s_for_unknown_company(client):
    response = await client.post("/collaborations", json={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_create_collaboration_409s_when_company_profile_not_ready(client, test_session_factory):
    company_id = await _seed_company(test_session_factory, status="complete_no_profile")

    response = await client.post("/collaborations", json={"company_id": str(company_id)})

    assert response.status_code == 409


async def test_create_collaboration_400s_when_strategy_belongs_to_a_different_company(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_b, status="complete"))
        await session.commit()

    response = await client.post(
        "/collaborations", json={"company_id": str(company_a), "strategy_id": str(strategy_id)}
    )

    assert response.status_code == 400


async def test_get_collaboration_includes_ideas(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    collaboration_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Collaboration(id=collaboration_id, company_id=company_id, status="complete"))
        session.add(
            CollaborationIdea(
                id=uuid.uuid4(),
                collaboration_id=collaboration_id,
                collaborator_archetype="Existing archetype",
                partnership_angle="a",
                outreach_template="t",
                priority="low",
            )
        )
        await session.commit()

    response = await client.get(f"/collaborations/{collaboration_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["ideas"]) == 1
    assert body["ideas"][0]["collaborator_archetype"] == "Existing archetype"


async def test_get_collaboration_404s_for_unknown_id(client):
    response = await client.get(f"/collaborations/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_collaborations_does_not_include_ideas(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    collaboration_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Collaboration(id=collaboration_id, company_id=company_id, status="complete"))
        session.add(
            CollaborationIdea(
                id=uuid.uuid4(),
                collaboration_id=collaboration_id,
                collaborator_archetype="Archetype",
                partnership_angle="a",
                outreach_template="t",
                priority="low",
            )
        )
        await session.commit()

    response = await client.get("/collaborations", params={"company_id": str(company_id)})

    body = response.json()
    assert body["total"] == 1
    assert "ideas" not in body["items"][0]
