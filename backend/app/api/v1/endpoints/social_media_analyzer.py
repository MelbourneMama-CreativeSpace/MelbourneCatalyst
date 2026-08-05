"""Social Media Analyzer routes: Platform Integration Agent's "connect
your account" flow, brokered through Composio rather than this app doing
raw OAuth itself.

Flow: `GET /connections/{platform}/authorize` starts a Composio
connection and redirects the browser to Composio's own hosted authorize
URL, which in turn sends the user to the real platform's consent screen.
Once done, Composio redirects the browser straight to the `callback_url`
we gave it (this app's `/integrations/{company_id}` frontend page) — our
backend has no callback route of its own to hit anymore, since Composio
is the registered OAuth redirect target on each platform's app, not us.
`GET /connections` lazily refreshes any connection still mid-flow so the
status is current by the time the user lands back on that page.

Metrics endpoint is schema-complete but returns nothing yet — no
metrics-fetching logic exists this round (see
`app/agents/social_media_analyzer/__init__.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.social_media_analyzer.oauth_flow import (
    ComposioNotConfiguredError,
    disconnect_connection,
    get_connection_status,
    initiate_connection,
)
from app.agents.social_media_analyzer.insights import generate_performance_insights
from app.agents.social_media_analyzer.metrics import MetricsNotConfiguredError, fetch_platform_metrics
from app.agents.social_media_analyzer.oauth_providers import PLATFORM_CONFIGS
from app.agents.social_media_analyzer.publish import publish_post
from app.config import settings
from app.db.models import (
    Company,
    ContentItem,
    ContentPlan,
    PlatformConnection,
    PlatformMetricSnapshot,
    PublishAttempt,
)
from app.db.session import get_session
from app.models.social_media import (
    PerformanceInsightsOut,
    PlatformConnectionListResponse,
    PlatformConnectionOut,
    PlatformMetricSnapshotListResponse,
    PlatformMetricSnapshotOut,
    PublishAttemptListResponse,
    PublishAttemptOut,
    PublishRequest,
    PublishResultOut,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import get_owned_company, owned_company_ids

# `get_current_user` accepts the session via an `access_token` query
# param as a fallback to the Authorization header — needed here
# specifically because /connections/{platform}/authorize is a plain
# `<a href>` browser navigation, which can't carry a custom header.
router = APIRouter(dependencies=[Depends(get_current_user)])

# Connections in one of these statuses haven't reached a settled state
# yet — worth checking Composio for a fresher status before returning them.
_UNSETTLED_STATUSES = {"pending"}


async def _get_company_or_404(
    session: AsyncSession, company_id: uuid.UUID, current_user: CurrentUser
) -> Company:
    return await get_owned_company(session, company_id, current_user)


async def _get_owned_connection(
    session: AsyncSession, connection_id: uuid.UUID, current_user: CurrentUser
) -> PlatformConnection:
    connection = await session.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    await get_owned_company(session, connection.company_id, current_user)
    return connection


async def _refresh_unsettled(session: AsyncSession, rows: list[PlatformConnection]) -> None:
    changed_rows = []
    for row in rows:
        if row.status not in _UNSETTLED_STATUSES or not row.composio_connected_account_id:
            continue
        fresh_status = await get_connection_status(row.composio_connected_account_id)
        if fresh_status != row.status:
            row.status = fresh_status
            changed_rows.append(row)
    if changed_rows:
        await session.commit()
        # updated_at has onupdate=func.now() — its real post-commit value
        # is unknown to these in-memory objects until refreshed, same fix
        # as content_management.py's update_campaign_lifecycle.
        for row in changed_rows:
            await session.refresh(row)


@router.get("/connections", response_model=PlatformConnectionListResponse)
async def list_connections(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlatformConnectionListResponse:
    """Always returns one row per known platform, even for platforms this
    company has never attempted to connect — unconnected platforms are
    synthesized as `status: "disconnected"` placeholders, not persisted,
    so the frontend has a stable list to render Connect buttons for."""
    await _get_company_or_404(session, company_id, current_user)

    rows = (
        await session.execute(
            select(PlatformConnection).where(PlatformConnection.company_id == company_id)
        )
    ).scalars().all()
    await _refresh_unsettled(session, list(rows))
    by_platform = {row.platform: row for row in rows}

    items = [
        PlatformConnectionOut.model_validate(by_platform[platform])
        if platform in by_platform
        else PlatformConnectionOut(company_id=company_id, platform=platform, status="disconnected")
        for platform in PLATFORM_CONFIGS
    ]
    return PlatformConnectionListResponse(items=items)


@router.get("/connections/{platform}/authorize")
async def authorize(
    platform: str,
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RedirectResponse:
    await _get_company_or_404(session, company_id, current_user)
    if platform not in PLATFORM_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform!r}")

    callback_url = f"{settings.FRONTEND_BASE_URL}/integrations/{company_id}"
    try:
        composio_connected_account_id, redirect_url = await initiate_connection(
            platform, company_id, callback_url
        )
    except ComposioNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    connection = (
        await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.company_id == company_id, PlatformConnection.platform == platform
            )
        )
    ).scalar_one_or_none()
    if connection is None:
        connection = PlatformConnection(id=uuid.uuid4(), company_id=company_id, platform=platform)
        session.add(connection)

    connection.composio_connected_account_id = composio_connected_account_id
    connection.status = "pending"
    connection.status_error = None
    await session.commit()

    return RedirectResponse(redirect_url, status_code=302)


@router.delete("/connections/{connection_id}", response_model=PlatformConnectionOut)
async def disconnect(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlatformConnectionOut:
    connection = await _get_owned_connection(session, connection_id, current_user)

    if connection.composio_connected_account_id:
        await disconnect_connection(connection.composio_connected_account_id)

    connection.composio_connected_account_id = None
    connection.external_account_id = None
    connection.external_account_name = None
    connection.scopes = None
    connection.status = "disconnected"
    connection.status_error = None
    connection.connected_at = None
    await session.commit()
    # updated_at has onupdate=func.now() — its real post-commit value is
    # unknown to this in-memory object until refreshed, regardless of
    # expire_on_commit=False (that only covers attributes with no
    # server-computed value). Same fix as content_management.py's
    # update_campaign_lifecycle.
    await session.refresh(connection)
    return PlatformConnectionOut.model_validate(connection)


@router.get("/connections/{connection_id}/metrics", response_model=PlatformMetricSnapshotListResponse)
async def get_metrics(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlatformMetricSnapshotListResponse:
    await _get_owned_connection(session, connection_id, current_user)

    rows = (
        await session.execute(
            select(PlatformMetricSnapshot)
            .where(PlatformMetricSnapshot.platform_connection_id == connection_id)
            .order_by(PlatformMetricSnapshot.captured_at.desc())
        )
    ).scalars().all()
    return PlatformMetricSnapshotListResponse(items=list(rows))


@router.post("/connections/{connection_id}/sync-metrics", response_model=PlatformMetricSnapshotOut)
async def sync_metrics(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlatformMetricSnapshotOut:
    """Manually triggers a metrics fetch for one connection — the same
    call the scheduled job (`run_scheduled_metrics_sync`) makes
    automatically every `METRICS_SYNC_INTERVAL_MINUTES`."""
    connection = await _get_owned_connection(session, connection_id, current_user)
    if connection.status != "connected" or connection.composio_connected_account_id is None:
        raise HTTPException(status_code=409, detail="This platform isn't connected yet.")

    try:
        snapshot = await fetch_platform_metrics(
            connection.id, connection.platform, connection.composio_connected_account_id
        )
    except MetricsNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:512])

    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return PlatformMetricSnapshotOut.model_validate(snapshot)


async def _publish_and_log(
    session: AsyncSession, item: ContentItem, connection: PlatformConnection
) -> PublishResultOut:
    """Shared by an immediate publish and a retry of a failed attempt —
    always logs a new `PublishAttempt` row (never mutates an existing
    one, consistent with `PublishAttempt`'s "log entry per attempt"
    design) and returns the real error on failure rather than raising a
    5xx, since a real Composio/platform-side failure (rate limit, expired
    token, a genuinely wrong post_tool_slug) is exactly the detail the
    caller needs to show the user."""
    try:
        execution_id = await publish_post(
            connection.platform, connection.composio_connected_account_id, item.draft_copy or ""
        )
    except Exception as exc:
        error_message = str(exc)[:512]
        session.add(
            PublishAttempt(
                id=uuid.uuid4(),
                content_item_id=item.id,
                platform_connection_id=connection.id,
                status="failed",
                status_error=error_message,
            )
        )
        await session.commit()
        return PublishResultOut(
            content_item_id=item.id, status="failed", status_error=error_message
        )

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
    return PublishResultOut(
        content_item_id=item.id, status="success", published_at=item.published_at
    )


async def _get_owned_item_company_id(
    session: AsyncSession, item: ContentItem, current_user: CurrentUser
) -> uuid.UUID:
    """Resolves and authorizes the company a ContentItem belongs to via
    its ContentPlan — used to cross-check against a connection's own
    company below (KNOWN_ISSUES.md C1: nothing previously stopped
    publishing one client's content to a different client's connected
    account, as long as the platform matched)."""
    content_plan = await session.get(ContentPlan, item.content_plan_id)
    if content_plan is None:
        raise HTTPException(status_code=404, detail="Content plan for this item not found")
    await get_owned_company(session, content_plan.company_id, current_user)
    return content_plan.company_id


@router.post("/connections/{connection_id}/publish", response_model=PublishResultOut)
async def publish_now(
    connection_id: uuid.UUID,
    payload: PublishRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishResultOut:
    """Publish one ContentItem to one connected platform immediately — the
    Draft Workspace's "Publish now" action."""
    connection = await _get_owned_connection(session, connection_id, current_user)
    if connection.status != "connected" or connection.composio_connected_account_id is None:
        raise HTTPException(status_code=409, detail="This platform isn't connected yet.")

    item = await session.get(ContentItem, payload.content_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    item_company_id = await _get_owned_item_company_id(session, item, current_user)
    if item_company_id != connection.company_id:
        raise HTTPException(
            status_code=409, detail="This content item does not belong to this platform connection's company."
        )
    if item.platform != connection.platform:
        raise HTTPException(
            status_code=400,
            detail=f"This item is for {item.platform}, not {connection.platform}.",
        )
    if item.published_at is not None:
        raise HTTPException(status_code=409, detail="This item has already been published.")

    return await _publish_and_log(session, item, connection)


@router.get("/publish-attempts", response_model=PublishAttemptListResponse)
async def list_publish_attempts(
    company_id: uuid.UUID | None = None,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishAttemptListResponse:
    """The Social Publishing Monitor — a history of this app's own publish
    attempts (not live platform engagement data, see
    `PlatformMetricSnapshot`/the metrics endpoints for that). Needs no
    Composio credentials to be useful: it's monitoring what this app
    itself already did, successfully or not."""
    if company_id is not None:
        await get_owned_company(session, company_id, current_user)
        owned_ids: list[uuid.UUID] = [company_id]
    else:
        owned_ids = await owned_company_ids(session, current_user)

    stmt = (
        select(PublishAttempt, PlatformConnection, ContentItem, Company)
        .join(PlatformConnection, PublishAttempt.platform_connection_id == PlatformConnection.id)
        .join(ContentItem, PublishAttempt.content_item_id == ContentItem.id)
        .join(Company, PlatformConnection.company_id == Company.id)
        .where(PlatformConnection.company_id.in_(owned_ids))
        .order_by(PublishAttempt.attempted_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(PublishAttempt.status == status)
    if platform is not None:
        stmt = stmt.where(PlatformConnection.platform == platform)

    rows = (await session.execute(stmt)).all()
    items = [
        PublishAttemptOut(
            id=attempt.id,
            content_item_id=item.id,
            content_item_title=item.title,
            platform_connection_id=connection.id,
            platform=connection.platform,
            company_id=company.id,
            company_name=company.name,
            status=attempt.status,
            status_error=attempt.status_error,
            composio_execution_id=attempt.composio_execution_id,
            attempted_at=attempt.attempted_at,
        )
        for attempt, connection, item, company in rows
    ]
    return PublishAttemptListResponse(items=items)


@router.post("/publish-attempts/{attempt_id}/retry", response_model=PublishResultOut)
async def retry_publish_attempt(
    attempt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishResultOut:
    attempt = await session.get(PublishAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Publish attempt not found")
    if attempt.status != "failed":
        raise HTTPException(status_code=409, detail="Only a failed attempt can be retried")

    connection = await _get_owned_connection(session, attempt.platform_connection_id, current_user)
    if connection.status != "connected" or connection.composio_connected_account_id is None:
        raise HTTPException(status_code=409, detail="This platform isn't connected yet.")

    item = await session.get(ContentItem, attempt.content_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    item_company_id = await _get_owned_item_company_id(session, item, current_user)
    if item_company_id != connection.company_id:
        raise HTTPException(
            status_code=409, detail="This content item does not belong to this platform connection's company."
        )
    if item.published_at is not None:
        raise HTTPException(status_code=409, detail="This item has already been published.")

    return await _publish_and_log(session, item, connection)


@router.post("/insights", response_model=PerformanceInsightsOut)
async def get_performance_insights(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> PerformanceInsightsOut:
    """One Claude call over the company's own real stored data — recent
    metric snapshots (see `metrics.py`) and recently published content.
    Never fabricates: explicitly asks Claude to say plainly when there
    isn't enough data yet, which is the honest answer until #18's metrics
    sync actually has real snapshots to work with."""
    company = await _get_company_or_404(session, company_id, current_user)

    snapshot_rows = (
        await session.execute(
            select(PlatformMetricSnapshot, PlatformConnection.platform)
            .join(
                PlatformConnection,
                PlatformMetricSnapshot.platform_connection_id == PlatformConnection.id,
            )
            .where(PlatformConnection.company_id == company_id)
            .order_by(PlatformMetricSnapshot.captured_at.desc())
            .limit(20)
        )
    ).all()

    published_items = (
        (
            await session.execute(
                select(ContentItem)
                .join(ContentPlan, ContentItem.content_plan_id == ContentPlan.id)
                .where(
                    ContentPlan.company_id == company_id, ContentItem.published_at.is_not(None)
                )
                .order_by(ContentItem.published_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    lines = [f"Company: {company.name or company.url}", ""]
    if snapshot_rows:
        lines.append("Recent metric snapshots:")
        for snapshot, platform in snapshot_rows:
            parts = [platform]
            if snapshot.follower_count is not None:
                parts.append(f"{snapshot.follower_count} followers")
            if snapshot.engagement_rate is not None:
                parts.append(f"{snapshot.engagement_rate * 100:.1f}% engagement")
            lines.append(f"- {' — '.join(parts)} (captured {snapshot.captured_at.isoformat()})")
    else:
        lines.append("No metric snapshots exist yet for this company.")
    lines.append("")
    if published_items:
        lines.append("Recently published content:")
        for item in published_items:
            lines.append(f"- [{item.platform}] {item.title} (published {item.published_at.isoformat()})")
    else:
        lines.append("No published content exists yet for this company.")

    insights, ok = await generate_performance_insights("\n".join(lines))
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Insights generation failed (check ANTHROPIC_API_KEY / Claude API availability).",
        )
    return PerformanceInsightsOut(insights=insights)
