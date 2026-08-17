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
from sqlalchemy import select

from app.api.v1.endpoints import content_management as content_management_module
from app.db.models import Campaign, Collaboration, CollaborationIdea, Company, ContentItem, ContentPlan, Strategy
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_run_strategy_generation(strategy_id, company_id):
        async with test_session_factory() as session:
            strategy = await session.get(Strategy, strategy_id)
            strategy.status = "complete"
            strategy.summary = "Fake strategy summary."
            strategy.marketing_strategy = "Fake marketing strategy."
            await session.commit()

    async def _fake_run_content_plan_generation(content_plan_id, company_id, strategy_id, days=None):
        async with test_session_factory() as session:
            plan = await session.get(ContentPlan, content_plan_id)
            plan.status = "complete"
            session.add(
                ContentItem(
                    id=uuid.uuid4(),
                    content_plan_id=content_plan_id,
                    title="Fake content item",
                    description="Fake description.",
                    draft_copy="Fake ready-to-publish caption.",
                    content_type="post",
                    platform="linkedin",
                    suggested_date=date.today(),
                    # Records the received `days` so tests can assert the
                    # request payload's `days` field actually reached the
                    # generation call, without a separate capture fixture.
                    theme=f"days={days}",
                )
            )
            await session.commit()

    async def _fake_regenerate_item_draft_copy(item_id):
        async with test_session_factory() as session:
            item = await session.get(ContentItem, item_id)
            if item is None:
                return None, False
            item.draft_copy = "Regenerated ready-to-publish caption."
            await session.commit()
            await session.refresh(item)
            return item, True

    async def _fake_run_campaign_generation(campaign_id, company_id, content_plan_id, strategy_id):
        async with test_session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            campaign.status = "complete"
            campaign.name = "Fake campaign name."
            campaign.objective = "Fake objective."
            await session.commit()

    async def _fake_check_content_quality(draft_copy, brand_voice, platform):
        if draft_copy == "trigger-failure":
            from app.agents.content_management.quality_check import QualityCheckResult

            return QualityCheckResult(), False
        from app.agents.content_management.quality_check import QualityCheckResult

        if "off-brand" in draft_copy:
            return (
                QualityCheckResult(
                    passed=False, issues=["Tone doesn't match brand voice."], notes="Needs edits."
                ),
                True,
            )
        return QualityCheckResult(passed=True, issues=[], notes="Reads well."), True

    async def _fake_generate_creative_brief(context, title, description, platform, content_type):
        from app.agents.content_management.creative_brief import GeneratedCreativeBrief

        if title == "trigger-failure":
            return GeneratedCreativeBrief(), False
        return (
            GeneratedCreativeBrief(
                hook="Fake hook.",
                shot_list=["Shot one", "Shot two"],
                visual_references="Fake visual references.",
                editing_notes="Fake editing notes.",
                thumbnail_concept="Fake thumbnail concept.",
            ),
            True,
        )

    async def _fake_repurpose_content_item(
        context, source_title, source_draft_copy, target_platform, target_content_type
    ):
        from app.agents.content_management.schemas import GeneratedContentItem

        if source_title == "trigger-failure":
            return None, False
        return (
            GeneratedContentItem(
                title=f"Repurposed: {source_title}",
                description="Fake repurposed description.",
                content_type=target_content_type,
                platform=target_platform,
                suggested_date=date.today(),
                draft_copy="Fake repurposed ready-to-publish caption.",
                hashtags=["repurposed"],
            ),
            True,
        )

    async def _fake_create_manual_item(company_id, topic, platform, content_type, media_url=None, trend_id=None):
        # Replaces the real create_manual_item wholesale (same reason
        # _fake_regenerate_item_draft_copy below replaces the whole
        # function rather than just its inner Claude call): the real one
        # opens its own session via the production async_session_factory,
        # which isn't the test's isolated test_session_factory — faking
        # only the Claude-call layer would leave that real production
        # session open against the test's event loop. This still exercises
        # the real get-or-create-manual-plan + persist behavior, just with
        # the test session.
        if topic == "trigger-failure":
            return None, False
        async with test_session_factory() as session:
            manual_plan = (
                await session.execute(
                    select(ContentPlan).where(
                        ContentPlan.company_id == company_id, ContentPlan.is_manual.is_(True)
                    )
                )
            ).scalar_one_or_none()
            if manual_plan is None:
                manual_plan = ContentPlan(
                    id=uuid.uuid4(), company_id=company_id, status="complete", is_manual=True
                )
                session.add(manual_plan)
                await session.flush()
            item = ContentItem(
                id=uuid.uuid4(),
                content_plan_id=manual_plan.id,
                title=f"Manual: {topic}",
                description="Fake manual description.",
                content_type=content_type,
                platform=platform,
                suggested_date=date.today(),
                draft_copy="Fake manual ready-to-publish caption.",
                hashtags=["fake", "manual"],
                approval_status="pending",
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return item, True

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
        content_management_module,
        "regenerate_item_draft_copy",
        _fake_regenerate_item_draft_copy,
    )
    monkeypatch.setattr(
        content_management_module,
        "create_manual_item",
        _fake_create_manual_item,
    )
    monkeypatch.setattr(
        content_management_module, "check_content_quality", _fake_check_content_quality
    )
    monkeypatch.setattr(
        content_management_module, "generate_creative_brief", _fake_generate_creative_brief
    )
    monkeypatch.setattr(
        content_management_module, "repurpose_content_item", _fake_repurpose_content_item
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
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    # url is unique per Company — default to one derived from the id so
    # multiple calls within a single test don't collide.
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


# --- Approval queue --------------------------------------------------------


async def test_pending_approvals_empty_state(client):
    response = await client.get("/approvals/pending")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


async def test_pending_approvals_includes_pending_strategies_and_content_items(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory, name="Acme")
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Strategy(
                id=uuid.uuid4(),
                company_id=company_id,
                status="complete",
                summary="Pending strategy summary",
                approval_status="pending",
            )
        )
        session.add(
            Strategy(
                id=uuid.uuid4(),
                company_id=company_id,
                status="complete",
                approval_status="approved",
            )
        )
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Pending item",
                description="d",
                content_type="post",
                platform="linkedin",
                suggested_date=date.today(),
                approval_status="pending",
            )
        )
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Rejected item",
                description="d",
                content_type="post",
                platform="linkedin",
                suggested_date=date.today(),
                approval_status="rejected",
            )
        )
        await session.commit()

    response = await client.get("/approvals/pending")
    body = response.json()
    assert body["total"] == 2
    types = {item["type"] for item in body["items"]}
    assert types == {"strategy", "content_item"}
    for item in body["items"]:
        assert item["company_name"] == "Acme"
        assert item["company_id"] == str(company_id)


