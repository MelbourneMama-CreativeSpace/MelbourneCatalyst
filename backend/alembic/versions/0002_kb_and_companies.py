"""knowledge base + companies

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-17

Enables pgvector on Postgres, creates companies + documents tables (with
the shared embeddings store), and adds relevance_score to trends so the
Trend Analyzer can persist Trend Matching results.

Vector-specific operations (extension, Vector column type, IVFFlat index)
run only on Postgres — skipped on SQLite so the existing in-memory test DB
keeps working.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("business_model", sa.String(length=512), nullable=True),
        sa.Column("target_audience", sa.String(), nullable=True),
        sa.Column("brand_voice", sa.String(), nullable=True),
        sa.Column("unique_value_prop", sa.String(), nullable=True),
        sa.Column(
            "niche_keywords",
            postgresql.ARRAY(sa.String()) if _is_postgres() else sa.JSON(),
            nullable=True,
        ),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB() if _is_postgres() else sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("url", name="uq_companies_url"),
    )
    op.create_index("ix_companies_status", "companies", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column(
            "embedding",
            Vector(EMBEDDING_DIM) if _is_postgres() else sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB() if _is_postgres() else sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_index("ix_documents_source_type", "documents", ["source_type"])

    if _is_postgres():
        # IVFFlat with cosine ops — standard default for small-to-medium
        # corpora. lists=100 is the pgvector-recommended baseline; can be
        # retuned once the corpus is large (rule of thumb: rows / 1000).
        op.execute(
            "CREATE INDEX ix_documents_embedding_cosine "
            "ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )

    op.add_column("trends", sa.Column("relevance_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trends", "relevance_score")
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_documents_embedding_cosine")
    op.drop_index("ix_documents_source_type", table_name="documents")
    op.drop_index("ix_documents_company_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_companies_status", table_name="companies")
    op.drop_table("companies")
    if _is_postgres():
        # Intentionally don't DROP EXTENSION vector — it may be used by
        # other schemas. Enabling it is idempotent; leaving it is safe.
        pass
