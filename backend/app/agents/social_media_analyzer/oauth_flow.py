"""Thin async wrapper around Composio's connected-accounts flow —
Composio brokers the actual OAuth2 exchange and custodies tokens; this
app only ever holds a reference id (`composio_connected_account_id`).

`composio-client`'s methods are synchronous; every call here runs via
`asyncio.to_thread` so it doesn't block the event loop, same reasoning
as any sync third-party SDK used from an async FastAPI handler.

Registering a platform's own OAuth app (client id/secret) happens once,
by hand, in Composio's dashboard — not through this SDK, which (as of
`composio-client` 1.42.0) doesn't accept raw client credentials
programmatically for a custom auth config. See `oauth_providers.py` and
`.env.example` for what each `COMPOSIO_<PLATFORM>_AUTH_CONFIG_ID`
setting expects.
"""

from __future__ import annotations

import asyncio
import uuid

from composio_client import Composio

from app.agents.social_media_analyzer.oauth_providers import (
    get_auth_config_id,
    get_platform_config,
    is_platform_configured,
)
from app.config import settings

# Composio's own connection-status vocabulary, mapped to this app's
# simpler status column. INITIALIZING/INITIATED both mean "the user
# hasn't finished platform-side consent yet."
_STATUS_MAP: dict[str, str] = {
    "ACTIVE": "connected",
    "INITIALIZING": "pending",
    "INITIATED": "pending",
    "FAILED": "error",
    "INACTIVE": "error",
    "REVOKED": "error",
    "EXPIRED": "expired",
}


class ComposioNotConfiguredError(Exception):
    """Raised when COMPOSIO_API_KEY or a platform's auth config id isn't set."""


def _require_known_platform(platform: str) -> None:
    get_platform_config(platform)  # raises ValueError for an unknown platform


def _client() -> Composio:
    return Composio(api_key=settings.COMPOSIO_API_KEY)


def map_status(composio_status: str) -> str:
    return _STATUS_MAP.get(composio_status, "error")


async def initiate_connection(
    platform: str, company_id: uuid.UUID, callback_url: str
) -> tuple[str, str]:
    """Starts a Composio-brokered connection for `company_id` (Composio's
    per-tenant `user_id`) against `platform`'s toolkit. Returns
    `(composio_connected_account_id, redirect_url)` — send the browser to
    `redirect_url`. Raises `ComposioNotConfiguredError` if
    `COMPOSIO_API_KEY` or this platform's auth config id isn't set."""
    _require_known_platform(platform)
    if not is_platform_configured(platform):
        raise ComposioNotConfiguredError(
            f"{platform} is not configured — set COMPOSIO_API_KEY and "
            f"its Composio auth config id in .env"
        )

    config = get_platform_config(platform)
    auth_config_id = get_auth_config_id(platform)
    client = _client()

    def _create():
        return client.connected_accounts.create(
            auth_config={"id": auth_config_id},
            connection={"user_id": str(company_id), "callback_url": callback_url},
        )

    response = await asyncio.to_thread(_create)
    if not response.redirect_url:
        raise ComposioNotConfiguredError(
            f"Composio did not return a redirect URL for {platform} — check that its "
            f"auth config ({config.toolkit_slug}) is set up correctly in the Composio dashboard"
        )
    return response.id, response.redirect_url


async def get_connection_status(composio_connected_account_id: str) -> str:
    """Current status of a previously-initiated connection, mapped to
    this app's status vocabulary. Never raises for a not-found id —
    treated as an error state, since the row referencing it is stale."""
    client = _client()
    try:
        response = await asyncio.to_thread(
            client.connected_accounts.retrieve, composio_connected_account_id
        )
    except Exception:
        return "error"
    return map_status(response.status)


async def disconnect_connection(composio_connected_account_id: str) -> None:
    """Deletes the connection on Composio's side and revokes the token
    with the platform. Swallows a not-found error — the local row is
    being cleared either way."""
    client = _client()
    try:
        await asyncio.to_thread(
            client.connected_accounts.delete,
            composio_connected_account_id,
            revoke_on_delete=True,
        )
    except Exception:
        pass
