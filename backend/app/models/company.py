"""Pydantic response schemas for the Company Analyzer API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


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
    """Onboarding input — just a URL. The agent extracts everything else."""

    url: HttpUrl


class CompanyCreatedResponse(BaseModel):
    id: uuid.UUID
    url: str
    status: str


class CompanyMemberOut(BaseModel):
    """One person with access to a company.

    `user_id` is null for an invite that hasn't been claimed yet — that row
    grants nothing until someone signs in with the matching email (see
    `app/security/ownership.py`), which is why `pending` is surfaced
    explicitly rather than left for the UI to infer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    user_id: str | None
    user_email: str | None
    invited_email: str | None
    role: str
    created_at: datetime

    @property
    def pending(self) -> bool:
        return self.user_id is None


class CompanyMemberListResponse(BaseModel):
    items: list[CompanyMemberOut]
    # Which of `items` is the caller — lets the UI mark "you" without the
    # browser ever needing to know its own Supabase user id.
    current_user_id: str


class CompanyMemberInviteRequest(BaseModel):
    """Invite by email address only.

    Deliberately not a user id: this app has no way to look one up (that
    would need Supabase's Admin API and a service-role key), and the person
    being invited may not have an account yet at all.
    """

    # Plain `str` rather than pydantic's `EmailStr`, which needs the
    # `email-validator` package this project doesn't install. A shape check
    # is all that's useful here anyway: the address is never delivered to,
    # it only has to match the `email` claim of a real Supabase token later,
    # and that comparison is exact — so a stricter parser would reject
    # addresses Supabase itself accepts without buying any safety.
    email: str

    @field_validator("email")
    @classmethod
    def _looks_like_an_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        local, _, domain = cleaned.partition("@")
        if not local or not domain or "." not in domain or " " in cleaned:
            raise ValueError("Not a valid email address")
        return cleaned
