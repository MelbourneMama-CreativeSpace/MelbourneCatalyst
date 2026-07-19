"""Social Media Analyzer routes: Platform Integration Agent's OAuth
"connect your account" flow (authorize → platform-side consent →
callback), connection listing/disconnect, and a metrics endpoint that's
schema-complete but returns nothing yet (no metrics-fetching logic exists
this round — see `app/agents/social_media_analyzer/__init__.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.social_media_analyzer.oauth_flow import (
    OAuthNotConfiguredError,
    build_authorize_url,
    exchange_code_for_token,
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
from app.security.oauth_state import OAuthStateError
from app.security.token_encryption import TokenEncryptionNotConfiguredError, encrypt_token

router = APIRouter()


async def _get_company_or_404(session: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


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
    company_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    await _get_company_or_404(session, company_id)
    try:
        authorize_url = build_authorize_url(platform, company_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform!r}")
    except OAuthNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except OAuthStateError:
        # sign_state() failing means TOKEN_ENCRYPTION_KEY isn't set — same
        # "this environment isn't set up for OAuth yet" story as an
        # unconfigured platform app, just a different missing setting.
        raise HTTPException(
            status_code=409,
            detail="TOKEN_ENCRYPTION_KEY is not configured — cannot start an OAuth flow",
        )
    return RedirectResponse(authorize_url, status_code=302)


@router.get("/connections/{platform}/callback")
async def callback(
    platform: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    # The platform itself redirects here — a denied-consent or
    # platform-side error must not 500, it should land the user back on
    # the app with a visible (if unhelpful-until-investigated) signal.
    if error:
        return RedirectResponse(
            f"{settings.FRONTEND_BASE_URL}/companies?connect_error={error}", status_code=302
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        token_result, state_payload = await exchange_code_for_token(platform, code, state)
    except OAuthStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OAuthNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}")

    company_id = uuid.UUID(state_payload["company_id"])

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

    try:
        connection.access_token_encrypted = encrypt_token(token_result.access_token)
        connection.refresh_token_encrypted = (
            encrypt_token(token_result.refresh_token) if token_result.refresh_token else None
        )
    except TokenEncryptionNotConfiguredError:
        raise HTTPException(
            status_code=409,
            detail="TOKEN_ENCRYPTION_KEY is not configured — cannot store the connection",
        )
    connection.token_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=token_result.expires_in)
        if token_result.expires_in
        else None
    )
    connection.external_account_id = token_result.external_account_id
    connection.external_account_name = token_result.external_account_name
    connection.scopes = token_result.granted_scopes
    connection.status = "connected"
    connection.status_error = None
    connection.connected_at = datetime.now(timezone.utc)
    await session.commit()

    return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/companies/{company_id}", status_code=302)


@router.delete("/connections/{connection_id}", response_model=PlatformConnectionOut)
async def disconnect(
    connection_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PlatformConnectionOut:
    connection = await session.get(PlatformConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.token_expires_at = None
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
