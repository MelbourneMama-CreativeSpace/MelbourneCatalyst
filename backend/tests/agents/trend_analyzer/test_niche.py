"""Tests for niche resolution — the replacement for the per-collector
keyword lists that used to live in `.env`."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agents.trend_analyzer import niche as niche_module
from app.agents.trend_analyzer.niche import resolve_niche_keywords, to_hashtags
from app.db.models import Company


async def _seed_company(
    session_factory, *, keywords, status="complete", updated_at=None, url=None
):
    company_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            Company(
                id=company_id,
                url=url or f"https://example.com/{company_id}",
                status=status,
                niche_keywords=keywords,
                updated_at=updated_at or datetime.now(timezone.utc),
            )
        )
        await session.commit()
    return company_id


@pytest.fixture
def patched_session(monkeypatch, test_session_factory):
    monkeypatch.setattr(niche_module, "async_session_factory", test_session_factory)
    return test_session_factory


async def test_returns_empty_when_no_company_onboarded(patched_session):
    # Not an error: a fresh install has nothing to search for yet, and the
    # collectors are expected to skip rather than fail.
    assert await resolve_niche_keywords() == []


async def test_returns_empty_when_companies_have_no_keywords(patched_session):
    await _seed_company(patched_session, keywords=None)
    assert await resolve_niche_keywords() == []


async def test_ignores_companies_that_have_not_completed_onboarding(patched_session):
    await _seed_company(patched_session, keywords=["ceramics"], status="pending")
    await _seed_company(patched_session, keywords=["bookshop"], status="failed")
    assert await resolve_niche_keywords() == []


async def test_unions_keywords_across_companies(patched_session):
    await _seed_company(patched_session, keywords=["ceramics", "pottery"])
    await _seed_company(patched_session, keywords=["bookshop"])

    assert sorted(await resolve_niche_keywords()) == ["bookshop", "ceramics", "pottery"]


async def test_deduplicates_case_insensitively_keeping_first_casing(patched_session):
    now = datetime.now(timezone.utc)
    await _seed_company(patched_session, keywords=["Social Media"], updated_at=now)
    await _seed_company(
        patched_session, keywords=["social media"], updated_at=now - timedelta(hours=1)
    )

    assert await resolve_niche_keywords() == ["Social Media"]


async def test_most_recently_updated_company_wins_the_cap(patched_session):
    now = datetime.now(timezone.utc)
    await _seed_company(
        patched_session, keywords=["stale"], updated_at=now - timedelta(days=30)
    )
    await _seed_company(patched_session, keywords=["fresh"], updated_at=now)

    # With room for only one keyword, the active company's niche is the one
    # that survives — a dormant company shouldn't crowd it out.
    assert await resolve_niche_keywords(limit=1) == ["fresh"]


async def test_blank_keywords_are_dropped(patched_session):
    await _seed_company(patched_session, keywords=["  ", "", "ceramics  "])
    assert await resolve_niche_keywords() == ["ceramics"]


def test_to_hashtags_collapses_to_valid_tags():
    assert to_hashtags(["social media", "AI", "3D-printing"]) == [
        "socialmedia",
        "ai",
        "3dprinting",
    ]


def test_to_hashtags_drops_keywords_with_nothing_taggable():
    assert to_hashtags(["!!!", "ceramics"]) == ["ceramics"]


def test_to_hashtags_respects_its_own_cap():
    # Instagram's 30-unique-hashtags-per-7-days budget is why this cap is
    # separate from (and lower than) the general keyword cap.
    assert to_hashtags(["a", "b", "c"], limit=2) == ["a", "b"]
