"""Tests for signed, timestamped OAuth `state` tokens."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.security import oauth_state


def _configure_key(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_sign_and_verify_round_trips(monkeypatch):
    _configure_key(monkeypatch)

    token = oauth_state.sign_state({"company_id": "abc", "platform": "instagram"})
    payload = oauth_state.verify_state(token)

    assert payload == {"company_id": "abc", "platform": "instagram"}


def test_verify_rejects_tampered_token(monkeypatch):
    _configure_key(monkeypatch)
    token = oauth_state.sign_state({"company_id": "abc"})

    body, _, signature = token.partition(".")
    tampered = f"{body}x.{signature}"

    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify_state(tampered)


def test_verify_rejects_wrong_signing_key(monkeypatch):
    _configure_key(monkeypatch)
    token = oauth_state.sign_state({"company_id": "abc"})

    _configure_key(monkeypatch)  # rotate to a different key

    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify_state(token)


def test_verify_rejects_expired_token(monkeypatch):
    _configure_key(monkeypatch)
    token = oauth_state.sign_state({"company_id": "abc"})

    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify_state(token, max_age_seconds=-1)


def test_verify_rejects_malformed_token(monkeypatch):
    _configure_key(monkeypatch)

    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify_state("not-a-real-token")


def test_sign_raises_when_key_not_configured(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "TOKEN_ENCRYPTION_KEY", "")

    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.sign_state({"company_id": "abc"})
