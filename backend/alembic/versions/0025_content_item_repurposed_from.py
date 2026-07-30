"""content item repurposed_from_id

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-30

Self-referential reference from a repurposed item back to its source —
the Content Repurposing Engine.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column(
            "repurposed_from_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("content_items", "repurposed_from_id")
