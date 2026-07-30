"""Verifies Supabase-issued session JWTs on incoming requests.

This app's entire authorization model is "has a valid Supabase session" —
any signed-in user can act on any company's data. There's no per-user
data isolation or roles; that's a deliberate scope match to "logged-in
MMCS team members only," not a placeholder for something more granular.

Supabase projects sign session tokens one of two ways, and which one is
active isn't something this app should assume — it reads each token's
own `alg` header and verifies accordingly:

- **HS256** (the long-standing default): a shared secret,
  `SUPABASE_JWT_SECRET` (Settings → API → JWT Settings → "Legacy JWT
  Secret"). Verified locally, no network call.
- **ES256/RS256** (newer, opt-in asymmetric signing keys): verified
  against the project's public JWKS endpoint — needs only
  `SUPABASE_URL`, no secret at all, since the whole point of asymmetric
  signing is that the verification key is public.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Query, Request

from app.config import settings

# Supabase's own session tokens always carry this audience claim.
_AUDIENCE = "authenticated"

# Keyed by SUPABASE_URL rather than a bare singleton, so tests that
# monkeypatch the setting to a different (or empty) URL get a correctly
# separate client instead of reusing one built against a stale URL.
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


@dataclass(slots=True)
class CurrentUser:
    id: str
    email: str | None


class AuthNotConfiguredError(Exception):
    """Raised when the setting needed to verify this token's signing
    algorithm isn't set."""


def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    if supabase_url not in _jwks_clients:
        _jwks_clients[supabase_url] = jwt.PyJWKClient(
            f"{supabase_url}/auth/v1/.well-known/jwks.json"
        )
    return _jwks_clients[supabase_url]


def _decode(token: str) -> CurrentUser:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid session token: {exc}") from exc

    try:
        if alg == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise AuthNotConfiguredError("SUPABASE_JWT_SECRET is not configured")
            payload = jwt.decode(
                token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience=_AUDIENCE
            )
        else:
            if not settings.SUPABASE_URL:
                raise AuthNotConfiguredError("SUPABASE_URL is not configured")
            signing_key = _jwks_client(settings.SUPABASE_URL).get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=[alg], audience=_AUDIENCE)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired session: {exc}") from exc

    return CurrentUser(id=payload["sub"], email=payload.get("email"))


async def get_current_user(
    request: Request,
    access_token: str | None = Query(
        default=None,
        description=(
            "Fallback for endpoints the browser navigates to directly (plain "
            "`<a href>`, not a fetch call) — those can't carry a custom "
            "Authorization header. Prefer the header everywhere else."
        ),
    ),
) -> CurrentUser:
    """FastAPI dependency — raises 401 if there's no valid session, 503 if
    auth isn't configured at all yet. Applied at router-inclusion level in
    `main.py` (and each endpoint file's own router) so it gates every
    existing endpoint without touching any of their individual
    signatures."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else access_token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return _decode(token)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
