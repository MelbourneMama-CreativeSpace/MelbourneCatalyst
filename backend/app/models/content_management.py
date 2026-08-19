"""Pydantic response schemas for the Content Management API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ApprovalStatus = Literal["pending", "approved", "rejected"]

PendingApprovalType = Literal["strategy", "content_item"]


class PendingApprovalOut(BaseModel):
    """One row in the approval queue — a Strategy or a ContentItem still
    `pending`, normalized into one shape so the queue can list both
    together instead of the user having to check separate pages."""

    type: PendingApprovalType
    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str | None
    title: str
    reviewer: str | None
    created_at: datetime


class PendingApprovalListResponse(BaseModel):
    items: list[PendingApprovalOut]
    total: int


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
    approval_status: ApprovalStatus
    approved_by: str | None
    reviewer: str | None
    created_at: datetime


class StrategyListResponse(BaseModel):
    items: list[StrategyOut]
    total: int


class StrategyCreateRequest(BaseModel):
    company_id: uuid.UUID


class StrategyApprovalUpdateRequest(BaseModel):
    approval_status: ApprovalStatus
    approved_by: str | None = None
    reviewer: str | None = None


class ManualContentItemCreateRequest(BaseModel):
    """POST .../manual-item — a user-supplied topic/idea, generated into a
    single ready-to-publish item rather than a whole calendar."""

    platform: str
    content_type: str
    topic: str


class ContentItemRepurposeRequest(BaseModel):
    """POST .../repurpose — adapt an existing item's message for a
    different platform/format."""

    platform: str
    content_type: str


class ContentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    draft_copy: str | None
    hashtags: list[str] | None
    media_url: str | None
    repurposed_from_id: uuid.UUID | None
    content_type: str
    platform: str
    theme: str | None
    inspired_by_handle: str | None
    suggested_date: date
    source_trend_id: uuid.UUID | None
    audience_interest: str | None
    seasonal_event: str | None
    approval_status: ApprovalStatus
    approved_by: str | None
    reviewer: str | None
    scheduled_at: datetime | None
    published_at: datetime | None
    quality_check_passed: bool | None
    quality_check_notes: str | None


class ContentItemWithCompanyOut(ContentItemOut):
    """ContentItemOut + the company it belongs to (via its ContentPlan) —
    for the cross-company Draft Workspace, where items from every client
    are grouped by platform rather than viewed one company's calendar at
    a time."""

    company_id: uuid.UUID
    company_name: str | None


class ContentItemListResponse(BaseModel):
    items: list[ContentItemWithCompanyOut]


class ContentItemUpdateRequest(BaseModel):
    """PATCH /content-items/{id} — reschedule (drag-and-drop), set approval
    status, and/or hand-edit the draft copy. All fields optional; at least
    one is expected but the endpoint doesn't hard-require it (a no-op
    patch is harmless). `approved_by` is only applied when `approval_status`
    is also set — it's attribution for the approval action, not a
    standalone field. Every time `draft_copy` changes (here or via
    regenerate), the *previous* value is snapshotted into
    `ContentItemRevision` first, so a hand-edit is never silently lost."""

    approval_status: ApprovalStatus | None = None
    approved_by: str | None = None
    suggested_date: date | None = None
    draft_copy: str | None = None
    hashtags: list[str] | None = None
    reviewer: str | None = None
    # Attribution for a draft_copy edit specifically — separate from
    # approved_by since editing and approving are different actions.
    edited_by: str | None = None


class ContentItemRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_item_id: uuid.UUID
    draft_copy: str
    edited_by: str | None
    created_at: datetime


class ContentItemRevisionListResponse(BaseModel):
    items: list[ContentItemRevisionOut]


class ContentItemCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_item_id: uuid.UUID
    author: str | None
    body: str
    created_at: datetime


class ContentItemCommentListResponse(BaseModel):
    items: list[ContentItemCommentOut]


class ContentItemCreativeBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_item_id: uuid.UUID
    hook: str | None
    shot_list: list[str]
    visual_references: str | None
    editing_notes: str | None
    thumbnail_concept: str | None
    created_at: datetime
    updated_at: datetime


class ContentItemCommentCreateRequest(BaseModel):
    author: str | None = None
    body: str


class ScheduleContentItemRequest(BaseModel):
    # None clears the schedule (unschedules the item) — same "explicit
    # null clears it" convention as everywhere else optional fields are
    # used to clear a prior value in this API.
    scheduled_at: datetime | None


class ContentPlanOut(BaseModel):
    """Full detail view (includes items) — POST /content-plans and GET /content-plans/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    status: str
    status_error: str | None
    is_manual: bool
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
    is_manual: bool
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
