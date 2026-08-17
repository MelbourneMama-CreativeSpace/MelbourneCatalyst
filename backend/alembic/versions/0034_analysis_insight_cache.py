"""analysis insight cache

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-14

Memoizes the Analysis page's AI "why" + "what's next" per (company,
period_days), so GET /analysis/overview stops calling Claude fresh on
every single page view — one row per (company, period), overwritten in
place on refresh, not an append-only log.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "analysis_insight_cache",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("ai_why", sa.String(), nullable=True),
        # Postgres ARRAY literal syntax ('{}'), not JSON ('[]') — this
        # column is ARRAY(String) on Postgres via with_variant, and only
        # falls back to plain JSON on SQLite (tests).
        sa.Column("ai_recommendations", string_array_type, nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "company_id", "period_days", name="uq_analysis_insight_cache_company_period"
        ),
    )
    op.create_index(
        "ix_analysis_insight_cache_company_id", "analysis_insight_cache", ["company_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_insight_cache_company_id", table_name="analysis_insight_cache")
    op.drop_table("analysis_insight_cache")
