"""Pydantic response schema for the dashboard summary endpoint."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.company import CompanyOut
from app.models.trend import TrendOut


class DashboardSummaryOut(BaseModel):
    company_count: int
    companies_onboarding: int
    recent_companies: list[CompanyOut]
    trending_topics: list[TrendOut]
