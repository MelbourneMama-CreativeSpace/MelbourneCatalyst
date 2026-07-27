"""Pydantic response schemas for the Social Media Analyzer API.

No token fields here by design — Composio custodies OAuth tokens, this
app only ever holds a reference id, and that id isn't exposed either
(it's an internal implementation detail, not something the frontend
needs).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlatformConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # None for a not-yet-connected platform — GET /connections synthesizes
    # a placeholder row (not persisted) for every platform with no
    # PlatformConnection yet, so the frontend always has a stable list of
    # all platforms to render, not just the ones someone has connected.
    id: uuid.UUID | None = None
    company_id: uuid.UUID
    platform: str
    status: str
    status_error: str | None = None
    external_account_id: str | None = None
    external_account_name: str | None = None
    scopes: str | None = None
    connected_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlatformConnectionListResponse(BaseModel):
    items: list[PlatformConnectionOut]


class PlatformMetricSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_connection_id: uuid.UUID
    captured_at: datetime
    follower_count: int | None
    engagement_rate: float | None


class PlatformMetricSnapshotListResponse(BaseModel):
    items: list[PlatformMetricSnapshotOut]
