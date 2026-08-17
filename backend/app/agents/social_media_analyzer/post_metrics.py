"""Real per-post engagement metrics via Composio — the data-layer
foundation LoomVerse's Analysis needs to answer "what worked" at the
individual-post level.

Every platform's real capability was checked live against Composio's
actual toolkit/schema before writing any of this (`client.tools.list` /
`client.tools.retrieve`), not assumed uniform:

- Facebook: the Insights API itself is largely dead for post-level
  metrics — Meta deprecated `post_impressions`, `post_engagements`,
  `post_reactions_by_type_total`, and friends as of November 2025,
  leaving only `post_media_view`. The real path is the post *object*
  itself (`FACEBOOK_GET_POST` with `likes.summary(true),
  comments.summary(true), shares, reactions.summary(true)` as fields),
  which still returns real counts directly.
- Instagram: `INSTAGRAM_GET_POST_INSIGHTS` genuinely works and returns
  reach/likes/comments/saved/shares (+ views for video), confirmed
  against its real output schema — a list of `{name, values: [{value}]}`
  objects, the standard Graph API Insights shape.
- LinkedIn: genuinely limited. No comment, share, or impression metric
  exists anywhere in Composio's current LinkedIn toolkit for a specific
  post — the only real number obtainable is a reaction count, via
  `LINKEDIN_LIST_REACTIONS`'s `paging.total` (requesting `count=1` so the
  call itself stays cheap; the total comes from the paging envelope, not
  from actually paginating every reaction).
- YouTube: already solved — reuses `youtube_upload.fetch_video_analytics`.

Every function here returns `None` for a metric the platform doesn't
expose, never a fabricated zero — `PostMetricSnapshot`'s columns are all
nullable for exactly this reason.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from composio_client import Composio
from sqlalchemy import select

from app.agents.social_media_analyzer.youtube_upload import fetch_video_analytics
from app.config import settings
from app.db.models import ContentItem, PlatformConnection, PostMetricSnapshot, PublishAttempt
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


async def fetch_facebook_post_metrics(connection: PlatformConnection, post_id: str) -> dict:
    client = _client()

    def _execute():
        return client.tools.execute(
            "FACEBOOK_GET_POST",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={
                "post_id": post_id,
                "fields": "likes.summary(true),comments.summary(true),shares,reactions.summary(true)",
            },
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    if not isinstance(data, dict):
        return {"raw_metadata": {}}

    likes = data.get("likes") or {}
    comments = data.get("comments") or {}
    shares = data.get("shares") or {}
    reactions = data.get("reactions") or {}
    # Reactions (all types: like/love/wow/etc.) is a superset of plain
    # likes — prefer it when present since it's the more complete "people
    # who reacted" count, falling back to the plain like count otherwise.
    like_count = (
        (reactions.get("summary") or {}).get("total_count")
        if isinstance(reactions, dict)
        else None
    )
    if like_count is None and isinstance(likes, dict):
        like_count = (likes.get("summary") or {}).get("total_count")

    return {
        "likes": like_count,
        "comments": (comments.get("summary") or {}).get("total_count") if isinstance(comments, dict) else None,
        "shares": shares.get("count") if isinstance(shares, dict) else None,
        "raw_metadata": data,
    }


async def fetch_instagram_post_metrics(connection: PlatformConnection, media_id: str) -> dict:
    client = _client()

    def _execute():
        return client.tools.execute(
            "INSTAGRAM_GET_POST_INSIGHTS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            # Explicit list rather than the auto_safe preset — a fixed,
            # known set of metrics this app's schema has columns for,
            # not whatever the preset happens to include this month.
            # Instagram 400s on a metric unsupported for the media's own
            # type (e.g. "views" on a plain image) — requested
            # individually below and any single failure is caught, not
            # let it fail the whole fetch.
            arguments={"ig_post_id": media_id, "metric": "reach,likes,comments,saved,shares"},
        )

    def _execute_views():
        return client.tools.execute(
            "INSTAGRAM_GET_POST_INSIGHTS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            arguments={"ig_post_id": media_id, "metric": "views"},
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None)
    items = data if isinstance(data, list) else []
    values = {
        item.get("name"): (item.get("values") or [{}])[0].get("value")
        for item in items
        if isinstance(item, dict)
    }

    views = None
    try:
        views_response = await asyncio.to_thread(_execute_views)
        views_data = getattr(views_response, "data", None)
        views_items = views_data if isinstance(views_data, list) else []
        if views_items and isinstance(views_items[0], dict):
            views = (views_items[0].get("values") or [{}])[0].get("value")
    except Exception:
        # Not every media type supports "views" (e.g. a plain image) —
        # not fetching it isn't a real failure of this whole call.
        pass

    return {
        "reach": values.get("reach"),
        "likes": values.get("likes"),
        "comments": values.get("comments"),
        "saves": values.get("saved"),
        "shares": values.get("shares"),
        "views": views,
        "raw_metadata": {"items": items},
    }


async def fetch_linkedin_post_metrics(connection: PlatformConnection, share_urn: str) -> dict:
    """Only a reaction count is genuinely obtainable — no comment, share,
    or impression metric exists anywhere in Composio's current LinkedIn
    toolkit for a specific post, confirmed live. Every other field stays
    null rather than guessed."""
    client = _client()

    def _execute():
        return client.tools.execute(
            "LINKEDIN_LIST_REACTIONS",
            connected_account_id=connection.composio_connected_account_id,
            user_id=str(connection.company_id),
            # count=1: the total comes from the paging envelope, not from
            # actually paginating every reaction — keeps this cheap
            # regardless of how popular the post is.
            arguments={"entity": share_urn, "count": 1},
        )

    response = await asyncio.to_thread(_execute)
    data = getattr(response, "data", None) or {}
    paging = data.get("paging") if isinstance(data, dict) else None
    total = paging.get("total") if isinstance(paging, dict) else None

    return {"likes": total, "raw_metadata": data if isinstance(data, dict) else {}}


async def fetch_youtube_post_metrics(connection: PlatformConnection, video_id: str) -> dict:
    items = await fetch_video_analytics(connection, [video_id])
    if not items:
        return {"raw_metadata": {}}
    item = items[0]
    stats = item.get("statistics") or {}

    def _to_int(value: object) -> int | None:
        try:
            return int(value)  # YouTube's own API returns these as strings
        except (TypeError, ValueError):
            return None

    return {
        "views": _to_int(stats.get("viewCount")),
        "likes": _to_int(stats.get("likeCount")),
        "comments": _to_int(stats.get("commentCount")),
        "raw_metadata": item,
    }


_FETCHER_BY_PLATFORM = {
    "facebook": fetch_facebook_post_metrics,
    "instagram": fetch_instagram_post_metrics,
    "linkedin": fetch_linkedin_post_metrics,
    "youtube": fetch_youtube_post_metrics,
}


async def fetch_post_metrics(connection: PlatformConnection, execution_id: str) -> dict | None:
    """Dispatches to the right platform's fetcher. Returns None for a
    platform with no real metrics capability at all (none currently —
    every connectable platform has at least *something*, even if it's
    just LinkedIn's reaction count) or on a genuine fetch failure, so a
    scheduled sync's per-item error handling can skip it cleanly."""
    fetcher = _FETCHER_BY_PLATFORM.get(connection.platform)
    if fetcher is None:
        return None
    try:
        return await fetcher(connection, execution_id)
    except Exception:
        logger.exception(
            "Post metrics fetch failed for %s execution %s", connection.platform, execution_id
        )
        return None


# ── Scheduled sync ──────────────────────────────────────────────────────
# Same "one row per fetch" shape as PublishAttempt/PlatformMetricSnapshot
# — a fresh PostMetricSnapshot every run, never overwriting the last one,
# so a metric's trajectory over time (the actual signal LoomVerse's
# Analysis needs — "is this post still gaining traction?") is preserved,
# not just its current value.


async def _sync_one_item(item_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        if item is None or item.published_at is None:
            return

        attempt = (
            await session.execute(
                select(PublishAttempt)
                .where(
                    PublishAttempt.content_item_id == item.id,
                    PublishAttempt.status == "success",
                )
                .order_by(PublishAttempt.attempted_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if attempt is None or not attempt.composio_execution_id:
            return

        connection = await session.get(PlatformConnection, attempt.platform_connection_id)
        if connection is None or connection.composio_connected_account_id is None:
            return

        metrics = await fetch_post_metrics(connection, attempt.composio_execution_id)
        if metrics is None:
            return

        session.add(
            PostMetricSnapshot(
                id=uuid.uuid4(),
                content_item_id=item.id,
                likes=metrics.get("likes"),
                comments=metrics.get("comments"),
                shares=metrics.get("shares"),
                saves=metrics.get("saves"),
                views=metrics.get("views"),
                reach=metrics.get("reach"),
                raw_metadata=metrics.get("raw_metadata") or {},
            )
        )
        await session.commit()


async def run_scheduled_post_metrics_sync() -> None:
    """Syncs a fresh metrics snapshot for every published content item —
    failures isolated per item, same pattern as every other scheduled
    batch job in this codebase (`run_scheduled_publishing`,
    `run_scheduled_youtube_uploads`, `run_scheduled_metrics_sync`)."""
    async with async_session_factory() as session:
        item_ids = (
            (
                await session.execute(
                    select(ContentItem.id).where(ContentItem.published_at.is_not(None))
                )
            )
            .scalars()
            .all()
        )

    for item_id in item_ids:
        try:
            await _sync_one_item(item_id)
        except Exception:
            logger.exception("Unexpected error syncing post metrics for item %s", item_id)
