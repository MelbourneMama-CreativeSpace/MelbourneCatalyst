"""Internal data shapes passed between collectors, the graph, and the DB layer.

These are plain dataclasses (not Pydantic) since they never cross the API boundary —
`app/models/trend.py` holds the Pydantic response schemas used there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TrendSource(StrEnum):
    GOOGLE_TRENDS = "google_trends"
    REDDIT = "reddit"
    RSS = "rss"
    YOUTUBE = "youtube"


@dataclass(slots=True)
class RawTrendItem:
    """A trend item as collected from a source, before dedupe/enrichment."""

    source: TrendSource
    title: str
    url: str
    description: str | None = None
    score: float | None = None
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EnrichedTrendItem:
    """A `RawTrendItem` plus Claude-generated category/insight, ready to persist."""

    item: RawTrendItem
    category: str
    insight: str


@dataclass(slots=True)
class SourceResult:
    """Per-source outcome of a single collection run, for the /sources status endpoint."""

    source: TrendSource
    item_count: int = 0
    error: str | None = None
    ran_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class RunResult:
    """Outcome of one full graph invocation, returned by `graph.run_collection()`."""

    new_item_count: int
    source_results: list[SourceResult]
