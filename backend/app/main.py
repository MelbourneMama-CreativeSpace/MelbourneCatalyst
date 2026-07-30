"""MMCS Social Network - FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.knowledge_base.reindex import run_scheduled_reindex
from app.agents.social_media_analyzer.metrics import run_scheduled_metrics_sync
from app.agents.social_media_analyzer.scheduled_publishing import run_scheduled_publishing
from app.agents.trend_analyzer.graph import run_collection
from app.agents.trend_analyzer.report_graph import run_scheduled_daily_reports
from app.api.v1.router import api_router
from app.config import settings
from app.security.auth import get_current_user

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.add_job(
        run_collection,
        trigger="interval",
        hours=settings.TREND_COLLECTION_INTERVAL_HOURS,
        id="trend_collection",
        coalesce=True,  # if a run is missed (e.g. downtime), fire once, not once per missed interval
        max_instances=1,  # never overlap with a still-running collection pass
    )
    scheduler.add_job(
        run_scheduled_reindex,
        trigger="interval",
        hours=settings.KB_REINDEX_INTERVAL_HOURS,
        id="kb_reindex",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_scheduled_daily_reports,
        trigger="interval",
        hours=settings.TREND_DAILY_REPORT_INTERVAL_HOURS,
        id="trend_daily_reports",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_scheduled_publishing,
        trigger="interval",
        minutes=settings.PUBLISH_SCHEDULER_INTERVAL_MINUTES,
        id="scheduled_publishing",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_scheduled_metrics_sync,
        trigger="interval",
        minutes=settings.METRICS_SYNC_INTERVAL_MINUTES,
        id="scheduled_metrics_sync",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Trend collection scheduled every %s hour(s)", settings.TREND_COLLECTION_INTERVAL_HOURS)
    logger.info("Knowledge base re-index scheduled every %s hour(s)", settings.KB_REINDEX_INTERVAL_HOURS)
    logger.info(
        "Daily trend report generation scheduled every %s hour(s)",
        settings.TREND_DAILY_REPORT_INTERVAL_HOURS,
    )
    logger.info(
        "Scheduled publishing check every %s minute(s)",
        settings.PUBLISH_SCHEDULER_INTERVAL_MINUTES,
    )
    logger.info(
        "Scheduled metrics sync every %s minute(s)", settings.METRICS_SYNC_INTERVAL_MINUTES
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.APP_NAME,
    description="LoomVerse AI — AI-powered marketing intelligence platform with multi-agent architecture.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - returns basic API info."""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


# Include API v1 router — gated on a valid Supabase session for every
# route in it. `/` and `/health` above stay public (uptime monitoring
# shouldn't need a session), everything under API_V1_PREFIX does not.
app.include_router(
    api_router, prefix=settings.API_V1_PREFIX, dependencies=[Depends(get_current_user)]
)
