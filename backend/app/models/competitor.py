"""Pydantic response schemas for the Competitor Research API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    url: str
    name: str | None
    status: str
    status_error: str | None
    industry: str | None
    business_model: str | None
    target_audience: str | None
    brand_voice: str | None
    unique_value_prop: str | None
    summary: str | None
    comparison_status: str
    comparison_status_error: str | None
    product_pricing_comparison: str | None
    marketing_strategy_analysis: str | None
    competitive_gaps: str | None
    strategic_recommendations: str | None
    created_at: datetime
    updated_at: datetime


class CompetitorListResponse(BaseModel):
    items: list[CompetitorOut]
    total: int


class CompetitorCreateRequest(BaseModel):
    company_id: uuid.UUID
    url: HttpUrl
    name: str | None = None


class CompetitorCreatedResponse(BaseModel):
    """Returned immediately on create — mirrors CompanyCreatedResponse, since
    onboarding runs in the background and the caller polls GET .../{id}."""

    id: uuid.UUID
    company_id: uuid.UUID
    url: str
    status: str


class CompetitorSuggestionsRequest(BaseModel):
    company_id: uuid.UUID


class CompetitorSuggestionsResponse(BaseModel):
    suggestions: list[str]
    ok: bool
