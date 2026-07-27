"""Trend Analyzer routes: list/filter discovered trends, inspect per-source
collection status, and trigger a manual collection run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trend_analyzer.graph import get_last_run_summary, run_collection
from app.agents.trend_analyzer.report_graph import run_trend_report_generation
from app.config import settings
from app.db.models import Company, Trend, TrendReport
from app.db.session import get_session
from app.models.trend import (
    CollectionRunResult,
    CollectionSourceResult,
    SourceStatusOut,
    TrendListResponse,
    TrendOut,
    TrendReportCreateRequest,
    TrendReportListResponse,
    TrendReportOut,
)

router = APIRouter()


async def _get_ready_company_or_error(session: AsyncSession, company_id: uuid.UUID) -> Company:
    """Same guard as content_management.py's — a report generated from a
    company that hasn't finished onboarding wastes a Claude call on a
    context that's mostly 'Unknown'."""
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if company.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Company profile is not ready (status: {company.status}). "
                "Onboarding must complete successfully before generating a report."
            ),
        )
    return company


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


# NOTE: these /reports and /recommended routes must stay registered
# before GET /{trend_id} below — that catch-all matches any single path
# segment, so a GET /reports or /recommended request would otherwise be
# captured by it first (and fail UUID validation on trend_id="reports"
# or "recommended") if either came later.


@router.post("/reports", response_model=TrendReportOut)
async def create_trend_report(
    payload: TrendReportCreateRequest, session: AsyncSession = Depends(get_session)
) -> TrendReportOut:
    await _get_ready_company_or_error(session, payload.company_id)
    period_days = payload.period_days or settings.TREND_REPORT_DEFAULT_PERIOD_DAYS

    report = TrendReport(
        id=uuid.uuid4(), company_id=payload.company_id, status="pending", period_days=period_days
    )
    session.add(report)
    await session.commit()

    await run_trend_report_generation(report.id, payload.company_id, period_days)

    # populate_existing=True — same identity-map staleness reason as
    # content_management.py's create_strategy.
    refreshed = (
        await session.execute(
            select(TrendReport)
            .execution_options(populate_existing=True)
            .where(TrendReport.id == report.id)
        )
    ).scalar_one()
    return TrendReportOut.model_validate(refreshed)


@router.get("/reports", response_model=TrendReportListResponse)
async def list_trend_reports(
    company_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_session)
) -> TrendReportListResponse:
    stmt = select(TrendReport).order_by(TrendReport.created_at.desc())
    count_stmt = select(func.count()).select_from(TrendReport)
    if company_id is not None:
        stmt = stmt.where(TrendReport.company_id == company_id)
        count_stmt = count_stmt.where(TrendReport.company_id == company_id)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return TrendReportListResponse(
        items=[TrendReportOut.model_validate(row) for row in rows], total=total
    )


@router.get("/reports/{report_id}", response_model=TrendReportOut)
async def get_trend_report(
    report_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> TrendReportOut:
    report = await session.get(TrendReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Trend report not found")
    return TrendReportOut.model_validate(report)


@router.get("/recommended", response_model=TrendListResponse)
async def list_recommended_trends(
    limit: int | None = Query(default=None, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> TrendListResponse:
    """Formalizes the dashboard's manual `min_relevance` filter into an
    opinionated shortlist: highly relevant AND recently discovered, so a
    trend that was relevant six months ago but has since gone stale
    doesn't linger at the top. No Claude call — pure filter + sort over
    already-scored trends, same `relevance_score` the collection graph
    computes."""
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
    rows = (await session.execute(stmt)).scalars().all()

    return TrendListResponse(
        items=[TrendOut.model_validate(row) for row in rows],
        total=len(rows),
        limit=effective_limit,
        offset=0,
    )


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
