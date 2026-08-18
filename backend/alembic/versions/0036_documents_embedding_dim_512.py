"""documents embedding dimension: 1024 -> 512

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-19

Fixes a real, pre-existing production bug: `documents.embedding` was
declared `vector(1024)` on the assumption voyage-3-lite defaults to
1024 dimensions. Confirmed live against the real Voyage API that it
does not -- voyage-3-lite only ever produces 512-dimension vectors,
and explicitly rejects `output_dimension=1024` with "accepted values
for 'voyage-3-lite' are [512]". Every real (non-null) embedding insert
has therefore always raised `ValueError: expected 1024 dimensions, not
512` at commit time -- caught nowhere, so it surfaced only as a
document silently failing to persist. Every existing `documents` row
was inserted with `embedding = NULL` (the graceful VOYAGE_API_KEY-not-
configured fallback), confirmed via `vector_dims(embedding)` returning
NULL for all of them -- so no real data is lost by narrowing the
column; nothing to convert.

The ivfflat index is tied to the column's declared dimension and must
be dropped before the type change and recreated after, same ordering
0002_kb_and_companies.py used to create it originally.
"""

from __future__ import annotations

from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_cosine")
    op.alter_column(
        "documents",
        "embedding",
        type_=Vector(512),
        postgresql_using="embedding::vector(512)",
    )
    op.execute(
        "CREATE INDEX ix_documents_embedding_cosine "
        "ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_cosine")
    op.alter_column(
        "documents",
        "embedding",
        type_=Vector(1024),
        postgresql_using="embedding::vector(1024)",
    )
    op.execute(
        "CREATE INDEX ix_documents_embedding_cosine "
        "ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
