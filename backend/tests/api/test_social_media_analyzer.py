"""API tests for the Social Media Analyzer routes.

Same in-memory-SQLite + AsyncClient/ASGITransport pattern as the other API
test files. `initiate_connection`/`get_connection_status`/
`disconnect_connection` are monkey-patched so these tests never make a
real call to Composio.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.endpoints import social_media_analyzer as social_media_analyzer_module
from app.db.models import Company, PlatformConnection
from app.db.session import get_session


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    monkeypatch.setattr(
        social_media_analyzer_module.settings, "FRONTEND_BASE_URL", "http://localhost:3000"
    )

    app = FastAPI()
    app.include_router(social_media_analyzer_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _seed_company(test_session_factory, **overrides) -> uuid.UUID:
    company_id = uuid.uuid4()
    defaults = dict(
        id=company_id, url=f"https://example.com/{company_id}", status="complete", name="Acme"
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(Company(**defaults))
        await session.commit()
    return company_id


# --- List connections ----------------------------------------------------


async def test_list_connections_returns_all_known_platforms_as_disconnected(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)

    response = await client.get("/connections", params={"company_id": str(company_id)})

    assert response.status_code == 200
    body = response.json()
    platforms = {item["platform"] for item in body["items"]}
    assert platforms == {"instagram", "facebook", "twitter", "linkedin", "tiktok", "youtube"}
    assert all(item["status"] == "disconnected" for item in body["items"])
    assert all(item["id"] is None for item in body["items"])


async def test_list_connections_404s_for_unknown_company(client):
    response = await client.get("/connections", params={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_list_connections_includes_a_real_connected_row(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=uuid.uuid4(),
                company_id=company_id,
                platform="youtube",
                status="connected",
                external_account_name="Example Bakery",
            )
        )
        await session.commit()

    response = await client.get("/connections", params={"company_id": str(company_id)})

    body = response.json()
    youtube = next(item for item in body["items"] if item["platform"] == "youtube")
    assert youtube["status"] == "connected"
    assert youtube["external_account_name"] == "Example Bakery"
    assert youtube["id"] is not None


async def test_list_connections_refreshes_a_pending_connection(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="instagram",
                status="pending",
                composio_connected_account_id="ca_abc123",
            )
        )
        await session.commit()

    async def _fake_get_status(composio_connected_account_id):
        assert composio_connected_account_id == "ca_abc123"
        return "connected"

    monkeypatch.setattr(social_media_analyzer_module, "get_connection_status", _fake_get_status)

    response = await client.get("/connections", params={"company_id": str(company_id)})

    body = response.json()
    instagram = next(item for item in body["items"] if item["platform"] == "instagram")
    assert instagram["status"] == "connected"

    async with test_session_factory() as session:
        connection = await session.get(PlatformConnection, connection_id)
    assert connection.status == "connected"


async def test_list_connections_does_not_refresh_a_settled_connection(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=uuid.uuid4(),
                company_id=company_id,
                platform="instagram",
                status="connected",
                composio_connected_account_id="ca_abc123",
            )
        )
        await session.commit()

    async def _fail_if_called(composio_connected_account_id):
        raise AssertionError("should not check status for an already-settled connection")

    monkeypatch.setattr(social_media_analyzer_module, "get_connection_status", _fail_if_called)

    response = await client.get("/connections", params={"company_id": str(company_id)})

    assert response.status_code == 200


# --- Authorize -------------------------------------------------------------


async def test_authorize_409s_when_platform_not_configured(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.get(
        "/connections/instagram/authorize", params={"company_id": str(company_id)}
    )

    assert response.status_code == 409


async def test_authorize_404s_for_unknown_platform(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)

    response = await client.get(
        "/connections/myspace/authorize", params={"company_id": str(company_id)}
    )

    assert response.status_code == 404


async def test_authorize_redirects_to_composios_url_and_persists_pending_connection(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)

    async def _fake_initiate(platform, cid, callback_url):
        assert platform == "instagram"
        assert cid == company_id
        assert callback_url == f"http://localhost:3000/integrations/{company_id}"
        return "ca_abc123", "https://backend.composio.dev/auth/xyz"

    monkeypatch.setattr(social_media_analyzer_module, "initiate_connection", _fake_initiate)

    response = await client.get(
        "/connections/instagram/authorize",
        params={"company_id": str(company_id)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://backend.composio.dev/auth/xyz"

    async with test_session_factory() as session:
        connection = (
            await session.execute(
                select(PlatformConnection).where(
                    PlatformConnection.company_id == company_id,
                    PlatformConnection.platform == "instagram",
                )
            )
        ).scalar_one()
    assert connection.status == "pending"
    assert connection.composio_connected_account_id == "ca_abc123"


async def test_authorize_404s_for_unknown_company(client):
    response = await client.get(
        "/connections/instagram/authorize", params={"company_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


# --- Disconnect ----------------------------------------------------------


async def test_disconnect_clears_connection_and_marks_disconnected(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                composio_connected_account_id="ca_abc123",
                external_account_name="Example Channel",
            )
        )
        await session.commit()

    disconnected_ids = []

    async def _fake_disconnect(composio_connected_account_id):
        disconnected_ids.append(composio_connected_account_id)

    monkeypatch.setattr(social_media_analyzer_module, "disconnect_connection", _fake_disconnect)

    response = await client.delete(f"/connections/{connection_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert disconnected_ids == ["ca_abc123"]

    async with test_session_factory() as session:
        connection = await session.get(PlatformConnection, connection_id)
    assert connection.composio_connected_account_id is None
    assert connection.external_account_name is None


async def test_disconnect_404s_for_unknown_connection(client):
    response = await client.delete(f"/connections/{uuid.uuid4()}")
    assert response.status_code == 404


# --- Metrics ---------------------------------------------------------------


async def test_metrics_returns_empty_list_for_a_real_connection(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(id=connection_id, company_id=company_id, platform="youtube", status="connected")
        )
        await session.commit()

    response = await client.get(f"/connections/{connection_id}/metrics")

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_metrics_404s_for_unknown_connection(client):
    response = await client.get(f"/connections/{uuid.uuid4()}/metrics")
    assert response.status_code == 404
