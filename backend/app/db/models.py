"""SQLAlchemy ORM models: trends, companies, the shared documents store, and
Content Management (strategies + content plans)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# JSONB on Postgres (Supabase), plain JSON on SQLite (used in tests).
_MetadataType = JSON().with_variant(JSONB(), "postgresql")
# Postgres ARRAY(String) for niche_keywords; JSON list on SQLite for tests.
_StringArrayType = JSON().with_variant(ARRAY(String()), "postgresql")

# Voyage voyage-3-lite embedding dimensionality.
EMBEDDING_DIM = 1024
# Vector column on Postgres via pgvector; JSON list on SQLite so the ORM
# still loads/saves it (semantic-search queries are Postgres-only anyway).
_EmbeddingType = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")


class Trend(Base):
    __tablename__ = "trends"
    __table_args__ = (UniqueConstraint("source", "url", name="uq_trends_source_url"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    insight: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Filled in by the Trend Analyzer graph's score_relevance node against
    # the current company's niche_keywords. Null when no company is
    # onboarded, or when scoring failed.
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    # `name` is nullable because the extractor fills it in during
    # onboarding — it doesn't exist yet when the pending row is created.
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Onboarding lifecycle: pending -> scraping -> extracting ->
    # complete | complete_no_profile | failed. complete_no_profile means
    # scraping succeeded but no profile could be extracted (e.g. missing
    # ANTHROPIC_API_KEY) — distinct from a silent "complete" with blank fields.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # All extracted profile fields are nullable so the row can exist in a
    # pending state before Claude has filled it in.
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(String, nullable=True)
    unique_value_prop: Mapped[str | None] = mapped_column(String, nullable=True)
    niche_keywords: Mapped[list[str] | None] = mapped_column(_StringArrayType, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)

    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list[Document]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # e.g. "website", "blog", "product_page" — future: "social_post", "doc_upload".
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    embedding = mapped_column(_EmbeddingType, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="documents")


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One-shot generation lifecycle: pending -> complete | failed. Simpler
    # than Company's status set — a single Claude call, no partial-success
    # "scraped but no profile" state to represent here.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    marketing_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    campaign_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    growth_recommendations: Mapped[str | None] = mapped_column(String, nullable=True)
    business_suggestions: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional — a plan can be generated straight from the company profile
    # + trends without an explicit prior strategy.
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    status_error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list[ContentItem]] = relationship(
        back_populates="content_plan", cascade="all, delete-orphan", order_by="ContentItem.suggested_date"
    )


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    content_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    theme: Mapped[str | None] = mapped_column(String(256), nullable=True)
    suggested_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Best-effort match back to the Trend that inspired this idea (matched
    # by title against the trends passed as generation context) — nullable
    # since not every idea traces to a specific trend, and SET NULL so an
    # old trend disappearing doesn't take the content idea down with it.
    source_trend_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trends.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    content_plan: Mapped[ContentPlan] = relationship(back_populates="items")
