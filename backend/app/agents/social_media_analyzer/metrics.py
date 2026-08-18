"""Fetching platform metrics via Composio's tool-execution endpoint. Same
shape as `publish.py` — synchronous `composio-client` calls run via
`asyncio.to_thread`.

Confirmed live against real connected accounts (Mindfries' Facebook page
and YouTube channel) — not guessed:

- Facebook: `FACEBOOK_GET_PAGE_INSIGHTS` needs `page_id`, which is
  exactly `PlatformConnection.external_account_id` (already resolved and
  cached at connect time — see `publish.py`'s `_resolve_facebook_page_id`).
  Its response nests the metrics list under `.data` (`{"data": [{"name":
  "page_follows", "values": [{"value": N}]}]}`), the same shape Meta uses
  for `INSTAGRAM_GET_POST_INSIGHTS` (see `post_metrics.py`'s
  `_extract_insight_items` for the same fix applied there).
- YouTube: `YOUTUBE_GET_CHANNEL_STATISTICS` accepts `mine=true` instead of
  a channel id — no id resolution/caching needed. Its response is
  `{"channels": [{"statistics": {"subscriberCount": "N", ...}}]}` (counts
  as strings, same as `fetch_video_analytics` already handles).
- LinkedIn: `LINKEDIN_GET_ORG_PAGE_STATS` genuinely doesn't apply here —
  it requires an *organization* URN (`urn:li:organization:{id}`), but a
  personal-profile connection's `external_account_id` is a *person* URN
  (`urn:li:person:{id}`, confirmed against Mindfries' own connection) —
  confirmed no other account-level stats tool exists anywhere in
  Composio's real LinkedIn toolkit for a personal profile.
- Instagram: confirmed no account-level insights tool exists anywhere in
  Composio's real Instagram toolkit at all (only per-media insights,
  already used by `post_metrics.py`).

LinkedIn/Instagram (and Twitter/TikTok, never yet connected in this
environment to verify against) are left unconfigured for exactly this
reason — `COMPOSIO_*_METRICS_TOOL_SLUG` stays unset for them rather than
pointing at a tool that doesn't apply. The full response is always stored
as-is in `raw_metadata` regardless of platform; only `follower_count`/
`engagement_rate` are promoted to their own columns, via each platform's
real parser below.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from composio_client import Composio
from sqlalchemy import select

from app.agents.social_media_analyzer.oauth_providers import (
    get_metrics_tool_slug,
    is_metrics_configured,
)
from app.config import settings
from app.db.models import PlatformConnection, PlatformMetricSnapshot
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class MetricsNotConfiguredError(Exception):
    """Raised when COMPOSIO_API_KEY or this platform's metrics tool slug
    isn't set — the caller maps this to a 409, same pattern `publish_post`
    already uses for `PublishNotConfiguredError`."""


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


def _as_dict(response: object) -> dict:
    data = getattr(response, "data", response)
    if isinstance(data, dict):
        return data
    # Some SDK response objects are Pydantic models, not plain dicts —
    # fall back to whatever dict-like view is available rather than
    # guessing a shape; an unrecognized response just yields an empty
    # dict, which the caller stores as-is (visible, not fabricated).
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return {}


# Platform-specific request arguments, confirmed against each tool's real
# input schema (`client.tools.retrieve(slug)`) — `{}` (the old universal
# default) 400s on both of these in practice, they're genuinely required.
def _facebook_args(external_account_id: str | None) -> dict:
    return {"page_id": external_account_id, "period": "lifetime"} if external_account_id else {}


def _youtube_args(external_account_id: str | None) -> dict:
    # No id resolution needed — "mine" asks for the authenticated
    # connection's own channel directly.
    return {"mine": True}


_ARGS_BUILDER_BY_PLATFORM = {
    "facebook": _facebook_args,
    "youtube": _youtube_args,
}


# Platform-specific response parsing, confirmed live against real
# connected accounts (see this module's docstring) — every platform
# genuinely nests its numbers differently, the same lesson already
# learned the hard way in post_metrics.py's _extract_insight_items.
def _parse_facebook(data: dict) -> tuple[int | None, float | None]:
    items = data.get("data") if isinstance(data.get("data"), list) else []
    follows = next((i for i in items if isinstance(i, dict) and i.get("name") == "page_follows"), None)
    value = (follows.get("values") or [{}])[0].get("value") if follows else None
    return (value if isinstance(value, int) else None), None


def _parse_youtube(data: dict) -> tuple[int | None, float | None]:
    channels = data.get("channels") if isinstance(data.get("channels"), list) else []
    stats = channels[0].get("statistics") if channels and isinstance(channels[0], dict) else None
    raw = stats.get("subscriberCount") if isinstance(stats, dict) else None
    try:
        return (int(raw) if raw is not None else None), None
    except (TypeError, ValueError):
        return None, None


def _parse_generic(data: dict) -> tuple[int | None, float | None]:
    """The original best-effort behavior for any platform without a
    confirmed real response shape yet (LinkedIn/Instagram have no
    account-level tool at all; Twitter/TikTok have never been connected
    in this environment to verify against) — read literal top-level
    keys, never guess a nested shape."""
    follower_count = data.get("follower_count")
    engagement_rate = data.get("engagement_rate")
    return (
        follower_count if isinstance(follower_count, int) else None,
        engagement_rate if isinstance(engagement_rate, (int, float)) else None,
    )


_PARSER_BY_PLATFORM = {
    "facebook": _parse_facebook,
    "youtube": _parse_youtube,
}


async def fetch_platform_metrics(
    platform_connection_id: uuid.UUID,
    platform: str,
    connected_account_id: str,
    external_account_id: str | None = None,
    company_id: str | None = None,
) -> PlatformMetricSnapshot:
    """Executes the platform's configured "get metrics" tool and returns a
    new, unpersisted `PlatformMetricSnapshot` — the caller adds it to a
    session and commits. Raises `MetricsNotConfiguredError` if unset; any
    other failure (a real Composio/platform-side error) propagates as-is
    so the caller can log the real reason, same as `publish_post`."""
    if not is_metrics_configured(platform):
        # User-safe message — never name internal env vars/config files
        # here, the specific gap is logged for whoever manages the
        # deployment instead.
        logger.warning(
            "%s metrics aren't configured (COMPOSIO_API_KEY / its metrics tool slug "
            "missing in .env)",
            platform,
        )
        raise MetricsNotConfiguredError(
            f"{platform.capitalize()} metrics aren't set up yet."
        )

    tool_slug = get_metrics_tool_slug(platform)
    client = _client()
    args_builder = _ARGS_BUILDER_BY_PLATFORM.get(platform)
    arguments = args_builder(external_account_id) if args_builder else {}

    def _execute():
        return client.tools.execute(
            tool_slug,
            connected_account_id=connected_account_id,
            # Confirmed live, the hard way (a real 400: "User ID is
            # required with connected account") — same requirement every
            # other real Composio call in this codebase already handles
            # (publish.py, post_metrics.py); this one just never had it.
            user_id=company_id,
            arguments=arguments,
        )

    response = await asyncio.to_thread(_execute)
    data = _as_dict(response)

    parser = _PARSER_BY_PLATFORM.get(platform, _parse_generic)
    follower_count, engagement_rate = parser(data)

    return PlatformMetricSnapshot(
        id=uuid.uuid4(),
        platform_connection_id=platform_connection_id,
        captured_at=datetime.now(timezone.utc),
        follower_count=follower_count,
        engagement_rate=engagement_rate,
        raw_metadata=data,
    )


async def _sync_one_connection(connection_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        connection = await session.get(PlatformConnection, connection_id)
        if connection is None or connection.composio_connected_account_id is None:
            return
        try:
            snapshot = await fetch_platform_metrics(
                connection.id,
                connection.platform,
                connection.composio_connected_account_id,
                connection.external_account_id,
                str(connection.company_id),
            )
        except MetricsNotConfiguredError:
            return  # not an error — just nothing to do for this platform yet
        except Exception:
            logger.exception("Scheduled metrics sync failed for connection %s", connection_id)
            return
        session.add(snapshot)
        await session.commit()


async def run_scheduled_metrics_sync() -> None:
    """Syncs a fresh metrics snapshot for every currently-connected
    platform — failures isolated per connection, same pattern as every
    other scheduled batch job in this codebase (`run_scheduled_publishing`,
    `run_scheduled_reindex`)."""
    async with async_session_factory() as session:
        connection_ids = (
            (
                await session.execute(
                    select(PlatformConnection.id).where(
                        PlatformConnection.status == "connected"
                    )
                )
            )
            .scalars()
            .all()
        )

    for connection_id in connection_ids:
        try:
            await _sync_one_connection(connection_id)
        except Exception:
            logger.exception(
                "Unexpected error during scheduled metrics sync for connection %s", connection_id
            )
