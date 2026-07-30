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
from app.security.auth import CurrentUser, get_current_user


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
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

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


async def test_sync_metrics_persists_a_new_snapshot(client, test_session_factory, monkeypatch):
    from app.db.models import PlatformMetricSnapshot

    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id, "youtube")

    async def _fake_fetch(connection_id_arg, platform, connected_account_id):
        assert platform == "youtube"
        assert connected_account_id == "conn-real-123"
        from datetime import datetime, timezone

        return PlatformMetricSnapshot(
            id=uuid.uuid4(),
            platform_connection_id=connection_id_arg,
            captured_at=datetime.now(timezone.utc),
            follower_count=500,
            engagement_rate=0.03,
            raw_metadata={"follower_count": 500, "engagement_rate": 0.03},
        )

    monkeypatch.setattr(social_media_analyzer_module, "fetch_platform_metrics", _fake_fetch)

    response = await client.post(f"/connections/{connection_id}/sync-metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["follower_count"] == 500
    assert body["engagement_rate"] == 0.03

    listing = await client.get(f"/connections/{connection_id}/metrics")
    assert len(listing.json()["items"]) == 1


async def test_sync_metrics_404s_for_unknown_connection(client):
    response = await client.post(f"/connections/{uuid.uuid4()}/sync-metrics")
    assert response.status_code == 404


async def test_sync_metrics_409s_when_platform_not_connected(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id, company_id=company_id, platform="youtube", status="disconnected"
            )
        )
        await session.commit()

    response = await client.post(f"/connections/{connection_id}/sync-metrics")
    assert response.status_code == 409


async def test_sync_metrics_409s_when_not_configured(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id, "youtube")

    async def _fake_fetch_not_configured(connection_id_arg, platform, connected_account_id):
        raise social_media_analyzer_module.MetricsNotConfiguredError("not configured")

    monkeypatch.setattr(
        social_media_analyzer_module, "fetch_platform_metrics", _fake_fetch_not_configured
    )

    response = await client.post(f"/connections/{connection_id}/sync-metrics")
    assert response.status_code == 409


async def test_sync_metrics_502s_on_real_composio_failure(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id, "youtube")

    async def _failing_fetch(connection_id_arg, platform, connected_account_id):
        raise RuntimeError("Composio: rate limited")

    monkeypatch.setattr(social_media_analyzer_module, "fetch_platform_metrics", _failing_fetch)

    response = await client.post(f"/connections/{connection_id}/sync-metrics")
    assert response.status_code == 502


# --- Publish -----------------------------------------------------------


async def _seed_connected_platform(
    test_session_factory, company_id: uuid.UUID, platform: str = "linkedin"
) -> uuid.UUID:
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id,
                company_id=company_id,
                platform=platform,
                status="connected",
                composio_connected_account_id="conn-real-123",
            )
        )
        await session.commit()
    return connection_id


async def _seed_content_item(
    test_session_factory, company_id: uuid.UUID, platform: str = "linkedin", **overrides
) -> uuid.UUID:
    from datetime import date

    from app.db.models import ContentItem, ContentPlan

    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    defaults = dict(
        id=item_id,
        content_plan_id=plan_id,
        title="Item",
        description="d",
        content_type="post",
        platform=platform,
        suggested_date=date.today(),
        draft_copy="Ready to publish.",
    )
    defaults.update(overrides)
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(ContentItem(**defaults))
        await session.commit()
    return item_id


