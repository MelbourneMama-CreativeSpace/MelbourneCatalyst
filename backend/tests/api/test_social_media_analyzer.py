"""API tests for the Social Media Analyzer routes.

Same in-memory-SQLite + AsyncClient/ASGITransport pattern as the other
API test files. `exchange_code_for_token` is monkey-patched for the
callback tests so they don't make a real HTTP call to any platform.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.agents.social_media_analyzer.oauth_flow import TokenResult
from app.api.v1.endpoints import social_media_analyzer as social_media_analyzer_module
from app.db.models import Company, PlatformConnection
from app.db.session import get_session
from app.security import oauth_state


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(social_media_analyzer_module.settings, "TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setattr(oauth_state.settings, "TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setattr(social_media_analyzer_module.settings, "FRONTEND_BASE_URL", "http://localhost:3000")

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


async def test_authorize_redirects_when_platform_is_configured(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    monkeypatch.setattr(social_media_analyzer_module.settings, "META_APP_CLIENT_ID", "test-id")
    monkeypatch.setattr(social_media_analyzer_module.settings, "META_APP_CLIENT_SECRET", "test-secret")

    response = await client.get(
        "/connections/instagram/authorize",
        params={"company_id": str(company_id)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "facebook.com" in response.headers["location"]


async def test_authorize_404s_for_unknown_company(client):
    response = await client.get(
        "/connections/instagram/authorize", params={"company_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


# --- Callback ----------------------------------------------------------


async def test_callback_redirects_with_error_param_untouched(client):
    response = await client.get(
        "/connections/instagram/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "connect_error=access_denied" in response.headers["location"]


async def test_callback_400s_when_missing_code_or_state(client):
    response = await client.get("/connections/instagram/callback")
    assert response.status_code == 400


async def test_callback_persists_a_connected_row(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)
    state = oauth_state.sign_state({"company_id": str(company_id), "platform": "instagram"})

    async def _fake_exchange(platform, code, state_token):
        return (
            TokenResult(
                access_token="real-access-token",
                refresh_token="real-refresh-token",
                expires_in=3600,
                granted_scopes="instagram_basic",
            ),
            {"company_id": str(company_id), "platform": "instagram"},
        )

    monkeypatch.setattr(social_media_analyzer_module, "exchange_code_for_token", _fake_exchange)

    response = await client.get(
        "/connections/instagram/callback",
        params={"code": "some-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"http://localhost:3000/companies/{company_id}"

    async with test_session_factory() as session:
        connection = (
            await session.execute(
                select(PlatformConnection).where(
                    PlatformConnection.company_id == company_id,
                    PlatformConnection.platform == "instagram",
                )
            )
        ).scalar_one()

    assert connection.status == "connected"
    assert connection.access_token_encrypted != "real-access-token"  # actually encrypted
    assert connection.scopes == "instagram_basic"


# --- Disconnect ----------------------------------------------------------


async def test_disconnect_clears_tokens_and_marks_disconnected(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform="youtube",
                status="connected",
                access_token_encrypted="ciphertext",
            )
        )
        await session.commit()

    response = await client.delete(f"/connections/{connection_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"

    async with test_session_factory() as session:
        connection = await session.get(PlatformConnection, connection_id)
    assert connection.access_token_encrypted is None


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
