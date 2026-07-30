"""trend report campaign/competitor correlation: campaign_alignment_notes, competitor_relevance_notes on trend_reports

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-19

Adds the two new TrendReport fields needed for campaign-history
comparison and competitor-activity correlation. No new tables —
additive columns on the existing `trend_reports` table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trend_reports", sa.Column("campaign_alignment_notes", sa.String(), nullable=True))
    op.add_column("trend_reports", sa.Column("competitor_relevance_notes", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("trend_reports", "competitor_relevance_notes")
    op.drop_column("trend_reports", "campaign_alignment_notes")
