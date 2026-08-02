"""The one place that answers "how relevant is this trend to this company".

`Trend.relevance_score` is a single global number per trend, scored against
whichever company happened to be most recently updated at collection time.
That was fine with one client and quietly wrong with two — it was
frequently the right score for the wrong company.
`CompanyTrendRelevance` (migration `0014`) fixed the data by scoring every
new trend against every complete company, but only the Content Planner was
ever switched over to read it; five other callers kept reading the legacy
global score.

This module holds that read, once, so all six behave identically:

**Prefer per-company scores, fall back to the legacy global score.** The
fallback is not vestigial and shouldn't be removed — a company onboarded
since the last collection run has no `CompanyTrendRelevance` rows at all,
and so does every trend collected before migration `0014`. Without it,
those companies would silently get *no* trend context rather than
imperfect trend context, which is a worse failure and a much harder one to
notice.

`company_id=None` is a legitimate caller (the dashboard's trending list
isn't scoped to a client) and goes straight to the legacy global score.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import CompanyTrendRelevance, Trend

# (trend, score) — score comes from CompanyTrendRelevance when the company
# has one, otherwise from Trend.relevance_score.
ScoredTrend = tuple[Trend, float]


async def fetch_scored_trends(
    session: AsyncSession,
    company_id: uuid.UUID | None,
    *,
    limit: int,
    min_score: float | None = None,
    max_age_days: int | None = None,
    extra_filters: tuple[ColumnElement[bool], ...] = (),
    fallback_to_global: bool = True,
) -> list[ScoredTrend]:
    """Top `limit` trends for `company_id`, most relevant first.

    Filters (`min_score`, `max_age_days`, `extra_filters`) apply identically
    to both the per-company and the legacy path, so switching between them
    can't change which trends qualify — only how they're ranked.

    `fallback_to_global=False` returns an empty list rather than falling
    back. Callers that *tell the user* the scores are company-specific must
    pass this — the Content Opportunity endpoint labels its prompt "this
    company's relevant trends", and quietly handing it globally-scored
    trends would turn an honest empty state ("no scored trends exist yet
    for this company") into a false claim.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
        if max_age_days is not None
        else None
    )

    if company_id is not None:
        stmt = (
            select(Trend, CompanyTrendRelevance.relevance_score)
            .join(CompanyTrendRelevance, CompanyTrendRelevance.trend_id == Trend.id)
            .where(CompanyTrendRelevance.company_id == company_id)
            .order_by(CompanyTrendRelevance.relevance_score.desc())
            .limit(limit)
        )
        if min_score is not None:
            stmt = stmt.where(CompanyTrendRelevance.relevance_score >= min_score)
        if cutoff is not None:
            stmt = stmt.where(Trend.discovered_at >= cutoff)
        for condition in extra_filters:
            stmt = stmt.where(condition)

        rows = (await session.execute(stmt)).all()
        if rows:
            return [(row[0], row[1]) for row in rows]
        if not fallback_to_global:
            return []
        # Falls through to the legacy path — see module docstring for why an
        # empty per-company result must not be treated as "no trends".

    legacy = (
        select(Trend)
        .where(Trend.relevance_score.is_not(None))
        .order_by(Trend.relevance_score.desc())
        .limit(limit)
    )
    if min_score is not None:
        legacy = legacy.where(Trend.relevance_score >= min_score)
    if cutoff is not None:
        legacy = legacy.where(Trend.discovered_at >= cutoff)
    for condition in extra_filters:
        legacy = legacy.where(condition)

    trends = (await session.execute(legacy)).scalars().all()
    # relevance_score is non-null by the filter above; the `or 0.0` is for
    # type-checkers, not a real case.
    return [(trend, trend.relevance_score or 0.0) for trend in trends]


async def get_recommended_trends(
    session: AsyncSession,
    limit: int | None = None,
    company_id: uuid.UUID | None = None,
) -> list[Trend]:
    """The "recommended" shortlist: relevant AND recently discovered.

    Shared by `/trend-analyzer/recommended` and the dashboard summary so
    the two can't drift. `company_id` is optional because the dashboard
    isn't scoped to one client.
    """
    scored = await fetch_scored_trends(
        session,
        company_id,
        limit=limit or settings.TREND_RECOMMENDATION_LIMIT,
        min_score=settings.TREND_RECOMMENDATION_MIN_RELEVANCE,
        max_age_days=settings.TREND_RECOMMENDATION_MAX_AGE_DAYS,
    )
    return [trend for trend, _ in scored]
