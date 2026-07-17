"""Pydantic response schemas for the Trend Analyzer API (the API boundary —
internal collector/graph shapes live in `app.agents.trend_analyzer.schemas`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    title: str
    description: str | None
    url: str
    score: float | None
    category: str | None
    insight: str | None
    discovered_at: datetime
    created_at: datetime


class TrendListResponse(BaseModel):
    items: list[TrendOut]
    total: int
    limit: int
    offset: int


class SourceStatusOut(BaseModel):
    """Aggregate status for GET /sources — persisted totals plus the most recent run's outcome."""

    source: str
    total_stored: int
    last_discovered_at: datetime | None
    last_run_at: datetime | None
    last_run_collected_count: int | None
    last_run_new_items: int | None
    last_run_error: str | None


class CollectionSourceResult(BaseModel):
    """Outcome for one source from a single POST /collect invocation.

    `collected_count` is what the collector fetched; `new_item_count` is how
    many of those were genuinely new (not already in the DB) — a source can
    legitimately collect 10 and persist 0 on a re-run.
    """

    source: str
    collected_count: int
    new_item_count: int
    error: str | None
    ran_at: datetime


class CollectionRunResult(BaseModel):
    new_item_count: int
    source_results: list[CollectionSourceResult]
