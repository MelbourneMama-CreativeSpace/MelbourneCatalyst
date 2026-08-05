"""Tests for the chat agent's read-only tools — direct DB-backed checks,
independent of the tool-use loop itself (covered in test_agent.py)."""

from __future__ import annotations

import uuid

from app.agents.chat import tools
from app.db.models import Company
from app.security.auth import CurrentUser

_CURRENT_USER = CurrentUser(id="test-user-id", email="test@example.com")


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id,
        url=f"https://example.com/{company_id}",
        status="complete",
        name="Acme",
        industry="Software",
        owner_id="test-user-id",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def test_get_company_summary_returns_profile(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)

    result = await tools.get_company_summary(
        db_session, _CURRENT_USER, company_id=str(company_id)
    )

    assert "Acme" in result
    assert "Software" in result


async def test_get_company_summary_handles_invalid_uuid(db_session):
    result = await tools.get_company_summary(db_session, _CURRENT_USER, company_id="not-a-uuid")
    assert "isn't a valid company id" in result


async def test_get_company_summary_handles_missing_company(db_session):
    result = await tools.get_company_summary(
        db_session, _CURRENT_USER, company_id=str(uuid.uuid4())
    )
    assert "No company found" in result


async def test_get_company_summary_handles_incomplete_onboarding(test_session_factory):
    company_id = await _seed_company(test_session_factory, status="pending", name=None)
    async with test_session_factory() as session:
        result = await tools.get_company_summary(
            session, _CURRENT_USER, company_id=str(company_id)
        )
    assert "onboarding not finished" in result


async def test_get_content_pipeline_status_counts_rows(test_session_factory, db_session):
    company_id = await _seed_company(test_session_factory)

    result = await tools.get_content_pipeline_status(
        db_session, _CURRENT_USER, company_id=str(company_id)
    )

    assert "0 strategies" in result
    assert "0 content plans" in result
    assert "0 campaigns" in result


async def test_list_trending_topics_handles_empty_state(db_session):
    result, cards = await tools.list_trending_topics(db_session, _CURRENT_USER)
    assert "No trending topics" in result
    assert cards == []
