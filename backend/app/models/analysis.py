"""Pydantic response schemas for LoomVerse's Analysis layer."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class MetricTotalsOut(BaseModel):
    posts: int
    reach: int | None
    engagement: int
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    views: int | None


class BreakdownRowOut(BaseModel):
    key: str
    posts: int
    total_engagement: int
    avg_engagement: float


class AnalysisOverviewOut(BaseModel):
    company_id: uuid.UUID
    period_days: int
    posts_published: int
    posts_failed: int
    current_totals: MetricTotalsOut
    previous_totals: MetricTotalsOut
    reach_change_pct: float | None
    engagement_change_pct: float | None
    by_platform: list[BreakdownRowOut]
    by_content_type: list[BreakdownRowOut]
    by_topic: list[BreakdownRowOut]
    best_platform: str | None
    worst_platform: str | None
    best_content_type: str | None
    worst_content_type: str | None
    best_topic: str | None
    worst_topic: str | None
    # False when no platform has produced a single real metrics snapshot
    # yet (e.g. right after connecting, before the sync job has run) —
    # the UI needs to show an honest "still gathering data" state, not a
    # dashboard full of zeros that look like real bad performance.
    metrics_available: bool
    ai_why: str | None
    ai_recommendations: list[str]
