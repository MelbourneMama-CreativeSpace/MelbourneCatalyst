"""products & services cataloging: products_and_services on companies

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-19

Adds `products_and_services` to `companies`, extracted by the same
Claude call that already produces `niche_keywords` — same dialect-aware
array/JSON column type, same nullable-until-onboarded shape.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")
    op.add_column("companies", sa.Column("products_and_services", string_array_type, nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "products_and_services")
