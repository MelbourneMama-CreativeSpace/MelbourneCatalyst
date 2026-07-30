"""publishing & scheduling: content_items.scheduled_at/published_at, publish_attempts

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-30

Adds opt-in scheduling to ContentItem (scheduled_at/published_at) and a
publish_attempts log table — one row per attempt to publish an item to a
connected platform via Composio's tool-execution endpoint.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "content_items", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform_connection_id",
            sa.Uuid(),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("composio_execution_id", sa.String(length=128), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_publish_attempts_content_item_id", "publish_attempts", ["content_item_id"]
    )
    op.create_index(
        "ix_publish_attempts_platform_connection_id",
        "publish_attempts",
        ["platform_connection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publish_attempts_platform_connection_id", table_name="publish_attempts"
    )
    op.drop_index("ix_publish_attempts_content_item_id", table_name="publish_attempts")
    op.drop_table("publish_attempts")
    op.drop_column("content_items", "published_at")
    op.drop_column("content_items", "scheduled_at")
