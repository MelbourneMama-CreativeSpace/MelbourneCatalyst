"""SQLAlchemy ORM models for the Trend Analyzer."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# JSONB on Postgres (Supabase), plain JSON on SQLite (used in tests).
_MetadataType = JSON().with_variant(JSONB(), "postgresql")


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
    raw_metadata: Mapped[dict] = mapped_column(_MetadataType, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
