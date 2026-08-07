"""Internal data shapes for the Company Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ScrapedPage:
    """A unit of company content, before chunking/embedding.

    Despite the name this isn't always a scraped web page — a company with
    no website is described by typed text or by its connected social
    accounts, and those enter the pipeline as `ScrapedPage`s too so that
    chunking, embedding and extraction stay one code path.

    `source_type` overrides the URL-based classification in
    `classify_source_type()`, which can only distinguish kinds of web page.
    """

    url: str
    title: str | None
    content: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    source_type: str | None = None


@dataclass(slots=True)
class CompanyProfile:
    """Structured company profile extracted by Claude from aggregated page content.

    Matches the JSON schema of the `extract_company_profile` tool call. Fields
    are optional so a partial extraction (e.g. couldn't determine
    business_model) still persists useful data.
    """

    name: str | None = None
    industry: str | None = None
    business_model: str | None = None
    target_audience: str | None = None
    brand_voice: str | None = None
    unique_value_prop: str | None = None
    niche_keywords: list[str] = field(default_factory=list)
    summary: str | None = None
    products_and_services: list[str] = field(default_factory=list)
