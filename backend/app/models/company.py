"""Pydantic response schemas for the Company Analyzer API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    name: str | None
    status: str
    status_error: str | None
    industry: str | None
    business_model: str | None
    target_audience: str | None
    brand_voice: str | None
    unique_value_prop: str | None
    niche_keywords: list[str] | None
    summary: str | None
    products_and_services: list[str] | None
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    items: list[CompanyOut]
    total: int


class CompanyCreateRequest(BaseModel):
    """Onboarding input. `url` is required; the agent extracts everything
    else. `name` is optional — when given (e.g. typed at signup) it seeds
    the row immediately instead of waiting on extraction, which still
    overwrites it if the scrape finds a different name."""

    url: HttpUrl
    name: str | None = None


class CompanyCreatedResponse(BaseModel):
    id: uuid.UUID
    url: str
    name: str | None
    status: str
