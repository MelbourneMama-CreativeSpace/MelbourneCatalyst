"""competitor research: competitors

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-19

Creates the competitors table for the Competitor Research Agent. No
dialect-specific types needed here (no vectors/arrays) — plain columns
work identically on SQLite/Postgres.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("business_model", sa.String(length=512), nullable=True),
        sa.Column("target_audience", sa.String(), nullable=True),
        sa.Column("brand_voice", sa.String(), nullable=True),
        sa.Column("unique_value_prop", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column(
            "comparison_status", sa.String(length=16), nullable=False, server_default="not_started"
        ),
        sa.Column("comparison_status_error", sa.String(), nullable=True),
        sa.Column("product_pricing_comparison", sa.String(), nullable=True),
        sa.Column("marketing_strategy_analysis", sa.String(), nullable=True),
        sa.Column("competitive_gaps", sa.String(), nullable=True),
        sa.Column("strategic_recommendations", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_competitors_company_id", "competitors", ["company_id"])
    op.create_index("ix_competitors_status", "competitors", ["status"])
    op.create_index("ix_competitors_comparison_status", "competitors", ["comparison_status"])


def downgrade() -> None:
    op.drop_index("ix_competitors_comparison_status", table_name="competitors")
    op.drop_index("ix_competitors_status", table_name="competitors")
    op.drop_index("ix_competitors_company_id", table_name="competitors")
    op.drop_table("competitors")
