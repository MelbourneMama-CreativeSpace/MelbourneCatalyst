"""Content Management routes: generate a Strategy from a company's profile
+ relevant trends, then generate a ContentPlan (calendar) from that.

Both POST endpoints run their LangGraph pipeline synchronously (awaited
inline, not via BackgroundTasks) — a single Claude tool-use call is fast
enough that a plain POST-and-wait is simpler than the fire-and-forget +
poll pattern company onboarding needs for its ~30s scrape+embed pipeline.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.content_management.content_plan_graph import run_content_plan_generation
from app.agents.content_management.strategy_graph import run_strategy_generation
from app.db.models import Company, ContentPlan, Strategy
from app.db.session import get_session
from app.models.content_management import (
    ContentPlanCreateRequest,
    ContentPlanListResponse,
    ContentPlanOut,
    ContentPlanSummaryOut,
    StrategyCreateRequest,
    StrategyListResponse,
    StrategyOut,
)

router = APIRouter()


async def _get_company_or_404(session: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("/strategies", response_model=StrategyOut)
async def create_strategy(
    payload: StrategyCreateRequest, session: AsyncSession = Depends(get_session)
) -> StrategyOut:
    await _get_company_or_404(session, payload.company_id)

    strategy = Strategy(id=uuid.uuid4(), company_id=payload.company_id, status="pending")
    session.add(strategy)
    await session.commit()

    await run_strategy_generation(strategy.id, payload.company_id)

    # populate_existing=True: the graph mutated this row via a *different*
    # session (async_session_factory() inside run_strategy_generation), but
    # this session still has `strategy` cached in its identity map from the
    # insert above (expire_on_commit=False) — without this, a plain re-fetch
    # would silently return the stale pre-generation object instead of
    # hitting the DB for the real current state.
    refreshed = (
        await session.execute(
            select(Strategy)
            .execution_options(populate_existing=True)
            .where(Strategy.id == strategy.id)
        )
    ).scalar_one()
    return StrategyOut.model_validate(refreshed)


@router.get("/strategies", response_model=StrategyListResponse)
async def list_strategies(
    company_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_session)
) -> StrategyListResponse:
    stmt = select(Strategy).order_by(Strategy.created_at.desc())
    count_stmt = select(func.count()).select_from(Strategy)
    if company_id is not None:
        stmt = stmt.where(Strategy.company_id == company_id)
        count_stmt = count_stmt.where(Strategy.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return StrategyListResponse(items=[StrategyOut.model_validate(row) for row in rows], total=total)


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
async def get_strategy(
    strategy_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> StrategyOut:
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return StrategyOut.model_validate(strategy)


@router.post("/content-plans", response_model=ContentPlanOut)
async def create_content_plan(
    payload: ContentPlanCreateRequest, session: AsyncSession = Depends(get_session)
) -> ContentPlanOut:
    await _get_company_or_404(session, payload.company_id)
    if payload.strategy_id is not None:
        strategy = await session.get(Strategy, payload.strategy_id)
        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")

    content_plan = ContentPlan(
        id=uuid.uuid4(),
        company_id=payload.company_id,
        strategy_id=payload.strategy_id,
        status="pending",
    )
    session.add(content_plan)
    await session.commit()

    await run_content_plan_generation(content_plan.id, payload.company_id, payload.strategy_id)

    # populate_existing=True — same identity-map staleness reason as
    # create_strategy above: this session's cached `content_plan` still
    # shows status="pending" from before the graph ran it under a
    # different session.
    refreshed = (
        await session.execute(
            select(ContentPlan)
            .options(selectinload(ContentPlan.items))
            .execution_options(populate_existing=True)
            .where(ContentPlan.id == content_plan.id)
        )
    ).scalar_one()
    return ContentPlanOut.model_validate(refreshed)


@router.get("/content-plans", response_model=ContentPlanListResponse)
async def list_content_plans(
    company_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_session)
) -> ContentPlanListResponse:
    stmt = select(ContentPlan).order_by(ContentPlan.created_at.desc())
    count_stmt = select(func.count()).select_from(ContentPlan)
    if company_id is not None:
        stmt = stmt.where(ContentPlan.company_id == company_id)
        count_stmt = count_stmt.where(ContentPlan.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return ContentPlanListResponse(
        items=[ContentPlanSummaryOut.model_validate(row) for row in rows], total=total
    )


@router.get("/content-plans/{content_plan_id}", response_model=ContentPlanOut)
async def get_content_plan(
    content_plan_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ContentPlanOut:
    content_plan = (
        await session.execute(
            select(ContentPlan)
            .options(selectinload(ContentPlan.items))
            .where(ContentPlan.id == content_plan_id)
        )
    ).scalar_one_or_none()
    if content_plan is None:
        raise HTTPException(status_code=404, detail="Content plan not found")
    return ContentPlanOut.model_validate(content_plan)
