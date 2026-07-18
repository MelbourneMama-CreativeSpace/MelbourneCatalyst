"""Trend Analyzer routes: list/filter discovered trends, inspect per-source
collection status, and trigger a manual collection run.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trend_analyzer.graph import get_last_run_summary, run_collection
from app.db.models import Trend
from app.db.session import get_session
from app.models.trend import (
    CollectionRunResult,
    CollectionSourceResult,
    SourceStatusOut,
    TrendListResponse,
    TrendOut,
)

router = APIRouter()


@router.get("/", response_model=TrendListResponse)
async def list_trends(
    source: str | None = None,
    category: str | None = None,
    since: datetime | None = None,
    min_relevance: float | None = Query(default=None, ge=0.0, le=1.0),
    ids: list[uuid.UUID] | None = Query(
        default=None, description="Look up specific trends by id (repeatable query param)"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> TrendListResponse:
    filters = []
    if ids:
        filters.append(Trend.id.in_(ids))
    if source:
        filters.append(Trend.source == source)
    if category:
        filters.append(Trend.category == category)
    if since:
        filters.append(Trend.discovered_at >= since)
    if min_relevance is not None:
        filters.append(Trend.relevance_score >= min_relevance)

    count_stmt = select(func.count()).select_from(Trend)
    list_stmt = select(Trend).order_by(Trend.discovered_at.desc()).limit(limit).offset(offset)
    for condition in filters:
        count_stmt = count_stmt.where(condition)
        list_stmt = list_stmt.where(condition)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(list_stmt)).scalars().all()

    return TrendListResponse(
        items=[TrendOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sources", response_model=list[SourceStatusOut])
async def source_status(session: AsyncSession = Depends(get_session)) -> list[SourceStatusOut]:
    last_run = get_last_run_summary()

    stmt = select(
        Trend.source,
        func.count().label("total_stored"),
        func.max(Trend.discovered_at).label("last_discovered_at"),
    ).group_by(Trend.source)
    stored_by_source = {row.source: row for row in (await session.execute(stmt)).all()}

    statuses = []
    for source in sorted(set(stored_by_source) | set(last_run)):
        stored = stored_by_source.get(source)
        run = last_run.get(source)
        statuses.append(
            SourceStatusOut(
                source=source,
                total_stored=stored.total_stored if stored else 0,
                last_discovered_at=stored.last_discovered_at if stored else None,
                last_run_at=run.ran_at if run else None,
                last_run_collected_count=run.item_count if run else None,
                last_run_new_items=run.new_item_count if run else None,
                last_run_error=run.error if run else None,
            )
        )
    return statuses


@router.get("/{trend_id}", response_model=TrendOut)
async def get_trend(trend_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> TrendOut:
    trend = await session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    return TrendOut.model_validate(trend)


@router.post("/collect", response_model=CollectionRunResult)
async def trigger_collection() -> CollectionRunResult:
    result = await run_collection()
    return CollectionRunResult(
        new_item_count=result.new_item_count,
        source_results=[
            CollectionSourceResult(
                source=source_result.source.value,
                collected_count=source_result.item_count,
                new_item_count=source_result.new_item_count,
                error=source_result.error,
                ran_at=source_result.ran_at,
            )
            for source_result in result.source_results
        ],
    )
