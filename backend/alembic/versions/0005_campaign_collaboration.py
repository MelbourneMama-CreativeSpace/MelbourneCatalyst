"""campaign manager + brand collaboration: campaigns, collaborations, collaboration_ideas

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19

Creates campaigns, collaborations, and collaboration_ideas for the
Campaign Manager and Brand Collaboration agents. No dialect-specific
types needed here (no vectors/arrays) — plain columns work identically
on SQLite/Postgres.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_plan_id",
            sa.Uuid(),
            sa.ForeignKey("content_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("lifecycle_stage", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("objective", sa.String(), nullable=True),
        sa.Column("budget_allocation", sa.String(), nullable=True),
        sa.Column("success_metrics", sa.String(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_campaigns_company_id", "campaigns", ["company_id"])
    op.create_index("ix_campaigns_content_plan_id", "campaigns", ["content_plan_id"])
    op.create_index("ix_campaigns_strategy_id", "campaigns", ["strategy_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_lifecycle_stage", "campaigns", ["lifecycle_stage"])

    op.create_table(
        "collaborations",
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
    op.create_index("ix_collaborations_company_id", "collaborations", ["company_id"])
    op.create_index("ix_collaborations_strategy_id", "collaborations", ["strategy_id"])
    op.create_index("ix_collaborations_status", "collaborations", ["status"])

    op.create_table(
        "collaboration_ideas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "collaboration_id",
            sa.Uuid(),
            sa.ForeignKey("collaborations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("collaborator_archetype", sa.String(length=256), nullable=False),
        sa.Column("partnership_angle", sa.String(), nullable=False),
        sa.Column("outreach_template", sa.String(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_collaboration_ideas_collaboration_id", "collaboration_ideas", ["collaboration_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_collaboration_ideas_collaboration_id", table_name="collaboration_ideas")
    op.drop_table("collaboration_ideas")
    op.drop_index("ix_collaborations_status", table_name="collaborations")
    op.drop_index("ix_collaborations_strategy_id", table_name="collaborations")
    op.drop_index("ix_collaborations_company_id", table_name="collaborations")
    op.drop_table("collaborations")
    op.drop_index("ix_campaigns_lifecycle_stage", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_strategy_id", table_name="campaigns")
    op.drop_index("ix_campaigns_content_plan_id", table_name="campaigns")
    op.drop_index("ix_campaigns_company_id", table_name="campaigns")
    op.drop_table("campaigns")
