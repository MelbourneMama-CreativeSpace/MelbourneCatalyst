"""Tests for the scheduled publishing job."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.agents.social_media_analyzer import scheduled_publishing as scheduled_module
from app.db.models import Company, ContentItem, ContentPlan, PlatformConnection, PublishAttempt


async def _seed_item(
    test_session_factory,
    *,
    scheduled_at=None,
    published_at=None,
    approval_status="approved",
    platform="linkedin",
    with_connection=False,
    connection_status="connected",
) -> uuid.UUID:
    company_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    item_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(id=company_id, url=f"https://example.com/{company_id}", status="complete")
        )
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete"))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Item",
                description="d",
                content_type="post",
                platform=platform,
                suggested_date=date.today(),
                draft_copy="Ready to publish.",
                approval_status=approval_status,
                scheduled_at=scheduled_at,
                published_at=published_at,
            )
        )
        if with_connection:
            session.add(
                PlatformConnection(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    platform=platform,
                    status=connection_status,
                    composio_connected_account_id="conn-abc123",
                )
            )
        await session.commit()
    return item_id


async def test_skips_items_not_yet_due(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    item_id = await _seed_item(test_session_factory, scheduled_at=future, with_connection=True)

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        item = await session.get(ContentItem, item_id)
    assert item.published_at is None


async def test_skips_unapproved_items(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    item_id = await _seed_item(
        test_session_factory, scheduled_at=past, approval_status="pending", with_connection=True
    )

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        item = await session.get(ContentItem, item_id)
    assert item.published_at is None


async def test_skips_when_no_connected_account(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    item_id = await _seed_item(test_session_factory, scheduled_at=past, with_connection=False)

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        attempts = (
            (
                await session.execute(
                    select(PublishAttempt).where(PublishAttempt.content_item_id == item_id)
                )
            )
            .scalars()
            .all()
        )
    assert item.published_at is None
    assert attempts == []  # no valid connection to reference as the FK


async def test_publishes_and_logs_success(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    item_id = await _seed_item(test_session_factory, scheduled_at=past, with_connection=True)

    async def _fake_publish_post(platform, connected_account_id, text):
        assert platform == "linkedin"
        assert connected_account_id == "conn-abc123"
        assert text == "Ready to publish."
        return "exec-xyz"

    monkeypatch.setattr(scheduled_module, "publish_post", _fake_publish_post)

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        attempts = (
            (
                await session.execute(
                    select(PublishAttempt).where(PublishAttempt.content_item_id == item_id)
                )
            )
            .scalars()
            .all()
        )
    assert item.published_at is not None
    assert len(attempts) == 1
    assert attempts[0].status == "success"
    assert attempts[0].composio_execution_id == "exec-xyz"


async def test_logs_failure_and_leaves_item_unpublished(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    item_id = await _seed_item(test_session_factory, scheduled_at=past, with_connection=True)

    async def _failing_publish_post(platform, connected_account_id, text):
        raise RuntimeError("Composio: rate limited")

    monkeypatch.setattr(scheduled_module, "publish_post", _failing_publish_post)

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        attempts = (
            (
                await session.execute(
                    select(PublishAttempt).where(PublishAttempt.content_item_id == item_id)
                )
            )
            .scalars()
            .all()
        )
    assert item.published_at is None
    assert len(attempts) == 1
    assert attempts[0].status == "failed"
    assert "rate limited" in attempts[0].status_error


async def test_one_item_failure_does_not_block_another(monkeypatch, test_session_factory):
    monkeypatch.setattr(scheduled_module, "async_session_factory", test_session_factory)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    failing_id = await _seed_item(test_session_factory, scheduled_at=past, with_connection=True)
    ok_id = await _seed_item(test_session_factory, scheduled_at=past, with_connection=True)

    async def _flaky_publish_post(platform, connected_account_id, text):
        # Fail the first call, succeed on the second — order isn't
        # guaranteed, so key off call count rather than item identity.
        _flaky_publish_post.calls += 1
        if _flaky_publish_post.calls == 1:
            raise RuntimeError("boom")
        return "exec-ok"

    _flaky_publish_post.calls = 0
    monkeypatch.setattr(scheduled_module, "publish_post", _flaky_publish_post)

    await scheduled_module.run_scheduled_publishing()

    async with test_session_factory() as session:
        failing_item = await session.get(ContentItem, failing_id)
        ok_item = await session.get(ContentItem, ok_id)
    # Exactly one succeeded and one failed — isolation confirmed either way.
    published = [failing_item.published_at is not None, ok_item.published_at is not None]
    assert published.count(True) == 1
    assert published.count(False) == 1
