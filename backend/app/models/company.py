"""Pydantic response schemas for the Company Analyzer API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator, model_validator


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str | None
    description: str | None
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
    """Onboarding input. The agent extracts everything else.

    Either `url` or `description` must be given — not every business has a
    website, and one that doesn't can still describe itself in a sentence or
    two. When both are present the site is scraped and the description is
    passed alongside it as extra context rather than being discarded.

    `name` is optional — when given (e.g. typed at signup) it seeds the row
    immediately instead of waiting on extraction, which still overwrites it
    if the scrape finds a different name.
    """

    url: HttpUrl | None = None
    description: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _needs_a_source(self) -> CompanyCreateRequest:
        # Without one of these there is nothing to extract a profile from,
        # and the row would sit at `pending` forever. Rejected at the edge
        # so the failure is a 422 the caller can act on, not a background
        # task that quietly marks itself failed.
        if self.url is None and not (self.description or "").strip():
            raise ValueError("Provide either a website URL or a description of the business")
        return self


class CompanyCreatedResponse(BaseModel):
    id: uuid.UUID
    url: str | None
    name: str | None
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
