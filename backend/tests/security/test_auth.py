"""Tests for Supabase JWT verification.

Uses self-signed tokens (a throwaway secret set via monkeypatch, never a
real Supabase project) — same "prove the logic without live credentials"
approach used throughout this codebase.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.security import auth

_SECRET = "test-secret-long-enough-for-hs256-not-a-real-key"
_OTHER_SECRET = "a-different-secret-also-long-enough-for-hs256"


def _sign(secret: str, **claims) -> str:
    payload = {"sub": "user-123", "email": "person@example.com", "aud": "authenticated", **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


class _FakeRequest:
    def __init__(self, authorization: str | None = None):
        self.headers = {"authorization": authorization} if authorization else {}


async def test_get_current_user_accepts_a_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_SECRET)

    user = await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert user.id == "user-123"
    assert user.email == "person@example.com"


async def test_get_current_user_accepts_bearer_header_case_insensitively(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_SECRET)

    user = await auth.get_current_user(_FakeRequest(f"bearer {token}"), None)

    assert user.id == "user-123"


async def test_get_current_user_falls_back_to_query_param(monkeypatch):
    """The OAuth authorize redirect is a plain `<a href>` browser
    navigation — it can't carry a custom header, only query params."""
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_SECRET)

    user = await auth.get_current_user(_FakeRequest(), token)

    assert user.id == "user-123"


async def test_get_current_user_prefers_header_over_query_param(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    header_token = _sign(_SECRET, sub="header-user")
    query_token = _sign(_SECRET, sub="query-user")

    user = await auth.get_current_user(_FakeRequest(f"Bearer {header_token}"), query_token)

    assert user.id == "header-user"


async def test_get_current_user_401s_with_no_token_at_all(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(), None)

    assert exc_info.value.status_code == 401


async def test_get_current_user_401s_for_a_token_signed_with_the_wrong_secret(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_OTHER_SECRET)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 401


async def test_get_current_user_401s_for_an_expired_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_SECRET, exp=int(time.time()) - 3600)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 401


async def test_get_current_user_401s_for_a_token_with_the_wrong_audience(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = jwt.encode({"sub": "user-123", "aud": "some-other-app"}, _SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 401


async def test_get_current_user_503s_when_auth_is_not_configured(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", "")
    token = _sign("whatever-doesnt-matter-here-not-verified")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 503


# --- ES256, for Supabase projects with asymmetric signing keys enabled --
#
# No shared secret exists for this mode — the whole point of asymmetric
# signing is that the verification key is public. These tests generate a
# throwaway EC keypair and stub `_jwks_client` to hand back its public
# half, rather than hitting a real network endpoint.


def _sign_es256(private_key, **claims) -> str:
    payload = {"sub": "user-456", "email": "es256@example.com", "aud": "authenticated", **claims}
    return jwt.encode(payload, private_key, algorithm="ES256")


def _stub_jwks_client(public_key):
    return lambda url: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
    )


async def test_get_current_user_verifies_an_es256_token_via_jwks(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = _sign_es256(private_key)

    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(auth.settings, "SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setattr(auth, "_jwks_client", _stub_jwks_client(private_key.public_key()))

    user = await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert user.id == "user-456"
    assert user.email == "es256@example.com"


async def test_get_current_user_401s_for_an_es256_token_signed_with_the_wrong_key(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    a_different_private_key = ec.generate_private_key(ec.SECP256R1())
    token = _sign_es256(private_key)

    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(auth.settings, "SUPABASE_URL", "https://fake-project.supabase.co")
    # JWKS hands back the wrong public key — as if the token were forged
    # or signed by a different project entirely.
    monkeypatch.setattr(
        auth, "_jwks_client", _stub_jwks_client(a_different_private_key.public_key())
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 401


async def test_get_current_user_503s_for_an_es256_token_when_supabase_url_not_configured(
    monkeypatch,
):
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = _sign_es256(private_key)

    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(auth.settings, "SUPABASE_URL", "")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest(f"Bearer {token}"), None)

    assert exc_info.value.status_code == 503


# --- End-to-end through a real route, not just the dependency directly ----


def _build_protected_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(auth.get_current_user)])
    async def protected():
        return {"ok": True}

    return app


async def test_a_protected_route_401s_without_a_session(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)

    transport = ASGITransport(app=_build_protected_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/protected")

    assert response.status_code == 401


async def test_a_protected_route_200s_with_a_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "SUPABASE_JWT_SECRET", _SECRET)
    token = _sign(_SECRET)

    transport = ASGITransport(app=_build_protected_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
