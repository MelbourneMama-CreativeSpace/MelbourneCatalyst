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
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


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
    """A `RawTrendItem` plus Claude-generated category/insight, ready to persist.

    `relevance_score` is filled in later by the graph's `score_relevance`
    node (against the current company's niche keywords). Stays None when no
    company has been onboarded, or when the KB embedding call failed.
    """

    item: RawTrendItem
    category: str
    insight: str
    relevance_score: float | None = None


@dataclass(slots=True)
class SourceResult:
    """Per-source outcome of a single collection run, for the /sources status endpoint.

    `item_count` is set by the collector node — how many raw items this
    source returned. `new_item_count` is filled in later by
    `merge_and_dedupe` — of those, how many were genuinely new (not already
    in the DB). Keep both: a source can legitimately collect 10 and persist
    0 on a re-run, and collapsing that into one field hides it.
    """

    source: TrendSource
    item_count: int = 0
    new_item_count: int = 0
    error: str | None = None
    ran_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class RunResult:
    """Outcome of one full graph invocation, returned by `graph.run_collection()`."""

    new_item_count: int
    source_results: list[SourceResult]


@dataclass(slots=True)
class GeneratedTrendReport:
    """Claude's structured output for `generate_trend_report`."""

    summary: str | None = None
    key_themes: list[str] = field(default_factory=list)
    notable_trends_summary: str | None = None
    content_opportunities: str | None = None
    campaign_alignment_notes: str | None = None
    competitor_relevance_notes: str | None = None
