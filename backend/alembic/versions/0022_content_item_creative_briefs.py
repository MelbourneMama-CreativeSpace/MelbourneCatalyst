"""content item creative briefs

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-30

Creative Brief Generator storage: one row per ContentItem, overwritten on
regeneration (not versioned like ContentItemRevision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "content_item_creative_briefs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("hook", sa.String(), nullable=True),
        sa.Column("shot_list", string_array_type, nullable=True),
        sa.Column("visual_references", sa.String(), nullable=True),
        sa.Column("editing_notes", sa.String(), nullable=True),
        sa.Column("thumbnail_concept", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("content_item_creative_briefs")
