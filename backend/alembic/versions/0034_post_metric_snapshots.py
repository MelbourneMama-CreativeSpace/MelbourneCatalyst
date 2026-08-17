"""post metric snapshots

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-12

Real per-post engagement metrics (likes/comments/shares/saves/views/
reach), one row per fetch — the data-layer foundation for LoomVerse's
Analysis: per-post performance, content-type/platform aggregation, and
the "5 questions" dashboard. Every field is nullable — what's actually
fetchable differs genuinely per platform (confirmed live against each
real Composio toolkit), not a uniform assumption.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.create_table(
        "post_metric_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("raw_metadata", metadata_type, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_post_metric_snapshots_content_item_id",
        "post_metric_snapshots",
        ["content_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_post_metric_snapshots_content_item_id", table_name="post_metric_snapshots"
    )
    op.drop_table("post_metric_snapshots")
