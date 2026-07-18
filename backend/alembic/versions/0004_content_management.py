"""content management: strategies + content plans

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-19

Creates strategies, content_plans, and content_items for the Strategy
Consultant and Content Planner agents. No dialect-specific types needed
here (no vectors/arrays) — plain columns work identically on SQLite/Postgres.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("marketing_strategy", sa.String(), nullable=True),
        sa.Column("campaign_direction", sa.String(), nullable=True),
        sa.Column("growth_recommendations", sa.String(), nullable=True),
        sa.Column("business_suggestions", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategies_company_id", "strategies", ["company_id"])
    op.create_index("ix_strategies_status", "strategies", ["status"])

    op.create_table(
        "content_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_content_plans_company_id", "content_plans", ["company_id"])
    op.create_index("ix_content_plans_strategy_id", "content_plans", ["strategy_id"])
    op.create_index("ix_content_plans_status", "content_plans", ["status"])

    op.create_table(
        "content_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_plan_id",
            sa.Uuid(),
            sa.ForeignKey("content_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("theme", sa.String(length=256), nullable=True),
        sa.Column("suggested_date", sa.Date(), nullable=False),
        sa.Column(
            "source_trend_id",
            sa.Uuid(),
            sa.ForeignKey("trends.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_content_items_content_plan_id", "content_items", ["content_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_content_items_content_plan_id", table_name="content_items")
    op.drop_table("content_items")
    op.drop_index("ix_content_plans_status", table_name="content_plans")
    op.drop_index("ix_content_plans_strategy_id", table_name="content_plans")
    op.drop_index("ix_content_plans_company_id", table_name="content_plans")
    op.drop_table("content_plans")
    op.drop_index("ix_strategies_status", table_name="strategies")
    op.drop_index("ix_strategies_company_id", table_name="strategies")
    op.drop_table("strategies")
