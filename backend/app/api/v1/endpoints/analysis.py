"""LoomVerse's Analysis routes — the "5 questions" overview built on real
per-post metrics (see app/agents/social_media_analyzer/analysis.py and
post_metrics.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.social_media_analyzer.analysis import build_overview, get_or_generate_insight
from app.db.session import get_session
from app.models.analysis import AnalysisOverviewOut, BreakdownRowOut, MetricTotalsOut
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import ensure_company_access

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/overview", response_model=AnalysisOverviewOut)
async def get_analysis_overview(
    company_id: uuid.UUID,
    period_days: int = 30,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> AnalysisOverviewOut:
    await ensure_company_access(session, company_id, user)

    overview = await build_overview(session, company_id, period_days=period_days)
    # Best-effort — never blocks the real numbers on a slow/failed Claude
    # call; the rest of the overview is already fully computed above
    # regardless of whether this succeeds. Memoized (see
    # get_or_generate_insight's docstring) — not a fresh Claude call on
    # every page view.
    why, recommendations = await get_or_generate_insight(session, overview)

    return AnalysisOverviewOut(
        company_id=overview.company_id,
        period_days=overview.period_days,
        posts_published=overview.posts_published,
        posts_failed=overview.posts_failed,
        current_totals=MetricTotalsOut(
            posts=overview.current_totals.posts,
            reach=overview.current_totals.reach,
            engagement=overview.current_totals.engagement,
            likes=overview.current_totals.likes,
            comments=overview.current_totals.comments,
            shares=overview.current_totals.shares,
            saves=overview.current_totals.saves,
            views=overview.current_totals.views,
        ),
        previous_totals=MetricTotalsOut(
            posts=overview.previous_totals.posts,
            reach=overview.previous_totals.reach,
            engagement=overview.previous_totals.engagement,
            likes=overview.previous_totals.likes,
            comments=overview.previous_totals.comments,
            shares=overview.previous_totals.shares,
            saves=overview.previous_totals.saves,
            views=overview.previous_totals.views,
        ),
        reach_change_pct=overview.reach_change_pct,
        engagement_change_pct=overview.engagement_change_pct,
        by_platform=[BreakdownRowOut(**vars(r)) for r in overview.by_platform],
        by_content_type=[BreakdownRowOut(**vars(r)) for r in overview.by_content_type],
        by_topic=[BreakdownRowOut(**vars(r)) for r in overview.by_topic],
        best_platform=overview.best_platform,
        worst_platform=overview.worst_platform,
        best_content_type=overview.best_content_type,
        worst_content_type=overview.worst_content_type,
        best_topic=overview.best_topic,
        worst_topic=overview.worst_topic,
        metrics_available=overview.metrics_available,
        ai_why=why,
        ai_recommendations=recommendations,
    )
