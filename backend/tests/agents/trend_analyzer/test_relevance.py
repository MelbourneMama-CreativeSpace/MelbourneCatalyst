"""The shared per-company trend relevance read (`relevance.py`).

This is the query five generation agents plus two endpoints now share, so
its two branches — per-company scores, and the legacy global fallback —
are worth testing directly rather than only through each caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.db.models import Company, CompanyTrendRelevance, Trend
from app.agents.trend_analyzer import relevance as relevance_module
from app.agents.trend_analyzer.relevance import (
    fetch_scored_trends,
    get_recommended_trends,
    score_trends_for_niche,
)


def _trend(title: str, *, global_score: float | None, age_days: int = 0) -> Trend:
    return Trend(
        id=uuid.uuid4(),
        source="rss",
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        relevance_score=global_score,
        discovered_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        raw_metadata={},
    )


@pytest_asyncio.fixture
async def seeded(db_session):
    """Two companies whose *own* rankings of the same two trends are
    deliberately the reverse of each other, and of the legacy global
    score. Any caller still reading the global score ranks these wrong."""
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    db_session.add(Company(id=company_a, url="https://a.example.com", status="complete"))
    db_session.add(Company(id=company_b, url="https://b.example.com", status="complete"))

    knitting = _trend("Knitting", global_score=0.2)
    cycling = _trend("Cycling", global_score=0.9)
    db_session.add_all([knitting, cycling])

    db_session.add_all(
        [
            CompanyTrendRelevance(company_id=company_a, trend_id=knitting.id, relevance_score=0.95),
            CompanyTrendRelevance(company_id=company_a, trend_id=cycling.id, relevance_score=0.10),
            CompanyTrendRelevance(company_id=company_b, trend_id=cycling.id, relevance_score=0.99),
            CompanyTrendRelevance(company_id=company_b, trend_id=knitting.id, relevance_score=0.05),
        ]
    )
    await db_session.commit()
    return {"a": company_a, "b": company_b}


async def test_each_company_gets_its_own_ranking(db_session, seeded):
    a = await fetch_scored_trends(db_session, seeded["a"], limit=10)
    b = await fetch_scored_trends(db_session, seeded["b"], limit=10)

    assert [t.title for t, _ in a] == ["Knitting", "Cycling"]
    assert [t.title for t, _ in b] == ["Cycling", "Knitting"]
    # The score returned is the company's own, not Trend.relevance_score —
    # callers print this number next to the ranking.
    assert a[0][1] == 0.95
    assert b[0][1] == 0.99


async def test_a_company_with_no_scores_falls_back_to_the_global_ranking(db_session, seeded):
    """A company onboarded since the last collection run has no
    CompanyTrendRelevance rows at all. Falling back beats handing the
    generation agents no trend context whatsoever."""
    newcomer = uuid.uuid4()
    db_session.add(Company(id=newcomer, url="https://c.example.com", status="complete"))
    await db_session.commit()

    rows = await fetch_scored_trends(db_session, newcomer, limit=10)
    assert [t.title for t, _ in rows] == ["Cycling", "Knitting"]
    assert rows[0][1] == 0.9  # the legacy global score


async def test_fallback_can_be_refused(db_session, seeded):
    """Callers that tell the user the scores are company-specific (the
    Content Opportunity endpoint) must get an empty list, not another
    company's ranking."""
    newcomer = uuid.uuid4()
    db_session.add(Company(id=newcomer, url="https://d.example.com", status="complete"))
    await db_session.commit()

    assert await fetch_scored_trends(
        db_session, newcomer, limit=10, fallback_to_global=False
    ) == []


async def test_no_company_uses_the_global_ranking(db_session, seeded):
    """The dashboard's trending list isn't scoped to a client."""
    rows = await fetch_scored_trends(db_session, None, limit=10)
    assert [t.title for t, _ in rows] == ["Cycling", "Knitting"]


async def test_min_score_applies_on_the_per_company_path(db_session, seeded):
    rows = await fetch_scored_trends(db_session, seeded["a"], limit=10, min_score=0.5)
    assert [t.title for t, _ in rows] == ["Knitting"]

    # Same threshold, other company — the opposite trend survives, which
    # couldn't happen if this were still reading the global score.
    rows_b = await fetch_scored_trends(db_session, seeded["b"], limit=10, min_score=0.5)
    assert [t.title for t, _ in rows_b] == ["Cycling"]


