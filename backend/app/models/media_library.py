"""Pydantic response schemas for the Media & Asset Library API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    public_url: str | None
    tags: list[str] | None
    uploaded_by: str | None
    created_at: datetime


class MediaAssetListResponse(BaseModel):
    items: list[MediaAssetOut]
