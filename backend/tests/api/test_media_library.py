"""API tests for the Media & Asset Library routes. `upload_asset`/
`delete_asset` (the real Supabase Storage calls) are monkey-patched so
these never make a real network call — same pattern as every other
Composio/Claude-dependent endpoint test in this codebase.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import media_library as media_library_module
from app.db.models import Company, MediaAsset
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_upload_asset(
        company_id, filename, content_type, data, *, tags=None, uploaded_by=None
    ):
        if filename == "trigger-not-configured":
            raise media_library_module.MediaLibraryNotConfiguredError("not configured")
        return MediaAsset(
            id=uuid.uuid4(),
            company_id=company_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_path=f"{company_id}/{filename}",
            public_url=f"https://fake.supabase.co/storage/v1/object/public/media-library/{company_id}/{filename}",
            tags=tags,
            uploaded_by=uploaded_by,
        )

    async def _fake_delete_asset(asset):
        if asset.filename == "trigger-not-configured-delete":
            raise media_library_module.MediaLibraryNotConfiguredError("not configured")

    monkeypatch.setattr(media_library_module, "upload_asset", _fake_upload_asset)
    monkeypatch.setattr(media_library_module, "delete_asset", _fake_delete_asset)

    app = FastAPI()
    app.include_router(media_library_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id,
        url=f"https://example.com/{company_id}",
        status="complete",
        name="Acme",
        owner_id="test-user-id",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


async def test_upload_media_asset_persists_and_returns_asset(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/{company_id}/assets",
        data={"tags": "hero, banner", "uploaded_by": "Priya"},
        files={"file": ("photo.png", b"fake image bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == str(company_id)
    assert body["filename"] == "photo.png"
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(b"fake image bytes")
    assert body["tags"] == ["hero", "banner"]
    assert body["uploaded_by"] == "Priya"
    assert body["public_url"] is not None

    listing = await client.get(f"/{company_id}/assets")
    assert len(listing.json()["items"]) == 1


async def test_upload_media_asset_404s_for_unknown_company(client):
    response = await client.post(
        f"/{uuid.uuid4()}/assets",
        files={"file": ("photo.png", b"data", "image/png")},
    )
    assert response.status_code == 404


async def test_upload_media_asset_413s_when_oversized(client, test_session_factory, monkeypatch):
    monkeypatch.setattr(media_library_module.settings, "MEDIA_UPLOAD_MAX_BYTES", 5)
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/{company_id}/assets",
        files={"file": ("photo.png", b"this is definitely over five bytes", "image/png")},
    )
    assert response.status_code == 413


async def test_upload_media_asset_409s_when_not_configured(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.post(
        f"/{company_id}/assets",
        files={"file": ("trigger-not-configured", b"data", "image/png")},
    )
    assert response.status_code == 409


async def test_list_media_assets_filters_by_tag(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    await client.post(
        f"/{company_id}/assets",
        data={"tags": "hero"},
        files={"file": ("hero.png", b"data", "image/png")},
    )
    await client.post(
        f"/{company_id}/assets",
        data={"tags": "banner"},
        files={"file": ("banner.png", b"data", "image/png")},
    )

    response = await client.get(f"/{company_id}/assets", params={"tag": "hero"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["filename"] == "hero.png"


async def test_delete_media_asset_removes_it(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    created = (
        await client.post(
            f"/{company_id}/assets", files={"file": ("photo.png", b"data", "image/png")}
        )
    ).json()

    response = await client.delete(f"/assets/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]

    listing = await client.get(f"/{company_id}/assets")
    assert listing.json()["items"] == []


async def test_delete_media_asset_404s_for_unknown_asset(client):
    response = await client.delete(f"/assets/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_media_asset_409s_when_not_configured(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    created = (
        await client.post(
            f"/{company_id}/assets",
            files={"file": ("trigger-not-configured-delete", b"data", "image/png")},
        )
    ).json()

    response = await client.delete(f"/assets/{created['id']}")
    assert response.status_code == 409
