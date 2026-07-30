"""reviewer assignment

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-30

Free-text reviewer assignment on ContentItem and Strategy — same
lightweight attribution pattern as approved_by, not a real per-user
identity (no real auth-linked user model exists in this app).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("reviewer", sa.String(length=128), nullable=True))
    op.add_column("strategies", sa.Column("reviewer", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("strategies", "reviewer")
    op.drop_column("content_items", "reviewer")
