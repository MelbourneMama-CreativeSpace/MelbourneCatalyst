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
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    items: list[CompanyOut]
    total: int


class CompanyCreateRequest(BaseModel):
    """Onboarding input — just a URL. The agent extracts everything else."""

    url: HttpUrl


class CompanyCreatedResponse(BaseModel):
    id: uuid.UUID
    url: str
    status: str
