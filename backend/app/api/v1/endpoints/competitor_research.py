"""Competitor Research routes: onboard a competitor by URL (same
scrape+extract pipeline as Company Analyzer, backgrounded + polled), then
generate a Company-vs-Competitor comparison once both profiles are ready.
Also offers Claude-suggested competitor names (not live discovery).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.company_analyzer.scraper import normalize_url
from app.agents.competitor_research.comparison_graph import run_comparison_generation
from app.agents.competitor_research.graph import run_competitor_onboarding
from app.agents.competitor_research.suggestions import suggest_competitor_names
from app.db.models import Competitor
from app.db.session import get_session
from app.models.competitor import (
    CompetitorCreatedResponse,
    CompetitorCreateRequest,
    CompetitorListResponse,
    CompetitorOut,
    CompetitorSuggestionsRequest,
    CompetitorSuggestionsResponse,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import accessible_company_id_clause, ensure_company_access

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/competitors", response_model=CompetitorCreatedResponse, status_code=202)
async def create_competitor(
    payload: CompetitorCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompetitorCreatedResponse:
    """Start onboarding for a competitor URL. Returns the pending row and
    kicks off the scrape+extract pipeline in the background — the caller
    polls `GET /competitors/{id}` until status becomes 'complete' or
    'failed', same as `POST /companies`."""
    await ensure_company_access(session, payload.company_id, user)
    url = normalize_url(str(payload.url))

    existing = (
        await session.execute(
            select(Competitor).where(
                Competitor.company_id == payload.company_id, Competitor.url == url
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.status = "pending"
        existing.status_error = None
        if payload.name is not None:
            existing.name = payload.name
        await session.commit()
        background_tasks.add_task(run_competitor_onboarding, existing.id, url)
        return CompetitorCreatedResponse(
            id=existing.id, company_id=payload.company_id, url=url, status=existing.status
        )

    competitor = Competitor(
        id=uuid.uuid4(),
        company_id=payload.company_id,
        url=url,
        name=payload.name,
        status="pending",
    )
    session.add(competitor)
    await session.commit()

    background_tasks.add_task(run_competitor_onboarding, competitor.id, url)
    return CompetitorCreatedResponse(
        id=competitor.id, company_id=payload.company_id, url=url, status=competitor.status
    )


@router.get("/competitors", response_model=CompetitorListResponse)
async def list_competitors(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompetitorListResponse:
    # `company_id` is an optional *narrowing* filter, so the unfiltered call
    # would otherwise list every tenant's competitors. Membership is applied
    # either way rather than only in the filtered branch.
    visible = accessible_company_id_clause(user, Competitor.company_id)
    stmt = select(Competitor).where(visible).order_by(Competitor.created_at.desc())
    count_stmt = select(func.count()).select_from(Competitor).where(visible)
    if company_id is not None:
        stmt = stmt.where(Competitor.company_id == company_id)
        count_stmt = count_stmt.where(Competitor.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return CompetitorListResponse(
        items=[CompetitorOut.model_validate(row) for row in rows], total=total
    )


@router.get("/competitors/{competitor_id}", response_model=CompetitorOut)
async def get_competitor(
    competitor_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompetitorOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    await ensure_company_access(session, competitor.company_id, user)
    return CompetitorOut.model_validate(competitor)


@router.post("/competitors/{competitor_id}/comparison", response_model=CompetitorOut)
async def create_comparison(
    competitor_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompetitorOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    company = await ensure_company_access(session, competitor.company_id, user)

    if company.status != "complete" or competitor.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Both profiles must be ready before comparing "
                f"(company status: {company.status}, competitor status: {competitor.status})."
            ),
        )

    await run_comparison_generation(competitor_id, company.id)

    # populate_existing=True: the graph mutated this row via a *different*
    # session (async_session_factory() inside run_comparison_generation),
    # but this session still has `competitor` cached in its identity map
    # from the `session.get()` above (expire_on_commit=False) — without
    # this, a plain re-fetch would silently return the stale pre-comparison
    # object instead of hitting the DB for the real current state. Same
    # pattern as content_management's create_strategy/create_content_plan.
    refreshed = (
        await session.execute(
            select(Competitor)
            .execution_options(populate_existing=True)
            .where(Competitor.id == competitor_id)
        )
    ).scalar_one()
    return CompetitorOut.model_validate(refreshed)


@router.post("/suggestions", response_model=CompetitorSuggestionsResponse)
async def get_suggestions(
    payload: CompetitorSuggestionsRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompetitorSuggestionsResponse:
    company = await ensure_company_access(session, payload.company_id, user)

    context = "\n".join(
        [
            f"Name: {company.name or 'Unknown'}",
            f"Industry: {company.industry or 'Unknown'}",
            f"Business model: {company.business_model or 'Unknown'}",
            f"Target audience: {company.target_audience or 'Unknown'}",
            f"Summary: {company.summary or 'Unknown'}",
        ]
    )
    names, ok = await suggest_competitor_names(context)
    return CompetitorSuggestionsResponse(suggestions=names, ok=ok)
