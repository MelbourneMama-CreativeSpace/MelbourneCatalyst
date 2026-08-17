"""LoomVerse's Analysis layer — aggregates real per-post metrics
(post_metrics.py's data) into the "5 questions" a person actually wants
answered: How are we doing? What worked? What didn't? Why? What next?

Deliberately not a 26-dimension analytics engine (yet) — this is the
foundation those dimensions eventually sit on top of. Every number here
is real, computed from `PostMetricSnapshot` rows a real platform actually
returned; nothing is fabricated to fill a gap (a platform with no real
metric for something — LinkedIn's comments/shares/impressions, currently
— just contributes `None`, not a guessed value).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AnalysisInsightCache, ContentItem, ContentPlan, PostMetricSnapshot

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"

# A simple, equal-weighted sum for Phase 1 — the user's own spec calls
# out per-platform/per-objective weighting (likes = low intent, saves =
# high interest, etc.) as its own later dimension ("Engagement Quality"),
# not something to guess weights for without real usage data to validate
# them against yet.
def _engagement(snapshot: PostMetricSnapshot | None) -> int:
    if snapshot is None:
        return 0
    return sum(v for v in (snapshot.likes, snapshot.comments, snapshot.shares, snapshot.saves) if v)


@dataclass
class MetricTotals:
    posts: int = 0
    reach: int | None = None
    engagement: int = 0
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    views: int | None = None

    def add(self, snapshot: PostMetricSnapshot | None) -> None:
        self.posts += 1
        if snapshot is None:
            return
        self.engagement += _engagement(snapshot)
        for field_name in ("reach", "likes", "comments", "shares", "saves", "views"):
            value = getattr(snapshot, field_name)
            if value is None:
                continue
            current = getattr(self, field_name)
            setattr(self, field_name, (current or 0) + value)


@dataclass
class BreakdownRow:
    key: str
    posts: int
    total_engagement: int
    avg_engagement: float


@dataclass
class AnalysisOverview:
    company_id: uuid.UUID
    period_days: int
    posts_published: int
    posts_failed: int
    current_totals: MetricTotals
    previous_totals: MetricTotals
    reach_change_pct: float | None
    engagement_change_pct: float | None
    by_platform: list[BreakdownRow] = field(default_factory=list)
    by_content_type: list[BreakdownRow] = field(default_factory=list)
    by_topic: list[BreakdownRow] = field(default_factory=list)
    best_platform: str | None = None
    worst_platform: str | None = None
    best_content_type: str | None = None
    worst_content_type: str | None = None
    best_topic: str | None = None
    worst_topic: str | None = None
    metrics_available: bool = False
    ai_summary: str | None = None


def _pct_change(current: int | None, previous: int | None) -> float | None:
    if not previous:
        return None
    current = current or 0
    return round(((current - previous) / previous) * 100, 1)


def _rank(rows: list[BreakdownRow]) -> tuple[str | None, str | None]:
    """(best, worst) by average engagement — only among groups with at
    least one post that actually has real metrics, otherwise "best"/
    "worst" would just be an artifact of which post happened to sync
    first."""
    scored = [r for r in rows if r.total_engagement > 0]
    if not scored:
        return None, None
    best = max(scored, key=lambda r: r.avg_engagement)
    worst = min(scored, key=lambda r: r.avg_engagement)
    if best.key == worst.key:
        return best.key, None
    return best.key, worst.key


def _breakdown(items: list[tuple[ContentItem, PostMetricSnapshot | None]], attr: str) -> list[BreakdownRow]:
    groups: dict[str, list[int]] = defaultdict(list)
    for item, snapshot in items:
        key = getattr(item, attr) or "uncategorized"
        groups[key].append(_engagement(snapshot))
    rows = [
        BreakdownRow(
            key=key,
            posts=len(engagements),
            total_engagement=sum(engagements),
            avg_engagement=round(sum(engagements) / len(engagements), 1) if engagements else 0.0,
        )
        for key, engagements in groups.items()
    ]
    rows.sort(key=lambda r: r.total_engagement, reverse=True)
    return rows


async def _latest_snapshot_by_item(
    session: AsyncSession, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PostMetricSnapshot]:
    """The most recent snapshot per item — snapshots accumulate one row
    per sync run, so this is genuinely "current," not a sum across every
    historical fetch (which would just double-count)."""
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            select(PostMetricSnapshot)
            .where(PostMetricSnapshot.content_item_id.in_(item_ids))
            .order_by(PostMetricSnapshot.captured_at.desc())
        )
    ).scalars().all()
    latest: dict[uuid.UUID, PostMetricSnapshot] = {}
    for row in rows:
        if row.content_item_id not in latest:
            latest[row.content_item_id] = row
    return latest


async def build_overview(
    session: AsyncSession, company_id: uuid.UUID, *, period_days: int = 30
) -> AnalysisOverview:
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=period_days)
    previous_start = period_start - timedelta(days=period_days)

    all_items = (
        (
            await session.execute(
                select(ContentItem)
                .join(ContentPlan, ContentItem.content_plan_id == ContentPlan.id)
                .where(ContentPlan.company_id == company_id)
            )
        )
        .scalars()
        .all()
    )

    # SQLite (used in tests) hands back naive datetimes for a
    # DateTime(timezone=True) column even though Postgres (production)
    # returns real tz-aware ones — normalize before comparing against the
    # tz-aware period boundaries below, same fix as knowledge_base.py's
    # staleness check.
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    published = [i for i in all_items if i.published_at is not None]
    current_items = [i for i in published if _aware(i.published_at) >= period_start]
    previous_items = [
        i for i in published if previous_start <= _aware(i.published_at) < period_start
    ]

    snapshots_by_item = await _latest_snapshot_by_item(
        session, [i.id for i in current_items + previous_items]
    )
    metrics_available = any(snapshots_by_item.values())

    current_totals = MetricTotals()
    current_pairs: list[tuple[ContentItem, PostMetricSnapshot | None]] = []
    for item in current_items:
        snapshot = snapshots_by_item.get(item.id)
        current_totals.add(snapshot)
        current_pairs.append((item, snapshot))

    previous_totals = MetricTotals()
    for item in previous_items:
        previous_totals.add(snapshots_by_item.get(item.id))

    by_platform = _breakdown(current_pairs, "platform")
    by_content_type = _breakdown(current_pairs, "content_type")
    by_topic = _breakdown(current_pairs, "theme")

    best_platform, worst_platform = _rank(by_platform)
    best_content_type, worst_content_type = _rank(by_content_type)
    best_topic, worst_topic = _rank(by_topic)

    posts_failed = len(
        [i for i in all_items if i.published_at is None and i.approval_status == "rejected"]
    )

    return AnalysisOverview(
        company_id=company_id,
        period_days=period_days,
        posts_published=len(current_items),
        posts_failed=posts_failed,
        current_totals=current_totals,
        previous_totals=previous_totals,
        reach_change_pct=_pct_change(current_totals.reach, previous_totals.reach),
        engagement_change_pct=_pct_change(current_totals.engagement, previous_totals.engagement),
        by_platform=by_platform,
        by_content_type=by_content_type,
        by_topic=by_topic,
        best_platform=best_platform,
        worst_platform=worst_platform,
        best_content_type=best_content_type,
        worst_content_type=worst_content_type,
        best_topic=best_topic,
        worst_topic=worst_topic,
        metrics_available=metrics_available,
    )


_INSIGHT_TOOL = {
    "name": "explain_performance",
    "description": "Explain why content performed the way it did and recommend concrete next steps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "why": {
                "type": "string",
                "description": "1-3 sentences explaining the pattern in the real numbers given — grounded only in those numbers, never invented.",
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 short, concrete, actionable next steps directly justified by the numbers given.",
            },
        },
        "required": ["why", "recommendations"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _build_insight_prompt(overview: AnalysisOverview) -> str:
    lines = [
        f"Period: last {overview.period_days} days, {overview.posts_published} posts published "
        f"(previous period: {overview.previous_totals.posts}).",
        f"Reach: {overview.current_totals.reach} ({overview.reach_change_pct}% vs previous period).",
        f"Engagement: {overview.current_totals.engagement} ({overview.engagement_change_pct}% vs previous period).",
    ]
    if overview.by_platform:
        lines.append(
            "By platform: "
            + ", ".join(f"{r.key} (avg engagement {r.avg_engagement}, {r.posts} posts)" for r in overview.by_platform)
        )
    if overview.by_content_type:
        lines.append(
            "By content type: "
            + ", ".join(f"{r.key} (avg engagement {r.avg_engagement}, {r.posts} posts)" for r in overview.by_content_type)
        )
    if overview.by_topic:
        lines.append(
            "By topic: "
            + ", ".join(f"{r.key} (avg engagement {r.avg_engagement}, {r.posts} posts)" for r in overview.by_topic)
        )
    return (
        "Here is this company's real social media performance data for the period below. "
        "Explain what's driving the pattern and recommend concrete next steps. "
        "Only reason from the numbers given — never invent a number, platform, or topic "
        "not listed here.\n\n" + "\n".join(lines)
    )


async def generate_insight(overview: AnalysisOverview) -> tuple[str | None, list[str]]:
    """Best-effort AI "why" + "what's next" over the real aggregated
    numbers — never raises, returns (None, []) on any failure or missing
    key so the rest of the overview still renders without it."""
    if not settings.ANTHROPIC_API_KEY:
        return None, []
    if overview.posts_published == 0:
        return None, []
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1024,
            tools=[_INSIGHT_TOOL],
            tool_choice={"type": "tool", "name": "explain_performance"},
            messages=[{"role": "user", "content": _build_insight_prompt(overview)}],
        )
        if response.stop_reason == "max_tokens":
            logger.warning("Analysis insight generation truncated at max_tokens")
            return None, []
        tool_use = next(block for block in response.content if block.type == "tool_use")
        return tool_use.input.get("why"), list(tool_use.input.get("recommendations") or [])
    except Exception:
        logger.exception("Analysis insight generation failed")
        return None, []


def _insight_cache_ttl() -> timedelta:
    # Matches the post-metrics sync cadence — there's no point treating an
    # insight as stale faster than the underlying numbers can actually
    # change, and no point caching it longer than that either.
    return timedelta(minutes=settings.POST_METRICS_SYNC_INTERVAL_MINUTES)


async def get_or_generate_insight(
    session: AsyncSession, overview: AnalysisOverview
) -> tuple[str | None, list[str]]:
    """Same contract as generate_insight, but memoized per (company,
    period_days) — GET /analysis/overview used to call Claude fresh on
    every single page view, which is a real Claude call for zero new
    information the overwhelming majority of the time, since the
    underlying totals only change on the metrics sync cadence, not on
    every refresh."""
    existing = (
        await session.execute(
            select(AnalysisInsightCache).where(
                AnalysisInsightCache.company_id == overview.company_id,
                AnalysisInsightCache.period_days == overview.period_days,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is not None:
        generated_at = existing.generated_at
        # SQLite (tests) hands back a naive datetime for a
        # DateTime(timezone=True) column; Postgres (production) doesn't —
        # same normalization as build_overview's period-window comparison
        # above.
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        if now - generated_at < _insight_cache_ttl():
            return existing.ai_why, list(existing.ai_recommendations)

    why, recommendations = await generate_insight(overview)

    if existing is not None:
        existing.ai_why = why
        existing.ai_recommendations = recommendations
        existing.generated_at = now
    else:
        session.add(
            AnalysisInsightCache(
                company_id=overview.company_id,
                period_days=overview.period_days,
                ai_why=why,
                ai_recommendations=recommendations,
                generated_at=now,
            )
        )
    await session.commit()

    return why, recommendations
