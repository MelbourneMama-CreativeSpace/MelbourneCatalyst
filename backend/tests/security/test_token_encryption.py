"""Tests for Fernet-based OAuth token encryption at rest."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.security import token_encryption


def test_encrypt_decrypt_round_trips(monkeypatch):
    monkeypatch.setattr(
        token_encryption.settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )

    ciphertext = token_encryption.encrypt_token("a-real-oauth-access-token")

    assert ciphertext != "a-real-oauth-access-token"
    assert token_encryption.decrypt_token(ciphertext) == "a-real-oauth-access-token"


def test_encrypt_raises_when_key_not_configured(monkeypatch):
    monkeypatch.setattr(token_encryption.settings, "TOKEN_ENCRYPTION_KEY", "")

    with pytest.raises(token_encryption.TokenEncryptionNotConfiguredError):
        token_encryption.encrypt_token("some-token")


def test_decrypt_raises_when_key_not_configured(monkeypatch):
    monkeypatch.setattr(token_encryption.settings, "TOKEN_ENCRYPTION_KEY", "")

    with pytest.raises(token_encryption.TokenEncryptionNotConfiguredError):
        token_encryption.decrypt_token("anything")


def test_decrypt_fails_with_wrong_key(monkeypatch):
    monkeypatch.setattr(
        token_encryption.settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    ciphertext = token_encryption.encrypt_token("a-token")

    monkeypatch.setattr(
        token_encryption.settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )

    with pytest.raises(ValueError):
        token_encryption.decrypt_token(ciphertext)


def test_encrypt_raises_value_error_for_malformed_key(monkeypatch):
    monkeypatch.setattr(token_encryption.settings, "TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    with pytest.raises(ValueError):
        token_encryption.encrypt_token("a-token")
