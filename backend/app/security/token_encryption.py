"""Fernet symmetric encryption for OAuth tokens at rest.

OAuth access/refresh tokens are real third-party credentials — unlike
everything else this app stores, a leaked row here grants access to a
user's actual social media account. `TOKEN_ENCRYPTION_KEY` must be a
valid Fernet key (32 url-safe base64-encoded bytes); generate one with
`Fernet.generate_key()` and keep it out of version control, same as any
other secret in `.env`.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class TokenEncryptionNotConfiguredError(Exception):
    """Raised when TOKEN_ENCRYPTION_KEY is unset — callers must not fall
    back to storing tokens in plaintext."""


def _fernet() -> Fernet:
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise TokenEncryptionNotConfiguredError(
            "TOKEN_ENCRYPTION_KEY is not configured — cannot encrypt/decrypt OAuth tokens"
        )
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token for storage. Raises `TokenEncryptionNotConfiguredError`
    if no key is set, and `ValueError` if the configured key is malformed."""
    try:
        return _fernet().encrypt(plaintext.encode()).decode()
    except TokenEncryptionNotConfiguredError:
        raise
    except Exception as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token read from storage. Raises
    `TokenEncryptionNotConfiguredError` if no key is set, and `ValueError`
    if the ciphertext can't be decrypted with the configured key (wrong
    key, corrupted data, or tampering)."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except TokenEncryptionNotConfiguredError:
        raise
    except InvalidToken as exc:
        raise ValueError("Could not decrypt token — wrong key or corrupted data") from exc
    except Exception as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from exc
