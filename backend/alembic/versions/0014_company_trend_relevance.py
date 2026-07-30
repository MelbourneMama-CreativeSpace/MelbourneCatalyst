"""per-company trend relevance scoring

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-21

Adds `company_trend_relevance`, a per-(company, trend) relevance score
computed against every complete company's niche_keywords, additive
alongside the existing single-tenant `trends.relevance_score` column.
Fixes the "most recently updated company" assumption that broke down as
soon as more than one client is onboarded.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_trend_relevance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("trend_id", sa.Uuid(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trend_id"], ["trends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "trend_id", name="uq_company_trend_relevance_company_trend"),
    )
    op.create_index(
        "ix_company_trend_relevance_company_id", "company_trend_relevance", ["company_id"]
    )
    op.create_index(
        "ix_company_trend_relevance_trend_id", "company_trend_relevance", ["trend_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_company_trend_relevance_trend_id", table_name="company_trend_relevance")
    op.drop_index("ix_company_trend_relevance_company_id", table_name="company_trend_relevance")
    op.drop_table("company_trend_relevance")
