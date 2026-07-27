"""strategy approval workflow: approval_status on strategies

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-19

Adds a manual review lifecycle to `strategies`, independent of the
existing `status` column (which is only the generation lifecycle) —
same pattern already used for `content_items.approval_status`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("approval_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.create_index("ix_strategies_approval_status", "strategies", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_strategies_approval_status", table_name="strategies")
    op.drop_column("strategies", "approval_status")
