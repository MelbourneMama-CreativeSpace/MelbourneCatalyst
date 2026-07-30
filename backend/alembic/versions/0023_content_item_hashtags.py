"""content item hashtags

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-30

Structured hashtags for a content item, separate from any hashtags
already written inline into draft_copy's prose.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")
    op.add_column("content_items", sa.Column("hashtags", string_array_type, nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "hashtags")
