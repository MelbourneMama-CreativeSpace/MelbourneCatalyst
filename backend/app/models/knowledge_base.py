"""Pydantic response schemas for Knowledge Base search and the Knowledge
Manager's freshness/audit-report endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchHitOut(BaseModel):
    document_id: str
    source_type: str
    source_url: str
    content: str
    similarity: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitOut]


class KnowledgeFreshnessOut(BaseModel):
    """Purely derived from the `documents` table — no Claude call, no
    stored row. `staleness_days` and `last_ingested_at` are `None` when
    the company has no documents yet."""

    company_id: uuid.UUID
    document_count: int
    last_ingested_at: datetime | None
    staleness_days: int | None


class KnowledgeAuditReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    status_error: str | None
    coverage_summary: str | None
    identified_gaps: str | None
    recommendations: str | None
    document_count_at_generation: int
    created_at: datetime


class KnowledgeAuditReportListResponse(BaseModel):
    items: list[KnowledgeAuditReportOut]
    total: int


class KnowledgeAuditReportCreateRequest(BaseModel):
    company_id: uuid.UUID


class DocumentOut(BaseModel):
    """Lightweight view for the document list — a truncated preview, not
    the full chunk content, so listing a company's whole KB stays cheap."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_url: str
    content_preview: str
    created_at: datetime


class DocumentDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_url: str
    content: str
    raw_metadata: dict
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int


class ManualDocumentCreateRequest(BaseModel):
    company_id: uuid.UUID
    title: str
    content: str


class BlogIndexRequest(BaseModel):
    company_id: uuid.UUID
    feed_urls: list[str]


class IngestionResultOut(BaseModel):
    """Returned by every ingestion-triggering endpoint (manual entry,
    upload, blog indexing) — how many source items were processed and how
    many chunks ended up persisted across all of them."""

    sources_processed: int
    chunks_persisted: int
