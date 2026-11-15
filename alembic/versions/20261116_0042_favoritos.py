"""CUR3: favoritos locales de series (2026-11-16).

Revision ID: 0042
Revises: 0041
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "series",
        sa.Column("favorite", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("series", "favorite")
