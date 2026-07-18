"""Tests for the Campaign Manager LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.agents.content_management import campaign_graph as graph_module
from app.agents.content_management.schemas import GeneratedCampaign
from app.db.models import Campaign, Company, ContentItem, ContentPlan, Strategy, Trend


async def _stub_generate_campaign(context: str):
    return (
        GeneratedCampaign(
            name="Sourdough Summer Push",
            objective="Drive foot traffic.",
            budget_allocation="60% Instagram, 40% local partnerships.",
            success_metrics="Foot traffic, engagement rate.",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 8, 3),
        ),
        True,
    )


async def _stub_generate_campaign_failed(context: str):
    return GeneratedCampaign(), False


async def test_run_campaign_generation_persists_a_complete_campaign(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_campaign", _stub_generate_campaign)

    company_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(Campaign(id=campaign_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_campaign_generation(campaign_id, company_id, None, None)

    async with test_session_factory() as session:
        campaign = await session.get(Campaign, campaign_id)

    assert campaign.status == "complete"
    assert campaign.name == "Sourdough Summer Push"
    assert campaign.start_date == date(2026, 7, 20)


async def test_run_campaign_generation_seeds_timeline_context_from_content_plan(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str):
        captured_context["value"] = context
        return GeneratedCampaign(), True

    monkeypatch.setattr(graph_module, "generate_campaign", _capturing_generate)

    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    today = date.today()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Item 1",
                description="d",
                content_type="post",
                platform="instagram",
                suggested_date=today,
            )
        )
        session.add(
            ContentItem(
                id=uuid.uuid4(),
                content_plan_id=plan_id,
                title="Item 2",
                description="d",
                content_type="post",
                platform="instagram",
                suggested_date=today + timedelta(days=13),
            )
        )
        session.add(Campaign(id=campaign_id, company_id=company_id, content_plan_id=plan_id, status="pending"))
        await session.commit()

    await graph_module.run_campaign_generation(campaign_id, company_id, plan_id, None)

    assert today.isoformat() in captured_context["value"]
    assert (today + timedelta(days=13)).isoformat() in captured_context["value"]


async def test_run_campaign_generation_includes_strategy_context(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str):
        captured_context["value"] = context
        return GeneratedCampaign(), True

    monkeypatch.setattr(graph_module, "generate_campaign", _capturing_generate)

    company_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Strategy(
                id=strategy_id,
                company_id=company_id,
                status="complete",
                marketing_strategy="Lead with automation.",
            )
        )
        session.add(Campaign(id=campaign_id, company_id=company_id, strategy_id=strategy_id, status="pending"))
        await session.commit()

    await graph_module.run_campaign_generation(campaign_id, company_id, None, strategy_id)

    assert "Lead with automation." in captured_context["value"]


async def test_run_campaign_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_campaign", _stub_generate_campaign_failed)

    company_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(Campaign(id=campaign_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_campaign_generation(campaign_id, company_id, None, None)

    async with test_session_factory() as session:
        campaign = await session.get(Campaign, campaign_id)

    assert campaign.status == "failed"
    assert campaign.status_error is not None


async def test_run_campaign_generation_marks_failed_when_company_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_campaign", _stub_generate_campaign)

    campaign_id = uuid.uuid4()
    missing_company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Campaign(id=campaign_id, company_id=missing_company_id, status="pending"))
        await session.commit()

    await graph_module.run_campaign_generation(campaign_id, missing_company_id, None, None)

    async with test_session_factory() as session:
        campaign = await session.get(Campaign, campaign_id)

    assert campaign.status == "failed"
    assert campaign.status_error == "Company not found"
