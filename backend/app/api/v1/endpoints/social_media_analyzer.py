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
from app.agents.social_media_analyzer.oauth_providers import PLATFORM_CONFIGS
from app.config import settings
from app.db.models import Company, PlatformConnection, PlatformMetricSnapshot
from app.db.session import get_session
from app.models.social_media import (
    PlatformConnectionListResponse,
    PlatformConnectionOut,
    PlatformMetricSnapshotListResponse,
)

router = APIRouter()

# Connections in one of these statuses haven't reached a settled state
# yet — worth checking Composio for a fresher status before returning them.
_UNSETTLED_STATUSES = {"pending"}


async def _get_company_or_404(session: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


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
    company_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PlatformConnectionListResponse:
    """Always returns one row per known platform, even for platforms this
    company has never attempted to connect — unconnected platforms are
    synthesized as `status: "disconnected"` placeholders, not persisted,
    so the frontend has a stable list to render Connect buttons for."""
    await _get_company_or_404(session, company_id)

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
    platform: str, company_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    await _get_company_or_404(session, company_id)
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
    connection_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PlatformConnectionOut:
    connection = await session.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")

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
    connection_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PlatformMetricSnapshotListResponse:
    connection = await session.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    rows = (
        await session.execute(
            select(PlatformMetricSnapshot)
            .where(PlatformMetricSnapshot.platform_connection_id == connection_id)
            .order_by(PlatformMetricSnapshot.captured_at.desc())
        )
    ).scalars().all()
    return PlatformMetricSnapshotListResponse(items=list(rows))