async def test_publish_now_succeeds(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id)
    item_id = await _seed_content_item(test_session_factory, company_id)

    async def _fake_publish_post(platform, connected_account_id, text):
        assert platform == "linkedin"
        assert connected_account_id == "conn-real-123"
        return "exec-live-1"

    monkeypatch.setattr(social_media_analyzer_module, "publish_post", _fake_publish_post)

    response = await client.post(
        f"/connections/{connection_id}/publish", json={"content_item_id": str(item_id)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["published_at"] is not None


async def test_publish_now_returns_failed_status_on_composio_error(
    client, test_session_factory, monkeypatch
):
    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id)
    item_id = await _seed_content_item(test_session_factory, company_id)

    async def _failing_publish_post(platform, connected_account_id, text):
        raise RuntimeError("Composio: not configured")

    monkeypatch.setattr(social_media_analyzer_module, "publish_post", _failing_publish_post)

    response = await client.post(
        f"/connections/{connection_id}/publish", json={"content_item_id": str(item_id)}
    )

    assert response.status_code == 200  # a real publish failure, not a server error
    body = response.json()
    assert body["status"] == "failed"
    assert "not configured" in body["status_error"]


async def test_publish_now_404s_for_unknown_connection(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    item_id = await _seed_content_item(test_session_factory, company_id)

    response = await client.post(
        f"/connections/{uuid.uuid4()}/publish", json={"content_item_id": str(item_id)}
    )
    assert response.status_code == 404


async def test_publish_now_409s_when_platform_not_connected(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    connection_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PlatformConnection(
                id=connection_id, company_id=company_id, platform="linkedin", status="disconnected"
            )
        )
        await session.commit()
    item_id = await _seed_content_item(test_session_factory, company_id)

    response = await client.post(
        f"/connections/{connection_id}/publish", json={"content_item_id": str(item_id)}
    )
    assert response.status_code == 409


# --- Publish attempts monitor --------------------------------------------


async def _seed_publish_attempt(
    test_session_factory,
    company_id: uuid.UUID,
    *,
    status: str = "failed",
    platform: str = "linkedin",
    status_error: str | None = "Composio: rate limited",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    from app.db.models import PublishAttempt

    connection_id = await _seed_connected_platform(test_session_factory, company_id, platform)
    item_id = await _seed_content_item(test_session_factory, company_id, platform=platform)
    attempt_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PublishAttempt(
                id=attempt_id,
                content_item_id=item_id,
                platform_connection_id=connection_id,
                status=status,
                status_error=status_error if status == "failed" else None,
                composio_execution_id="exec-1" if status == "success" else None,
            )
        )
        await session.commit()
    return attempt_id, connection_id, item_id


async def test_list_publish_attempts_returns_joined_data(client, test_session_factory):
    company_id = await _seed_company(test_session_factory)
    attempt_id, connection_id, item_id = await _seed_publish_attempt(
        test_session_factory, company_id
    )

    response = await client.get("/publish-attempts")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == str(attempt_id)
    assert row["content_item_id"] == str(item_id)
    assert row["platform_connection_id"] == str(connection_id)
    assert row["platform"] == "linkedin"
    assert row["company_id"] == str(company_id)
    assert row["company_name"] == "Acme"
    assert row["status"] == "failed"
    assert row["status_error"] == "Composio: rate limited"


async def test_list_publish_attempts_filters_by_company_status_and_platform(
    client, test_session_factory
):
    company_a = await _seed_company(test_session_factory)
    company_b = await _seed_company(test_session_factory)
    await _seed_publish_attempt(test_session_factory, company_a, status="failed", platform="linkedin")
    await _seed_publish_attempt(test_session_factory, company_a, status="success", platform="instagram")
    await _seed_publish_attempt(test_session_factory, company_b, status="failed", platform="linkedin")

    response = await client.get(
        "/publish-attempts",
        params={"company_id": str(company_a), "status": "failed", "platform": "linkedin"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["company_id"] == str(company_a)
    assert items[0]["status"] == "failed"
    assert items[0]["platform"] == "linkedin"


async def test_retry_publish_attempt_succeeds(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)
    attempt_id, connection_id, item_id = await _seed_publish_attempt(
        test_session_factory, company_id
    )

    async def _fake_publish_post(platform, connected_account_id, text):
        return "exec-retry-1"

    monkeypatch.setattr(social_media_analyzer_module, "publish_post", _fake_publish_post)

    response = await client.post(f"/publish-attempts/{attempt_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["published_at"] is not None

    # A retry logs a NEW attempt row, doesn't mutate the old failed one.
    list_response = await client.get("/publish-attempts", params={"company_id": str(company_id)})
    statuses = sorted(item["status"] for item in list_response.json()["items"])
    assert statuses == ["failed", "success"]


async def test_retry_publish_attempt_404s_for_unknown_attempt(client):
    response = await client.post(f"/publish-attempts/{uuid.uuid4()}/retry")
    assert response.status_code == 404


async def test_retry_publish_attempt_409s_when_attempt_was_not_failed(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)
    attempt_id, _, _ = await _seed_publish_attempt(test_session_factory, company_id, status="success")

    response = await client.post(f"/publish-attempts/{attempt_id}/retry")
    assert response.status_code == 409


async def test_retry_publish_attempt_409s_when_item_already_published(
    client, test_session_factory
):
    from datetime import datetime, timezone

    from app.db.models import PublishAttempt

    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id)
    item_id = await _seed_content_item(
        test_session_factory, company_id, published_at=datetime.now(timezone.utc)
    )
    attempt_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            PublishAttempt(
                id=attempt_id,
                content_item_id=item_id,
                platform_connection_id=connection_id,
                status="failed",
                status_error="stale error",
            )
        )
        await session.commit()

    response = await client.post(f"/publish-attempts/{attempt_id}/retry")
    assert response.status_code == 409


async def test_publish_now_400s_when_item_platform_mismatches_connection(
    client, test_session_factory
):
    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id, "linkedin")
    item_id = await _seed_content_item(test_session_factory, company_id, platform="instagram")

    response = await client.post(
        f"/connections/{connection_id}/publish", json={"content_item_id": str(item_id)}
    )
    assert response.status_code == 400


async def test_publish_now_409s_when_already_published(client, test_session_factory):
    from datetime import datetime, timezone

    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id)
    item_id = await _seed_content_item(
        test_session_factory, company_id, published_at=datetime.now(timezone.utc)
    )

    response = await client.post(
        f"/connections/{connection_id}/publish", json={"content_item_id": str(item_id)}
    )
    assert response.status_code == 409


# --- Insights ------------------------------------------------------------


async def test_insights_404s_for_unknown_company(client):
    response = await client.post("/insights", params={"company_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_insights_502s_on_generation_failure(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)

    async def _failing_generate(context):
        return None, False

    monkeypatch.setattr(social_media_analyzer_module, "generate_performance_insights", _failing_generate)

    response = await client.post("/insights", params={"company_id": str(company_id)})
    assert response.status_code == 502


async def test_insights_context_reflects_no_data_yet(client, test_session_factory, monkeypatch):
    company_id = await _seed_company(test_session_factory)

    captured = {}

    async def _fake_generate(context):
        captured["context"] = context
        return "not enough data yet", True

    monkeypatch.setattr(social_media_analyzer_module, "generate_performance_insights", _fake_generate)

    response = await client.post("/insights", params={"company_id": str(company_id)})

    assert response.status_code == 200
    assert response.json()["insights"] == "not enough data yet"
    assert "No metric snapshots exist yet" in captured["context"]
    assert "No published content exists yet" in captured["context"]


async def test_insights_context_includes_real_snapshots_and_published_content(
    client, test_session_factory, monkeypatch
):
    from datetime import datetime, timezone

    from app.db.models import PlatformMetricSnapshot

    company_id = await _seed_company(test_session_factory)
    connection_id = await _seed_connected_platform(test_session_factory, company_id, "linkedin")
    await _seed_content_item(
        test_session_factory,
        company_id,
        platform="linkedin",
        title="Real published post",
        published_at=datetime.now(timezone.utc),
    )
    async with test_session_factory() as session:
        session.add(
            PlatformMetricSnapshot(
                id=uuid.uuid4(),
                platform_connection_id=connection_id,
                captured_at=datetime.now(timezone.utc),
                follower_count=850,
                engagement_rate=0.021,
                raw_metadata={},
            )
        )
        await session.commit()

    captured = {}

    async def _fake_generate(context):
        captured["context"] = context
        return "Real insights.", True

    monkeypatch.setattr(social_media_analyzer_module, "generate_performance_insights", _fake_generate)

    response = await client.post("/insights", params={"company_id": str(company_id)})

    assert response.status_code == 200
    assert "850 followers" in captured["context"]
    assert "2.1% engagement" in captured["context"]
    assert "Real published post" in captured["context"]
