"""Tests for the generic OAuth2 authorization-code flow."""

from __future__ import annotations

import urllib.parse
import uuid

import pytest
from cryptography.fernet import Fernet

from app.agents.social_media_analyzer import oauth_flow
from app.security import oauth_state


def _configure_token_key(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(oauth_flow.settings, "TOKEN_ENCRYPTION_KEY", oauth_state.settings.TOKEN_ENCRYPTION_KEY)


def test_build_authorize_url_raises_when_platform_not_configured(monkeypatch):
    _configure_token_key(monkeypatch)
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_ID", "")
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_SECRET", "")

    with pytest.raises(oauth_flow.OAuthNotConfiguredError):
        oauth_flow.build_authorize_url("instagram", uuid.uuid4())


def test_build_authorize_url_raises_for_unknown_platform(monkeypatch):
    _configure_token_key(monkeypatch)

    with pytest.raises(ValueError):
        oauth_flow.build_authorize_url("myspace", uuid.uuid4())


def test_build_authorize_url_includes_client_id_and_signed_state(monkeypatch):
    _configure_token_key(monkeypatch)
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_SECRET", "test-client-secret")

    company_id = uuid.uuid4()
    url = oauth_flow.build_authorize_url("instagram", company_id)

    parsed = urllib.parse.urlparse(url)
    assert parsed.netloc == "www.facebook.com"
    params = urllib.parse.parse_qs(parsed.query)
    assert params["client_id"] == ["test-client-id"]
    assert "state" in params

    decoded = oauth_state.verify_state(params["state"][0])
    assert decoded["company_id"] == str(company_id)
    assert decoded["platform"] == "instagram"


def test_build_authorize_url_includes_pkce_challenge_for_twitter(monkeypatch):
    _configure_token_key(monkeypatch)
    monkeypatch.setattr(oauth_flow.settings, "TWITTER_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(oauth_flow.settings, "TWITTER_OAUTH_CLIENT_SECRET", "test-client-secret")

    url = oauth_flow.build_authorize_url("twitter", uuid.uuid4())

    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert "code_challenge" in params
    assert params["code_challenge_method"] == ["S256"]

    decoded = oauth_state.verify_state(params["state"][0])
    assert "pkce_code_verifier" in decoded


async def test_exchange_code_for_token_rejects_platform_mismatch(monkeypatch):
    _configure_token_key(monkeypatch)
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_SECRET", "test-client-secret")

    # A state token genuinely signed for "twitter", presented on the
    # "instagram" callback — should be rejected rather than silently
    # trusted, since that would let a callback for one platform's flow
    # complete a different platform's connection.
    state = oauth_state.sign_state({"company_id": str(uuid.uuid4()), "platform": "twitter"})

    with pytest.raises(oauth_state.OAuthStateError):
        await oauth_flow.exchange_code_for_token("instagram", "some-code", state)


async def test_exchange_code_for_token_parses_a_successful_response(monkeypatch):
    _configure_token_key(monkeypatch)
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(oauth_flow.settings, "META_APP_CLIENT_SECRET", "test-client-secret")

    company_id = uuid.uuid4()
    state = oauth_state.sign_state({"company_id": str(company_id), "platform": "instagram"})

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "real-token", "expires_in": 3600, "scope": "instagram_basic"}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data):
            return _FakeResponse()

    monkeypatch.setattr(oauth_flow.httpx, "AsyncClient", lambda **kwargs: _FakeClient())

    result, state_payload = await oauth_flow.exchange_code_for_token("instagram", "some-code", state)

    assert result.access_token == "real-token"
    assert result.expires_in == 3600
    assert state_payload["company_id"] == str(company_id)
