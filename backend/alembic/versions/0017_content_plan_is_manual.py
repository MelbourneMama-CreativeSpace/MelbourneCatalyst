"""content plans: is_manual flag for the manual-drafts container

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-29

Adds `is_manual` to `content_plans` — True marks the one reusable
per-company plan that holds manually-input content items (see
`_get_or_create_manual_plan` in content_management.py), keeping it
distinct from AI-generated calendars in a company's plan history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_plans",
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("content_plans", "is_manual")
