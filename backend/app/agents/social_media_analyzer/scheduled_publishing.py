"""Scheduled publishing job — same recurring-job shape as the Trend
Analyzer's collection run and the Knowledge Base's re-index job
(`run_collection`, `run_scheduled_reindex`): registered in `main.py`'s
`lifespan` with `coalesce=True, max_instances=1`, per-item failures
isolated so one bad item doesn't abort the batch.

Deliberately conservative about *what* gets auto-published: only items
that are both scheduled (`scheduled_at <= now()`) AND already
`approval_status == "approved"` — a scheduled-but-not-yet-approved item
is never published automatically, so scheduling and approval stay two
independent, both-required gates rather than one implying the other.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.social_media_analyzer.publish import publish_post
from app.db.models import ContentItem, ContentPlan, PlatformConnection, PublishAttempt
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def _attempt_publish(item_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        if item is None or item.published_at is not None:
            return  # already published or vanished since the batch was listed

        content_plan = await session.get(ContentPlan, item.content_plan_id)
        company_id = content_plan.company_id if content_plan else None

        connection = None
        if company_id is not None:
            connection = (
                await session.execute(
                    select(PlatformConnection).where(
                        PlatformConnection.company_id == company_id,
                        PlatformConnection.platform == item.platform,
                        PlatformConnection.status == "connected",
                    )
                )
            ).scalar_one_or_none()

        if connection is None or connection.composio_connected_account_id is None:
            # Nothing valid to log a PublishAttempt against (no real
            # connection row to reference as the FK) — skip for now and
            # let the next scheduler run retry once a connection exists.
            # The item stays scheduled and unpublished, which is correct.
            logger.warning(
                "Skipping scheduled publish for item %s — no connected %s account",
                item.id,
                item.platform,
            )
            return

        try:
            execution_id = await publish_post(
                session, connection, item.draft_copy or "", media_url=item.media_url
            )
        except Exception as exc:
            logger.exception("Scheduled publish failed for item %s", item.id)
            session.add(
                PublishAttempt(
                    id=uuid.uuid4(),
                    content_item_id=item.id,
                    platform_connection_id=connection.id,
                    status="failed",
                    status_error=str(exc)[:512],
                )
            )
            await session.commit()
            return

        item.published_at = datetime.now(timezone.utc)
        session.add(
            PublishAttempt(
                id=uuid.uuid4(),
                content_item_id=item.id,
                platform_connection_id=connection.id,
                status="success",
                composio_execution_id=execution_id,
            )
        )
        await session.commit()


async def run_scheduled_publishing() -> None:
    """Finds every approved, scheduled, not-yet-published ContentItem
    whose `scheduled_at` has passed, and attempts to publish each —
    failures isolated per item, same pattern as every other scheduled
    batch job in this codebase."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        due_item_ids = (
            (
                await session.execute(
                    select(ContentItem.id).where(
                        ContentItem.scheduled_at.is_not(None),
                        ContentItem.scheduled_at <= now,
                        ContentItem.published_at.is_(None),
                        ContentItem.approval_status == "approved",
                    )
                )
            )
            .scalars()
            .all()
        )

    for item_id in due_item_ids:
        try:
            await _attempt_publish(item_id)
        except Exception:
            logger.exception("Unexpected error attempting scheduled publish for item %s", item_id)
