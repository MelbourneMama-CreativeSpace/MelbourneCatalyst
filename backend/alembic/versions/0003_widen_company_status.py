"""widen company status column

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-18

`Company.status` gains a new value, "complete_no_profile" (19 chars),
which didn't fit in the original VARCHAR(16). SQLite doesn't enforce
VARCHAR length (this is a no-op there), but Postgres does.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.alter_column(
            "companies",
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
        )


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.alter_column(
            "companies",
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
        )
