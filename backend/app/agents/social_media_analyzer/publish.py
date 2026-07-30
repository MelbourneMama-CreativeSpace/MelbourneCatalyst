"""Publishing a post via Composio's tool-execution endpoint.

Same shape as `oauth_flow.py` — synchronous `composio-client` calls run
via `asyncio.to_thread`, `_client()` constructs the client fresh per call.
Uses `client.tools.execute()` (confirmed against the real installed
`composio-client` 1.42.0 package, `resources/tools.py`), the same
low-level action-execution endpoint Composio's own agentic-tool-use
integrations use — not guessed, verified by reading the installed SDK.
"""

from __future__ import annotations

import asyncio

from composio_client import Composio

from app.agents.social_media_analyzer.oauth_providers import (
    get_post_tool_slug,
    is_publishing_configured,
)
from app.config import settings


class PublishNotConfiguredError(Exception):
    """Raised when COMPOSIO_API_KEY or this platform's post tool slug
    isn't set — the caller maps this to a 409, same pattern `authorize()`
    already uses for the connection flow."""


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


async def publish_post(platform: str, connected_account_id: str, text: str) -> str:
    """Executes the platform's configured "create a post" tool against the
    given connected account. Returns Composio's execution id on success.
    Raises `PublishNotConfiguredError` if not configured; any other
    failure (a real Composio/platform-side error) propagates as-is so the
    caller can log the real reason rather than a swallowed generic
    failure — unlike the connection flow, a failed *publish* is something
    the caller needs the real detail of to show the user."""
    if not is_publishing_configured(platform):
        raise PublishNotConfiguredError(
            f"{platform} publishing is not configured — set COMPOSIO_API_KEY and "
            f"its Composio post tool slug in .env"
        )

    tool_slug = get_post_tool_slug(platform)
    client = _client()

    def _execute():
        return client.tools.execute(
            tool_slug,
            connected_account_id=connected_account_id,
            arguments={"text": text},
        )

    response = await asyncio.to_thread(_execute)
    return str(getattr(response, "id", None) or getattr(response, "data", response))
