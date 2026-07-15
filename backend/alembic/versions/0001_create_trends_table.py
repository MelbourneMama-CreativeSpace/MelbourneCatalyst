"""create trends table

Revision ID: 0001
Revises:
Create Date: 2026-07-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trends",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("insight", sa.String(length=512), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "url", name="uq_trends_source_url"),
    )
    op.create_index("ix_trends_source", "trends", ["source"])
    op.create_index("ix_trends_category", "trends", ["category"])


def downgrade() -> None:
    op.drop_index("ix_trends_category", table_name="trends")
    op.drop_index("ix_trends_source", table_name="trends")
    op.drop_table("trends")
