"""Media & Asset Library storage — thin wrapper around the official
`supabase` Python SDK's Storage client. Its real async API
(`create_async_client`, `bucket.upload/remove/get_public_url`, and that
`get_public_url` is itself a coroutine, along with `FileOptions`'
dash-cased keys like "content-type") was confirmed by introspecting the
actual installed package before writing this — same discipline as
`social_media_analyzer/publish.py`'s composio-client integration.
"""

from __future__ import annotations

import uuid

from supabase import AsyncClient, create_async_client

from app.config import settings
from app.db.models import MediaAsset


class MediaLibraryNotConfiguredError(Exception):
    """Raised when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY isn't set —
    the caller maps this to a 409, same pattern as Composio's
    PublishNotConfiguredError."""


def is_media_library_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def _require_configured() -> None:
    if not is_media_library_configured():
        raise MediaLibraryNotConfiguredError(
            "Media library isn't configured — set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in .env, and create the "
            f"'{settings.SUPABASE_STORAGE_BUCKET}' bucket once in Supabase's dashboard."
        )


async def _client() -> AsyncClient:
    return await create_async_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def upload_asset(
    company_id: uuid.UUID,
    filename: str,
    content_type: str,
    data: bytes,
    *,
    tags: list[str] | None = None,
    uploaded_by: str | None = None,
) -> MediaAsset:
    """Uploads `data` to the configured bucket and returns a new,
    unpersisted `MediaAsset` — the caller adds it to a session and
    commits (this function only handles the storage side, matching every
    other agent module's separation between an external call and DB
    persistence). Raises `MediaLibraryNotConfiguredError` if unset; any
    other failure (a real Supabase-side error) propagates as-is so the
    caller can surface the real reason."""
    _require_configured()

    storage_path = f"{company_id}/{uuid.uuid4()}-{filename}"
    client = await _client()
    bucket = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    await bucket.upload(storage_path, data, file_options={"content-type": content_type})
    public_url = await bucket.get_public_url(storage_path)

    return MediaAsset(
        id=uuid.uuid4(),
        company_id=company_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        storage_path=storage_path,
        public_url=public_url,
        tags=tags,
        uploaded_by=uploaded_by,
    )


async def delete_asset(asset: MediaAsset) -> None:
    """Removes the file from storage. The caller deletes the DB row
    separately (same "storage call, then persistence" split as upload)."""
    _require_configured()
    client = await _client()
    bucket = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    await bucket.remove([asset.storage_path])
