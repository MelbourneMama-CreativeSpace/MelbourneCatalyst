"""youtube upload privacy status

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-09

`privacy_status` was hardcoded to "unlisted" everywhere upstream even
though `upload_youtube_video()` itself always took it as a real parameter
— a user asking for a public upload had no way to actually get one. Adds
it as a real, per-job column (unlisted | public | private, defaulting to
unlisted — the safe default stays the default, it just stops being the
only option).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "youtube_upload_jobs",
        sa.Column(
            "privacy_status", sa.String(length=16), nullable=False, server_default="unlisted"
        ),
    )


def downgrade() -> None:
    op.drop_column("youtube_upload_jobs", "privacy_status")