async def test_pending_approvals_excludes_other_companies_never_leaking(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory, name="A")
    company_b = await _seed_company(test_session_factory, name="B")
    async with test_session_factory() as session:
        session.add(
            Strategy(id=uuid.uuid4(), company_id=company_a, status="complete", approval_status="pending")
        )
        session.add(
            Strategy(id=uuid.uuid4(), company_id=company_b, status="complete", approval_status="pending")
        )
        await session.commit()

    response = await client.get("/approvals/pending")
    company_ids = {item["company_id"] for item in response.json()["items"]}
    assert company_ids == {str(company_a), str(company_b)}


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


async def test_new_strategies_default_to_pending_approval(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/strategies", json={"company_id": str(company_id)})

    assert response.json()["approval_status"] == "pending"


async def test_update_strategy_approval_sets_approved(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval", json={"approval_status": "approved"}
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"


async def test_update_strategy_approval_sets_reviewer(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Strategy(id=strategy_id, company_id=company_id, status="complete", approval_status="pending")
        )
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval",
        json={"approval_status": "pending", "reviewer": "Priya"},
    )

    assert response.status_code == 200
    assert response.json()["reviewer"] == "Priya"
    # Assigning a reviewer alone doesn't itself approve/reject anything.
    assert response.json()["approval_status"] == "pending"


async def test_strategy_reviewer_appears_in_pending_approvals_queue(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Strategy(id=strategy_id, company_id=company_id, status="complete", approval_status="pending")
        )
        await session.commit()
    await client.patch(
        f"/strategies/{strategy_id}/approval",
        json={"approval_status": "pending", "reviewer": "Priya"},
    )

    response = await client.get("/approvals/pending")

    assert response.status_code == 200
    matching = [i for i in response.json()["items"] if i["id"] == str(strategy_id)]
    assert len(matching) == 1
    assert matching[0]["reviewer"] == "Priya"


async def test_approving_a_strategy_indexes_it_into_the_knowledge_base(
    client, test_session_factory, monkeypatch
):
    import app.agents.knowledge_base.ingestion as ingestion_module
    from app.db.models import Document

    async def _fake_embed(texts):
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)

    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Strategy(
                id=strategy_id,
                company_id=company_id,
                status="complete",
                summary="Lean into short-form video.",
                marketing_strategy="Focus on Instagram Reels weekly.",
            )
        )
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval", json={"approval_status": "approved"}
    )
    assert response.status_code == 200

    async with test_session_factory() as session:
        docs = (
            (
                await session.execute(
                    select(Document).where(
                        Document.company_id == company_id, Document.source_type == "strategy"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(docs) == 1
    assert docs[0].source_url == f"strategy://{strategy_id}"
    assert "short-form video" in docs[0].content


async def test_update_strategy_approval_records_approved_by(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval",
        json={"approval_status": "approved", "approved_by": "Priya"},
    )

    assert response.status_code == 200
    assert response.json()["approved_by"] == "Priya"


async def test_update_strategy_approval_sets_rejected(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval", json={"approval_status": "rejected"}
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"


async def test_update_strategy_approval_404s_for_unknown_id(client):
    response = await client.patch(
        f"/strategies/{uuid.uuid4()}/approval", json={"approval_status": "approved"}
    )
    assert response.status_code == 404


async def test_update_strategy_approval_rejects_invalid_value(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    strategy_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Strategy(id=strategy_id, company_id=company_id, status="complete"))
        await session.commit()

    response = await client.patch(
        f"/strategies/{strategy_id}/approval", json={"approval_status": "maybe"}
    )

    assert response.status_code == 422


# --- Content plans ---------------------------------------------------------


async def test_create_content_plan_returns_completed_plan_with_items(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/content-plans", json={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Fake content item"
    assert body["items"][0]["draft_copy"] == "Fake ready-to-publish caption."


async def test_create_content_plan_passes_days_through(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        "/content-plans", json={"company_id": str(company_id), "days": 30}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["theme"] == "days=30"


async def test_create_content_plan_defaults_days_when_omitted(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post("/content-plans", json={"company_id": str(company_id)})

    assert response.status_code == 200
    assert response.json()["items"][0]["theme"] == "days=None"


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


# --- Manual content items -------------------------------------------------


async def test_create_manual_content_item_returns_generated_item(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "our new office opening"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Manual: our new office opening"
    assert body["draft_copy"] == "Fake manual ready-to-publish caption."
    assert body["platform"] == "linkedin"
    assert body["approval_status"] == "pending"
    assert body["hashtags"] == ["fake", "manual"]


async def test_create_manual_content_item_accepts_new_platform_and_content_type_values(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "threads", "content_type": "newsletter", "topic": "a monthly roundup"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "threads"
    assert body["content_type"] == "newsletter"


async def test_update_content_item_sets_hashtags(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(
        f"/content-items/{item_id}", json={"hashtags": ["launch", "smallbiz"]}
    )

    assert response.status_code == 200
    assert response.json()["hashtags"] == ["launch", "smallbiz"]


async def test_update_content_item_sets_reviewer(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(f"/content-items/{item_id}", json={"reviewer": "Priya"})

    assert response.status_code == 200
    assert response.json()["reviewer"] == "Priya"


async def test_update_content_item_reviewer_survives_a_pure_reschedule(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)
    await client.patch(f"/content-items/{item_id}", json={"reviewer": "Priya"})

    response = await client.patch(
        f"/content-items/{item_id}", json={"suggested_date": "2026-12-25"}
    )

    assert response.status_code == 200
    assert response.json()["reviewer"] == "Priya"


async def test_content_item_reviewer_appears_in_pending_approvals_queue(
    client, test_session_factory
):
    item_id, _ = await _seed_content_item(test_session_factory)
    await client.patch(f"/content-items/{item_id}", json={"reviewer": "Priya"})

    response = await client.get("/approvals/pending")

    assert response.status_code == 200
    items = response.json()["items"]
    matching = [i for i in items if i["id"] == str(item_id)]
    assert len(matching) == 1
    assert matching[0]["reviewer"] == "Priya"


async def test_create_manual_content_item_reuses_the_same_manual_plan(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    first = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "topic one"},
    )
    second = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "instagram", "content_type": "post", "topic": "topic two"},
    )

    async with test_session_factory() as session:
        from sqlalchemy import select

        plans = (
            (await session.execute(select(ContentPlan).where(ContentPlan.company_id == company_id)))
            .scalars()
            .all()
        )
    manual_plans = [p for p in plans if p.is_manual]
    assert len(manual_plans) == 1
    assert first.json()["id"] != second.json()["id"]  # different items
    # but the same underlying plan, confirmed via GET
    plan_detail = await client.get(f"/content-plans/{manual_plans[0].id}")
    assert len(plan_detail.json()["items"]) == 2


async def test_create_manual_content_item_does_not_mix_with_generated_plans(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    await client.post("/content-plans", json={"company_id": str(company_id)})
    await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "topic"},
    )

    listing = await client.get(f"/content-plans?company_id={company_id}")
    plans = listing.json()["items"]
    assert len(plans) == 2
    assert sum(1 for p in plans if p["is_manual"]) == 1
    assert sum(1 for p in plans if not p["is_manual"]) == 1


async def test_create_manual_content_item_404s_for_unknown_company(client):
    response = await client.post(
        f"/content-plans/{uuid.uuid4()}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "topic"},
    )
    assert response.status_code == 404


async def test_create_manual_content_item_409s_when_company_profile_not_ready(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory, status="pending")

    response = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "topic"},
    )
    assert response.status_code == 409


async def test_create_manual_content_item_502s_on_generation_failure(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/content-plans/{company_id}/manual-item",
        json={"platform": "linkedin", "content_type": "post", "topic": "trigger-failure"},
    )
    assert response.status_code == 502


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


# --- Content items (approval + reschedule) ----------------------------------


async def _seed_content_item(test_session_factory, **overrides) -> tuple[uuid.UUID, uuid.UUID]:
    company_id = await _seed_company(test_session_factory)
    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    defaults = dict(
        id=item_id,
        content_plan_id=plan_id,
        title="Item",
        description="d",
        content_type="post",
        platform="instagram",
        suggested_date=date.today(),
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(ContentItem(**defaults))
        await session.commit()
    return item_id, plan_id


async def test_update_content_item_sets_approval_status(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(f"/content-items/{item_id}", json={"approval_status": "approved"})

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"


async def test_update_content_item_rejects(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(f"/content-items/{item_id}", json={"approval_status": "rejected"})

    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"


async def test_update_content_item_reschedules_suggested_date(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)
    new_date = "2026-12-25"

    response = await client.patch(f"/content-items/{item_id}", json={"suggested_date": new_date})

    assert response.status_code == 200
    assert response.json()["suggested_date"] == new_date


async def test_update_content_item_can_set_both_fields_at_once(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(
        f"/content-items/{item_id}",
        json={"approval_status": "approved", "suggested_date": "2026-12-25"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"
    assert body["suggested_date"] == "2026-12-25"


async def test_update_content_item_404s_for_unknown_id(client):
    response = await client.patch(
        f"/content-items/{uuid.uuid4()}", json={"approval_status": "approved"}
    )
    assert response.status_code == 404


async def test_update_content_item_rejects_invalid_approval_status(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(f"/content-items/{item_id}", json={"approval_status": "maybe"})

    assert response.status_code == 422


async def test_update_content_item_records_approved_by(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(
        f"/content-items/{item_id}",
        json={"approval_status": "approved", "approved_by": "Priya"},
    )

    assert response.status_code == 200
    assert response.json()["approved_by"] == "Priya"


async def test_approving_a_content_item_indexes_it_into_the_knowledge_base(
    client, test_session_factory, monkeypatch
):
    import app.agents.knowledge_base.ingestion as ingestion_module
    from app.db.models import Document

    async def _fake_embed(texts):
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)

    item_id, plan_id = await _seed_content_item(
        test_session_factory, draft_copy="A real approved caption about our new product."
    )
    async with test_session_factory() as session:
        company_id = (await session.get(ContentPlan, plan_id)).company_id

    response = await client.patch(
        f"/content-items/{item_id}", json={"approval_status": "approved"}
    )
    assert response.status_code == 200

    async with test_session_factory() as session:
        docs = (
            (
                await session.execute(
                    select(Document).where(
                        Document.company_id == company_id, Document.source_type == "content_item"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(docs) == 1
    assert docs[0].source_url == f"content-item://{item_id}"
    assert "approved caption" in docs[0].content


async def test_rejecting_a_content_item_does_not_index_it(
    client, test_session_factory, monkeypatch
):
    import app.agents.knowledge_base.ingestion as ingestion_module
    from app.db.models import Document

    async def _fake_embed(texts):
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)

    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="A rejected caption.")

    response = await client.patch(f"/content-items/{item_id}", json={"approval_status": "rejected"})
    assert response.status_code == 200

    async with test_session_factory() as session:
        docs = (
            (await session.execute(select(Document).where(Document.source_type == "content_item")))
            .scalars()
            .all()
        )
    assert docs == []


async def test_quality_check_persists_passing_result(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="A great draft.")

    response = await client.post(f"/content-items/{item_id}/quality-check")

    assert response.status_code == 200
    body = response.json()
    assert body["quality_check_passed"] is True
    assert body["quality_check_notes"] == "Reads well."


async def test_quality_check_persists_failing_result_with_issues(client, test_session_factory):
    item_id, _ = await _seed_content_item(
        test_session_factory, draft_copy="An off-brand draft."
    )

    response = await client.post(f"/content-items/{item_id}/quality-check")

    assert response.status_code == 200
    body = response.json()
    assert body["quality_check_passed"] is False
    assert "Tone doesn't match" in body["quality_check_notes"]
    assert "Needs edits." in body["quality_check_notes"]


async def test_quality_check_404s_for_unknown_item(client):
    response = await client.post(f"/content-items/{uuid.uuid4()}/quality-check")
    assert response.status_code == 404


async def test_quality_check_400s_when_no_draft_copy_yet(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy=None)

    response = await client.post(f"/content-items/{item_id}/quality-check")
    assert response.status_code == 400


async def test_quality_check_502s_on_generation_failure(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="trigger-failure")

    response = await client.post(f"/content-items/{item_id}/quality-check")
    assert response.status_code == 502


async def test_creative_brief_generates_and_persists(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, title="Some reel")

    response = await client.post(f"/content-items/{item_id}/creative-brief")

    assert response.status_code == 200
    body = response.json()
    assert body["content_item_id"] == str(item_id)
    assert body["hook"] == "Fake hook."
    assert body["shot_list"] == ["Shot one", "Shot two"]
    assert body["thumbnail_concept"] == "Fake thumbnail concept."


async def test_creative_brief_get_fetches_the_generated_brief(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, title="Some reel")
    await client.post(f"/content-items/{item_id}/creative-brief")

    response = await client.get(f"/content-items/{item_id}/creative-brief")

    assert response.status_code == 200
    assert response.json()["hook"] == "Fake hook."


async def test_creative_brief_get_404s_before_generation(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.get(f"/content-items/{item_id}/creative-brief")
    assert response.status_code == 404


async def test_creative_brief_404s_for_unknown_item(client):
    response = await client.post(f"/content-items/{uuid.uuid4()}/creative-brief")
    assert response.status_code == 404


async def test_creative_brief_502s_on_generation_failure(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, title="trigger-failure")

    response = await client.post(f"/content-items/{item_id}/creative-brief")
    assert response.status_code == 502


async def test_creative_brief_regeneration_overwrites_the_previous_one(
    client, test_session_factory, monkeypatch
):
    item_id, _ = await _seed_content_item(test_session_factory, title="Some reel")
    await client.post(f"/content-items/{item_id}/creative-brief")

    async def _fake_regenerated(context, title, description, platform, content_type):
        from app.agents.content_management.creative_brief import GeneratedCreativeBrief

        return (
            GeneratedCreativeBrief(
                hook="Updated hook.",
                shot_list=["New shot"],
                visual_references="Updated references.",
                editing_notes="Updated notes.",
                thumbnail_concept="",
            ),
            True,
        )

    monkeypatch.setattr(content_management_module, "generate_creative_brief", _fake_regenerated)

    response = await client.post(f"/content-items/{item_id}/creative-brief")

    assert response.status_code == 200
    body = response.json()
    assert body["hook"] == "Updated hook."
    assert body["shot_list"] == ["New shot"]


async def test_update_content_item_reschedule_alone_does_not_set_approved_by(
    client, test_session_factory
):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.patch(
        f"/content-items/{item_id}",
        json={"suggested_date": "2026-12-25", "approved_by": "Priya"},
    )

    assert response.status_code == 200
    # approved_by is attribution for an approval action — a pure reschedule
    # with no approval_status in the payload shouldn't set it.
    assert response.json()["approved_by"] is None


async def test_regenerate_content_item_draft_updates_draft_copy(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Stale draft.")

    response = await client.post(f"/content-items/{item_id}/regenerate-draft")

    assert response.status_code == 200
    assert response.json()["draft_copy"] == "Regenerated ready-to-publish caption."


async def test_regenerate_content_item_draft_404s_for_unknown_id(client):
    response = await client.post(f"/content-items/{uuid.uuid4()}/regenerate-draft")

    assert response.status_code == 404


async def test_regenerate_content_item_draft_502s_on_generation_failure(
    client, test_session_factory, monkeypatch
):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Original draft.")

    async def _failing_regenerate(item_id):
        from app.db.models import ContentItem as _ContentItem

        async with test_session_factory() as session:
            item = await session.get(_ContentItem, item_id)
            return item, False

    monkeypatch.setattr(
        content_management_module, "regenerate_item_draft_copy", _failing_regenerate
    )

    response = await client.post(f"/content-items/{item_id}/regenerate-draft")

    assert response.status_code == 502


async def test_repurpose_content_item_creates_a_new_item_in_the_manual_plan(
    client, test_session_factory
):
    item_id, source_plan_id = await _seed_content_item(
        test_session_factory, title="Original LinkedIn post", draft_copy="A long professional take."
    )

    response = await client.post(
        f"/content-items/{item_id}/repurpose", json={"platform": "instagram", "content_type": "story"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Repurposed: Original LinkedIn post"
    assert body["platform"] == "instagram"
    assert body["content_type"] == "story"
    assert body["repurposed_from_id"] == str(item_id)
    assert body["hashtags"] == ["repurposed"]
    assert body["approval_status"] == "pending"

    # Lands in the manual plan, not the source item's own plan.
    async with test_session_factory() as session:
        from app.db.models import ContentItem as _ContentItem

        new_item = await session.get(_ContentItem, uuid.UUID(body["id"]))
        assert new_item.content_plan_id != source_plan_id


async def test_repurpose_content_item_404s_for_unknown_source(client):
    response = await client.post(
        f"/content-items/{uuid.uuid4()}/repurpose", json={"platform": "instagram", "content_type": "story"}
    )
    assert response.status_code == 404


async def test_repurpose_content_item_400s_when_source_has_no_draft_copy(
    client, test_session_factory
):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy=None)

    response = await client.post(
        f"/content-items/{item_id}/repurpose", json={"platform": "instagram", "content_type": "story"}
    )
    assert response.status_code == 400


async def test_repurpose_content_item_502s_on_generation_failure(client, test_session_factory):
    item_id, _ = await _seed_content_item(
        test_session_factory, title="trigger-failure", draft_copy="Copy."
    )

    response = await client.post(
        f"/content-items/{item_id}/repurpose", json={"platform": "instagram", "content_type": "story"}
    )
    assert response.status_code == 502


async def test_list_content_items_is_empty_by_default(client):
    response = await client.get("/content-items")
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_list_content_items_includes_company_context(client, test_session_factory):
    item_id, plan_id = await _seed_content_item(
        test_session_factory, platform="linkedin", draft_copy="A draft."
    )
    async with test_session_factory() as session:
        plan = await session.get(ContentPlan, plan_id)
        company_id = plan.company_id

    response = await client.get("/content-items")
    body = response.json()["items"]
    assert len(body) == 1
    assert body[0]["id"] == str(item_id)
    assert body[0]["company_id"] == str(company_id)
    assert body[0]["company_name"] == "Acme"
    assert body[0]["platform"] == "linkedin"


async def test_list_content_items_filters_by_company_id(client, test_session_factory):
    _, plan_a = await _seed_content_item(test_session_factory)
    _, plan_b = await _seed_content_item(test_session_factory)
    async with test_session_factory() as session:
        company_a = (await session.get(ContentPlan, plan_a)).company_id

    response = await client.get(f"/content-items?company_id={company_a}")
    assert len(response.json()["items"]) == 1


async def test_list_content_items_filters_by_platform(client, test_session_factory):
    await _seed_content_item(test_session_factory, platform="instagram")
    await _seed_content_item(test_session_factory, platform="linkedin")

    response = await client.get("/content-items?platform=linkedin")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["platform"] == "linkedin"


# --- Scheduling ------------------------------------------------------------


async def test_schedule_content_item_sets_scheduled_at(client, test_session_factory):
    from datetime import datetime, timezone

    item_id, _ = await _seed_content_item(test_session_factory)
    when = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)

    response = await client.post(
        f"/content-items/{item_id}/schedule", json={"scheduled_at": when.isoformat()}
    )

    assert response.status_code == 200
    assert response.json()["scheduled_at"] is not None


async def test_schedule_content_item_can_clear_the_schedule(client, test_session_factory):
    from datetime import datetime, timezone

    item_id, _ = await _seed_content_item(
        test_session_factory, scheduled_at=datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    response = await client.post(f"/content-items/{item_id}/schedule", json={"scheduled_at": None})

    assert response.status_code == 200
    assert response.json()["scheduled_at"] is None


async def test_schedule_content_item_404s_for_unknown_item(client):
    response = await client.post(
        f"/content-items/{uuid.uuid4()}/schedule", json={"scheduled_at": None}
    )
    assert response.status_code == 404


async def test_schedule_content_item_409s_when_already_published(client, test_session_factory):
    from datetime import datetime, timezone

    item_id, _ = await _seed_content_item(
        test_session_factory, published_at=datetime.now(timezone.utc)
    )

    response = await client.post(
        f"/content-items/{item_id}/schedule",
        json={"scheduled_at": datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat()},
    )
    assert response.status_code == 409


async def test_new_content_items_default_to_pending_approval(client, test_session_factory):
    _, plan_id = await _seed_content_item(test_session_factory)

    response = await client.get(f"/content-plans/{plan_id}")

    assert response.status_code == 200
    assert response.json()["items"][0]["approval_status"] == "pending"


# --- Draft Workspace: editable draft_copy, revisions, comments -----------


async def test_update_content_item_draft_copy_edits_it(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Original draft.")

    response = await client.patch(
        f"/content-items/{item_id}", json={"draft_copy": "Hand-edited draft."}
    )

    assert response.status_code == 200
    assert response.json()["draft_copy"] == "Hand-edited draft."


async def test_update_content_item_draft_copy_creates_a_revision(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Original draft.")

    await client.patch(
        f"/content-items/{item_id}",
        json={"draft_copy": "Hand-edited draft.", "edited_by": "Priya"},
    )

    revisions = await client.get(f"/content-items/{item_id}/revisions")
    assert revisions.status_code == 200
    items = revisions.json()["items"]
    assert len(items) == 1
    # The revision holds the OLD value, not the new one.
    assert items[0]["draft_copy"] == "Original draft."
    assert items[0]["edited_by"] == "Priya"


async def test_update_content_item_draft_copy_noop_creates_no_revision(
    client, test_session_factory
):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Same draft.")

    await client.patch(f"/content-items/{item_id}", json={"draft_copy": "Same draft."})

    revisions = await client.get(f"/content-items/{item_id}/revisions")
    assert revisions.json()["items"] == []


async def test_update_content_item_multiple_edits_create_multiple_revisions(
    client, test_session_factory
):
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="v1")

    await client.patch(f"/content-items/{item_id}", json={"draft_copy": "v2"})
    await client.patch(f"/content-items/{item_id}", json={"draft_copy": "v3"})

    revisions = (await client.get(f"/content-items/{item_id}/revisions")).json()["items"]
    assert sorted(r["draft_copy"] for r in revisions) == ["v1", "v2"]


async def test_regenerate_content_item_draft_endpoint_still_returns_ok(
    client, test_session_factory
):
    # This fixture's `regenerate_item_draft_copy` is faked out entirely
    # (see the `client` fixture above), so it doesn't exercise the real
    # revision-snapshotting behavior — that's covered directly against the
    # real function in tests/agents/content_management/test_content_plan_graph.py.
    # This just confirms the endpoint itself still round-trips correctly.
    item_id, _ = await _seed_content_item(test_session_factory, draft_copy="Stale draft.")

    response = await client.post(f"/content-items/{item_id}/regenerate-draft")

    assert response.status_code == 200


async def test_list_content_item_comments_empty_by_default(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    response = await client.get(f"/content-items/{item_id}/comments")

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_create_and_list_content_item_comment(client, test_session_factory):
    item_id, _ = await _seed_content_item(test_session_factory)

    created = await client.post(
        f"/content-items/{item_id}/comments",
        json={"body": "This needs a stronger hook.", "author": "Priya"},
    )
    assert created.status_code == 200
    assert created.json()["body"] == "This needs a stronger hook."
    assert created.json()["author"] == "Priya"

    listed = await client.get(f"/content-items/{item_id}/comments")
    assert len(listed.json()["items"]) == 1


async def test_create_content_item_comment_404s_for_unknown_item(client):
    response = await client.post(
        f"/content-items/{uuid.uuid4()}/comments", json={"body": "hi"}
    )
    assert response.status_code == 404


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
