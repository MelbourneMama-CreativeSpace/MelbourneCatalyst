"""trend outputs + knowledge manager: trend_reports, knowledge_audit_reports

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-19

Creates trend_reports (Trend Analyzer's weekly report / insights /
content-opportunities generation) and knowledge_audit_reports (Knowledge
Manager's KB coverage/gaps report). `key_themes` on trend_reports reuses
the same dialect-aware ARRAY/JSON variant already used for
Company.niche_keywords.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "trend_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("key_themes", string_array_type, nullable=True),
        sa.Column("notable_trends_summary", sa.String(), nullable=True),
        sa.Column("content_opportunities", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_trend_reports_company_id", "trend_reports", ["company_id"])
    op.create_index("ix_trend_reports_status", "trend_reports", ["status"])

    op.create_table(
        "knowledge_audit_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("coverage_summary", sa.String(), nullable=True),
        sa.Column("identified_gaps", sa.String(), nullable=True),
        sa.Column("recommendations", sa.String(), nullable=True),
        sa.Column("document_count_at_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_audit_reports_company_id", "knowledge_audit_reports", ["company_id"])
    op.create_index("ix_knowledge_audit_reports_status", "knowledge_audit_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_audit_reports_status", table_name="knowledge_audit_reports")
    op.drop_index("ix_knowledge_audit_reports_company_id", table_name="knowledge_audit_reports")
    op.drop_table("knowledge_audit_reports")
    op.drop_index("ix_trend_reports_status", table_name="trend_reports")
    op.drop_index("ix_trend_reports_company_id", table_name="trend_reports")
    op.drop_table("trend_reports")
