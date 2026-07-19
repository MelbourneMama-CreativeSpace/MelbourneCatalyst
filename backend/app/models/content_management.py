"""Pydantic response schemas for the Content Management API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

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


ApprovalStatus = Literal["pending", "approved", "rejected"]


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
    audience_interest: str | None
    seasonal_event: str | None
    approval_status: ApprovalStatus


class ContentItemUpdateRequest(BaseModel):
    """PATCH /content-items/{id} — reschedule (drag-and-drop) and/or set
    approval status. Both fields optional; at least one is expected but
    the endpoint doesn't hard-require it (a no-op patch is harmless)."""

    approval_status: ApprovalStatus | None = None
    suggested_date: date | None = None


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
    # Overrides settings.CONTENT_PLAN_DAYS (14) — e.g. 7 for a weekly plan,
    # 30 for a monthly one.
    days: int | None = None


LifecycleStage = Literal["draft", "scheduled", "active", "completed", "archived"]


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    content_plan_id: uuid.UUID | None
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    lifecycle_stage: LifecycleStage
    name: str | None
    objective: str | None
    budget_allocation: str | None
    success_metrics: str | None
    start_date: date | None
    end_date: date | None
    created_at: datetime


class CampaignListResponse(BaseModel):
    items: list[CampaignOut]
    total: int


class CampaignCreateRequest(BaseModel):
    company_id: uuid.UUID
    content_plan_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None


class CampaignLifecycleUpdateRequest(BaseModel):
    lifecycle_stage: LifecycleStage


class CollaborationIdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaborator_archetype: str
    partnership_angle: str
    outreach_template: str
    priority: str
    rationale: str | None


class CollaborationOut(BaseModel):
    """Full detail view (includes ideas) — POST /collaborations and GET /collaborations/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    created_at: datetime
    ideas: list[CollaborationIdeaOut]


class CollaborationSummaryOut(BaseModel):
    """Lightweight view for list endpoints — no ideas, same rationale as
    ContentPlanSummaryOut."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    created_at: datetime


class CollaborationListResponse(BaseModel):
    items: list[CollaborationSummaryOut]
    total: int


class CollaborationCreateRequest(BaseModel):
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None = None
