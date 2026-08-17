"""Fetching platform metrics via Composio's tool-execution endpoint. Same
shape as `publish.py` — synchronous `composio-client` calls run via
`asyncio.to_thread`. Unlike `publish_post()`, this deliberately does NOT
parse the platform's response into a fixed schema: no real connected
account exists in this dev environment to verify any platform's actual
response shape against, so guessing at nested field names would produce
code that looks done but silently breaks on real data. The full response
is stored as-is in `raw_metadata`; only `follower_count`/`engagement_rate`
are opportunistically read, and only if the response has a literal
top-level key with exactly that name — best-effort, not a real parser.
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


async def fetch_platform_metrics(
    platform_connection_id: uuid.UUID, platform: str, connected_account_id: str
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

    def _execute():
        return client.tools.execute(
            tool_slug,
            connected_account_id=connected_account_id,
            arguments={},
        )

    response = await asyncio.to_thread(_execute)
    data = _as_dict(response)

    follower_count = data.get("follower_count")
    engagement_rate = data.get("engagement_rate")

    return PlatformMetricSnapshot(
        id=uuid.uuid4(),
        platform_connection_id=platform_connection_id,
        captured_at=datetime.now(timezone.utc),
        follower_count=follower_count if isinstance(follower_count, int) else None,
        engagement_rate=engagement_rate if isinstance(engagement_rate, (int, float)) else None,
        raw_metadata=data,
    )


async def _sync_one_connection(connection_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        connection = await session.get(PlatformConnection, connection_id)
        if connection is None or connection.composio_connected_account_id is None:
            return
        try:
            snapshot = await fetch_platform_metrics(
                connection.id, connection.platform, connection.composio_connected_account_id
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
