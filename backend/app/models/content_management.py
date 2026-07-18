"""Pydantic response schemas for the Content Management API."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    status_error: str | None
    summary: str | None
    marketing_strategy: str | None
    campaign_direction: str | None
    growth_recommendations: str | None
    business_suggestions: str | None
    created_at: datetime


class StrategyListResponse(BaseModel):
    items: list[StrategyOut]
    total: int


class StrategyCreateRequest(BaseModel):
    company_id: uuid.UUID


class ContentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    content_type: str
    platform: str
    theme: str | None
    suggested_date: date
    source_trend_id: uuid.UUID | None


class ContentPlanOut(BaseModel):
    """Full detail view (includes items) — POST /content-plans and GET /content-plans/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    created_at: datetime
    items: list[ContentItemOut]


class ContentPlanSummaryOut(BaseModel):
    """Lightweight view for list endpoints — no items, avoids loading every
    plan's full calendar just to render a list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    created_at: datetime


class ContentPlanListResponse(BaseModel):
    items: list[ContentPlanSummaryOut]
    total: int


class ContentPlanCreateRequest(BaseModel):
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None = None
