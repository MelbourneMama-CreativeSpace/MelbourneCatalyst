"""content item draft copy + approver attribution on strategies/content_items

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-21

Adds `draft_copy` to `content_items` — the actual finished, publishable
copy for a calendar slot, distinct from the existing `description` brief.
Also adds lightweight `approved_by` free-text attribution to both
`strategies` and `content_items`, so a small internal team can see who
signed off on what without a full auth system.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("draft_copy", sa.String(), nullable=True))
    op.add_column("content_items", sa.Column("approved_by", sa.String(length=128), nullable=True))
    op.add_column("strategies", sa.Column("approved_by", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("strategies", "approved_by")
    op.drop_column("content_items", "approved_by")
    op.drop_column("content_items", "draft_copy")
