"""MMCS Social Network - FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.trend_analyzer.graph import run_collection
from app.api.v1.router import api_router
from app.config import settings

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
    scheduler.start()
    logger.info("Trend collection scheduled every %s hour(s)", settings.TREND_COLLECTION_INTERVAL_HOURS)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Marketing Intelligence Platform with multi-agent architecture.",
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


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
