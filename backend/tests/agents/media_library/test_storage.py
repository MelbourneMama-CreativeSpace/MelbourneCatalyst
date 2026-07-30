"""Tests for the Supabase Storage wrapper (Media & Asset Library)."""

from __future__ import annotations

import uuid

import pytest

from app.agents.media_library import storage as storage_module
from app.db.models import MediaAsset


def test_is_media_library_configured_false_by_default(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "")
    assert storage_module.is_media_library_configured() is False


def test_is_media_library_configured_true_when_both_set(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    assert storage_module.is_media_library_configured() is True


async def test_upload_asset_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "")

    with pytest.raises(storage_module.MediaLibraryNotConfiguredError):
        await storage_module.upload_asset(uuid.uuid4(), "photo.png", "image/png", b"data")


async def test_delete_asset_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "")

    asset = MediaAsset(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        filename="photo.png",
        content_type="image/png",
        size_bytes=4,
        storage_path="c/photo.png",
    )
    with pytest.raises(storage_module.MediaLibraryNotConfiguredError):
        await storage_module.delete_asset(asset)


class _FakeBucket:
    def __init__(self):
        self.uploaded = []
        self.removed = []

    async def upload(self, path, data, file_options=None):
        self.uploaded.append((path, data, file_options))
        return {"path": path}

    async def get_public_url(self, path, options=None):
        return f"https://fake.supabase.co/storage/v1/object/public/media-library/{path}"

    async def remove(self, paths):
        self.removed.extend(paths)
        return [{"name": p} for p in paths]


class _FakeStorageClient:
    def __init__(self, bucket):
        self._bucket = bucket

    def from_(self, bucket_name):
        return self._bucket


class _FakeClient:
    def __init__(self, bucket):
        self.storage = _FakeStorageClient(bucket)


async def test_upload_asset_succeeds_with_mocked_client(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_STORAGE_BUCKET", "media-library")

    bucket = _FakeBucket()
    monkeypatch.setattr(storage_module, "_client", lambda: _fake_async(_FakeClient(bucket)))

    company_id = uuid.uuid4()
    asset = await storage_module.upload_asset(
        company_id, "photo.png", "image/png", b"real bytes", tags=["hero"], uploaded_by="Priya"
    )

    assert asset.company_id == company_id
    assert asset.filename == "photo.png"
    assert asset.size_bytes == len(b"real bytes")
    assert asset.tags == ["hero"]
    assert asset.uploaded_by == "Priya"
    assert asset.public_url.endswith(asset.storage_path)
    assert len(bucket.uploaded) == 1
    assert bucket.uploaded[0][2] == {"content-type": "image/png"}


async def test_delete_asset_succeeds_with_mocked_client(monkeypatch):
    monkeypatch.setattr(storage_module.settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(storage_module.settings, "SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    bucket = _FakeBucket()
    monkeypatch.setattr(storage_module, "_client", lambda: _fake_async(_FakeClient(bucket)))

    asset = MediaAsset(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        filename="photo.png",
        content_type="image/png",
        size_bytes=4,
        storage_path="c/photo.png",
    )
    await storage_module.delete_asset(asset)

    assert bucket.removed == ["c/photo.png"]


async def _fake_async(value):
    return value
