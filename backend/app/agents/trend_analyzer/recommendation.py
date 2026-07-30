"""Shared "recommended trends" query — relevant AND recently discovered.

Extracted so `/trend-analyzer/recommended` and the dashboard summary
endpoint both read the same shortlist instead of two copies of the same
filter drifting apart.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Trend


async def get_recommended_trends(session: AsyncSession, limit: int | None = None) -> list[Trend]:
    effective_limit = limit or settings.TREND_RECOMMENDATION_LIMIT
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.TREND_RECOMMENDATION_MAX_AGE_DAYS)

    stmt = (
        select(Trend)
        .where(
            Trend.relevance_score >= settings.TREND_RECOMMENDATION_MIN_RELEVANCE,
            Trend.discovered_at >= cutoff,
        )
        .order_by(Trend.relevance_score.desc())
        .limit(effective_limit)
    )
    return list((await session.execute(stmt)).scalars().all())
