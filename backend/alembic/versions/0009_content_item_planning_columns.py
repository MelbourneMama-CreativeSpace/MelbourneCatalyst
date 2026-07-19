"""content planner remainder: audience_interest, seasonal_event, approval_status on content_items

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19

Adds the three new ContentItem columns needed for audience-interest-based
planning, seasonal-event integration, and the content preview & approval
flow. No new tables — these are additive columns on the existing
`content_items` table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("audience_interest", sa.String(length=256), nullable=True))
    op.add_column("content_items", sa.Column("seasonal_event", sa.String(length=128), nullable=True))
    op.add_column(
        "content_items",
        sa.Column("approval_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.create_index("ix_content_items_approval_status", "content_items", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_content_items_approval_status", table_name="content_items")
    op.drop_column("content_items", "approval_status")
    op.drop_column("content_items", "seasonal_event")
    op.drop_column("content_items", "audience_interest")
