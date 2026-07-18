"""Tests for the Brand Collaboration LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.content_management import collaboration_graph as graph_module
from app.agents.content_management.schemas import GeneratedCollaboration, GeneratedCollaborationIdea
from app.db.models import Collaboration, CollaborationIdea, Company, Strategy, Trend


async def _stub_generate_collaboration(context: str):
    return (
        GeneratedCollaboration(
            ideas=[
                GeneratedCollaborationIdea(
                    collaborator_archetype="Micro-influencer food bloggers",
                    partnership_angle="Free tasting for a post.",
                    outreach_template="Hi! We'd love to host you...",
                    priority="high",
                    rationale="Strong audience overlap.",
                ),
            ]
        ),
        True,
    )


async def _stub_generate_collaboration_failed(context: str):
    return GeneratedCollaboration(), False


async def test_run_collaboration_generation_persists_ideas(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_collaboration", _stub_generate_collaboration)

    company_id = uuid.uuid4()
    collaboration_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(Collaboration(id=collaboration_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_collaboration_generation(collaboration_id, company_id, None)

    async with test_session_factory() as session:
        collaboration = await session.get(Collaboration, collaboration_id)
        ideas = (
            await session.execute(
                select(CollaborationIdea).where(CollaborationIdea.collaboration_id == collaboration_id)
            )
        ).scalars().all()

    assert collaboration.status == "complete"
    assert len(ideas) == 1
    assert ideas[0].collaborator_archetype == "Micro-influencer food bloggers"
    assert ideas[0].priority == "high"


async def test_run_collaboration_generation_includes_strategy_context(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str):
        captured_context["value"] = context
        return GeneratedCollaboration(), True

    monkeypatch.setattr(graph_module, "generate_collaboration", _capturing_generate)

    company_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    collaboration_id = uuid.uuid4()
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
        session.add(
            Collaboration(id=collaboration_id, company_id=company_id, strategy_id=strategy_id, status="pending")
        )
        await session.commit()

    await graph_module.run_collaboration_generation(collaboration_id, company_id, strategy_id)

    assert "Lead with automation." in captured_context["value"]


async def test_run_collaboration_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_collaboration", _stub_generate_collaboration_failed)

    company_id = uuid.uuid4()
    collaboration_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(Collaboration(id=collaboration_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_collaboration_generation(collaboration_id, company_id, None)

    async with test_session_factory() as session:
        collaboration = await session.get(Collaboration, collaboration_id)
        ideas = (
            await session.execute(
                select(CollaborationIdea).where(CollaborationIdea.collaboration_id == collaboration_id)
            )
        ).scalars().all()

    assert collaboration.status == "failed"
    assert collaboration.status_error is not None
    assert ideas == []


async def test_run_collaboration_generation_marks_failed_when_company_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_collaboration", _stub_generate_collaboration)

    collaboration_id = uuid.uuid4()
    missing_company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Collaboration(id=collaboration_id, company_id=missing_company_id, status="pending"))
        await session.commit()

    await graph_module.run_collaboration_generation(collaboration_id, missing_company_id, None)

    async with test_session_factory() as session:
        collaboration = await session.get(Collaboration, collaboration_id)

    assert collaboration.status == "failed"
    assert collaboration.status_error == "Company not found"
