"""Generic OAuth2 authorization-code flow, parameterized per platform via
`oauth_providers.PLATFORM_CONFIGS` — the same two functions handle all 5
platforms rather than five near-duplicate implementations.

No session/cookie system exists in this app (auth is deferred — see
KNOWN_ISSUES.md), so the `state` param carries everything the callback
needs, signed via `app.security.oauth_state` so it can't be forged.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
import uuid
from dataclasses import dataclass

import httpx

from app.agents.social_media_analyzer.oauth_providers import (
    PLATFORM_CONFIGS,
    get_client_credentials,
    get_platform_config,
    is_platform_configured,
)
from app.config import settings
from app.security.oauth_state import OAuthStateError, sign_state, verify_state


class OAuthNotConfiguredError(Exception):
    """Raised when a platform's Client ID/Secret aren't set in settings."""


@dataclass(slots=True)
class TokenResult:
    access_token: str
    refresh_token: str | None
    expires_in: int | None  # seconds, per the token response
    granted_scopes: str | None
    # Resolving the connected account's own id/display name needs a
    # platform-specific follow-up call (e.g. Meta's /me, Google's
    # userinfo endpoint) — deliberately not implemented this round, same
    # "schema exists, fetching logic doesn't" scope as the metrics
    # snapshot table. Left None; the connection still persists correctly
    # without it, just without a friendly display name yet.
    external_account_id: str | None = None
    external_account_name: str | None = None


def _require_known_platform(platform: str) -> None:
    if platform not in PLATFORM_CONFIGS:
        raise ValueError(f"Unknown platform: {platform!r}")


def _callback_url(platform: str) -> str:
    return f"{settings.APP_BASE_URL}/api/v1/social-media-analyzer/connections/{platform}/callback"


def _make_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(platform: str, company_id: uuid.UUID) -> str:
    """Build the platform's real OAuth authorize URL with a signed state
    param. Raises `OAuthNotConfiguredError` if that platform's Client
    ID/Secret aren't configured."""
    _require_known_platform(platform)
    if not is_platform_configured(platform):
        raise OAuthNotConfiguredError(
            f"{platform} OAuth is not configured — set its client ID/secret in .env"
        )

    config = get_platform_config(platform)
    client_id, _ = get_client_credentials(platform)

    state_payload: dict[str, str] = {
        "company_id": str(company_id),
        "platform": platform,
        "nonce": secrets.token_urlsafe(16),
    }

    params = {
        "client_id": client_id,
        "redirect_uri": _callback_url(platform),
        "response_type": "code",
        "scope": " ".join(config.scopes),
    }

    if config.pkce:
        verifier, challenge = _make_pkce_pair()
        state_payload["pkce_code_verifier"] = verifier
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"

    params["state"] = sign_state(state_payload)

    return f"{config.authorize_url}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(platform: str, code: str, state: str) -> tuple[TokenResult, dict]:
    """Verify `state`, exchange `code` for tokens against the platform's
    token endpoint. Returns `(TokenResult, state_payload)` so the caller
    gets `company_id` back out of the verified state. Raises
    `OAuthStateError` (invalid/expired/tampered state),
    `OAuthNotConfiguredError`, or `httpx.HTTPStatusError` (token exchange
    itself failed)."""
    _require_known_platform(platform)
    if not is_platform_configured(platform):
        raise OAuthNotConfiguredError(f"{platform} OAuth is not configured")

    state_payload = verify_state(state)
    if state_payload.get("platform") != platform:
        raise OAuthStateError("State token platform does not match callback platform")

    config = get_platform_config(platform)
    client_id, client_secret = get_client_credentials(platform)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _callback_url(platform),
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if config.pkce:
        data["code_verifier"] = state_payload.get("pkce_code_verifier", "")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(config.token_url, data=data)
        response.raise_for_status()
        payload = response.json()

    return (
        TokenResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            granted_scopes=payload.get("scope"),
        ),
        state_payload,
    )
