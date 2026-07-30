"""content quality review: quality_check_passed/notes on content_items

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-30

Adds a quality/brand-consistency check result to ContentItem — single
current state (overwritten by each new check), not versioned like
draft_copy's revisions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items", sa.Column("quality_check_passed", sa.Boolean(), nullable=True)
    )
    op.add_column("content_items", sa.Column("quality_check_notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "quality_check_notes")
    op.drop_column("content_items", "quality_check_passed")