async def test_max_age_days_applies_on_both_paths(db_session):
    company = uuid.uuid4()
    db_session.add(Company(id=company, url="https://e.example.com", status="complete"))
    fresh = _trend("Fresh", global_score=0.8, age_days=1)
    stale = _trend("Stale", global_score=0.9, age_days=60)
    db_session.add_all([fresh, stale])
    db_session.add(
        CompanyTrendRelevance(company_id=company, trend_id=stale.id, relevance_score=0.99)
    )
    await db_session.commit()

    # Per-company path: the company's only scored trend is too old, so the
    # window excludes it and the legacy fallback takes over.
    scoped = await fetch_scored_trends(db_session, company, limit=10, max_age_days=7)
    assert [t.title for t, _ in scoped] == ["Fresh"]

    # Global path, same window.
    unscoped = await fetch_scored_trends(db_session, None, limit=10, max_age_days=7)
    assert [t.title for t, _ in unscoped] == ["Fresh"]


async def test_limit_is_respected(db_session, seeded):
    assert len(await fetch_scored_trends(db_session, seeded["a"], limit=1)) == 1
    assert len(await fetch_scored_trends(db_session, None, limit=1)) == 1


async def test_recommended_shortlist_is_company_aware(db_session, seeded):
    """`/recommended` and the dashboard both go through this."""
    a = await get_recommended_trends(db_session, 10, seeded["a"])
    b = await get_recommended_trends(db_session, 10, seeded["b"])

    assert a[0].title == "Knitting"
    assert b[0].title == "Cycling"


async def test_trends_with_no_score_at_all_are_excluded_from_the_global_path(db_session):
    company = uuid.uuid4()
    db_session.add(Company(id=company, url="https://f.example.com", status="complete"))
    db_session.add(_trend("Unscored", global_score=None))
    db_session.add(_trend("Scored", global_score=0.5))
    await db_session.commit()

    rows = await fetch_scored_trends(db_session, company, limit=10)
    assert [t.title for t, _ in rows] == ["Scored"]


# --- score_trends_for_niche: on-demand, no company required ---------------


async def test_score_trends_for_niche_ranks_by_similarity_to_free_text(monkeypatch, db_session):
    """A handle's niche described as free text (e.g. from
    analyze_social_profile, with no company onboarded for it) still gets
    a real, differentiated ranking — not just whatever order trends
    happen to be in."""

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        # niche text and "Cycling gear" both embed to [1, 0] (exact
        # match); "Knitting patterns" embeds to [0, 1] (orthogonal, no
        # match at all).
        vectors = {"an indie cycling gear brand": [1.0, 0.0], "Cycling gear": [1.0, 0.0]}
        return [vectors.get(t, [0.0, 1.0]) for t in texts]

    monkeypatch.setattr(relevance_module, "embed_documents", _fake_embed)
    db_session.add_all(
        [_trend("Cycling gear", global_score=None), _trend("Knitting patterns", global_score=None)]
    )
    await db_session.commit()

    scored = await score_trends_for_niche(db_session, "an indie cycling gear brand")

    assert [t.title for t, _ in scored] == ["Cycling gear", "Knitting patterns"]
    assert scored[0][1] == 1.0  # cosine 1.0 -> normalized (1+1)/2
    assert scored[1][1] == 0.5  # cosine 0.0 (orthogonal) -> normalized 0.5


async def test_score_trends_for_niche_excludes_trends_older_than_the_window(
    monkeypatch, db_session
):
    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(relevance_module, "embed_documents", _fake_embed)
    db_session.add_all(
        [
            _trend("Fresh", global_score=None, age_days=1),
            _trend("Stale", global_score=None, age_days=30),
        ]
    )
    await db_session.commit()

    scored = await score_trends_for_niche(db_session, "anything", max_age_days=14)

    assert [t.title for t, _ in scored] == ["Fresh"]


async def test_score_trends_for_niche_returns_empty_without_any_trends(db_session):
    assert await score_trends_for_niche(db_session, "a brand new niche") == []


async def test_score_trends_for_niche_returns_empty_on_embedding_failure(monkeypatch, db_session):
    async def _failed_embed(texts: list[str]) -> list[None]:
        return [None for _ in texts]

    monkeypatch.setattr(relevance_module, "embed_documents", _failed_embed)
    db_session.add(_trend("Some trend", global_score=None))
    await db_session.commit()

    assert await score_trends_for_niche(db_session, "a niche") == []


async def test_score_trends_for_niche_respects_limit(monkeypatch, db_session):
    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(relevance_module, "embed_documents", _fake_embed)
    db_session.add_all([_trend(f"Trend {i}", global_score=None) for i in range(5)])
    await db_session.commit()

    scored = await score_trends_for_niche(db_session, "anything", limit=2)

    assert len(scored) == 2
