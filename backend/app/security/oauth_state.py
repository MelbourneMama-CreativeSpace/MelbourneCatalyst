"""Signed, timestamped `state` tokens for the OAuth authorization-code flow.

There's no session/cookie system in this app (auth is explicitly
deferred — see KNOWN_ISSUES.md), so the OAuth `state` param can't be
looked up server-side. Instead the state itself carries everything the
callback needs (company_id, platform, a nonce, and — for X's PKCE flow —
the code_verifier), signed with HMAC-SHA256 so it can't be forged or
tampered with, and timestamped so a stale/replayed callback is rejected.

Reuses `TOKEN_ENCRYPTION_KEY` as the HMAC key material rather than
introducing a second secret to configure — it's already required for
this same OAuth feature, and HMAC accepts any byte string as a key
(unlike Fernet, which requires that specific 32-byte format), so this
does not depend on `token_encryption.py`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import settings


class OAuthStateError(Exception):
    """Raised when a state token is missing, malformed, tampered with,
    expired, or signed with no key configured."""


def _signing_key() -> bytes:
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise OAuthStateError("TOKEN_ENCRYPTION_KEY is not configured — cannot sign OAuth state")
    return settings.TOKEN_ENCRYPTION_KEY.encode()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def sign_state(payload: dict[str, Any]) -> str:
    """Sign `payload` (must be JSON-serializable) into an opaque,
    URL-safe state token embedding the current timestamp."""
    body = json.dumps({"payload": payload, "ts": int(time.time())}, sort_keys=True).encode()
    body_b64 = _b64encode(body)
    signature = hmac.new(_signing_key(), body_b64.encode(), hashlib.sha256).hexdigest()
    return f"{body_b64}.{signature}"


def verify_state(token: str, max_age_seconds: int = 600) -> dict[str, Any]:
    """Verify and decode a state token. Raises `OAuthStateError` if the
    signature doesn't match, the token is malformed, or it's older than
    `max_age_seconds`."""
    body_b64, _, signature = token.partition(".")
    if not signature:
        raise OAuthStateError("Malformed state token")

    expected = hmac.new(_signing_key(), body_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise OAuthStateError("State token signature does not match — tampered or forged")

    try:
        body = json.loads(_b64decode(body_b64))
    except Exception as exc:
        raise OAuthStateError("Malformed state token") from exc

    if time.time() - body.get("ts", 0) > max_age_seconds:
        raise OAuthStateError("State token has expired")

    return body["payload"]
