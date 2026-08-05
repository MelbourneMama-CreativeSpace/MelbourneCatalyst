"""Dashboard summary route: a handful of honest, real aggregate numbers for
the central dashboard panel — no Claude call, pure SQL, so it works
identically regardless of ANTHROPIC_API_KEY credit."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trend_analyzer.recommendation import get_recommended_trends
from app.db.models import Company
from app.db.session import get_session
from app.models.company import CompanyOut
from app.models.dashboard import DashboardSummaryOut
from app.models.trend import TrendOut
from app.security.auth import CurrentUser, get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

_ONBOARDING_STATUSES = ("pending", "scraping", "extracting")


@router.get("/summary", response_model=DashboardSummaryOut)
async def get_dashboard_summary(
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardSummaryOut:
    company_count = (
        await session.execute(
            select(func.count()).select_from(Company).where(Company.owner_id == current_user.id)
        )
    ).scalar_one()
    companies_onboarding = (
        await session.execute(
            select(func.count())
            .select_from(Company)
            .where(Company.owner_id == current_user.id, Company.status.in_(_ONBOARDING_STATUSES))
        )
    ).scalar_one()
    recent_companies = (
        (
            await session.execute(
                select(Company)
                .where(Company.owner_id == current_user.id)
                .order_by(Company.updated_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    trending_topics = await get_recommended_trends(session, limit=5)

    return DashboardSummaryOut(
        company_count=company_count,
        companies_onboarding=companies_onboarding,
        recent_companies=[CompanyOut.model_validate(c) for c in recent_companies],
        trending_topics=[TrendOut.model_validate(t) for t in trending_topics],
    )
