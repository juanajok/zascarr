"""#1088: última lectura y visitas recientes por serie.

Revision ID: 0051
Revises: 0050

Aditiva y reversible. `last_read_at` se rellena SOLO con fechas ya existentes
(`GREATEST(started_at, completed_at)`), nunca con `now()`.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reading_progress",
                  sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE reading_progress "
        "SET last_read_at = GREATEST(started_at, completed_at) "
        "WHERE started_at IS NOT NULL OR completed_at IS NOT NULL"
    )
    op.create_table(
        "series_recent_views",
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id"),
    )
    op.create_index("ix_series_recent_views_last_viewed_at",
                    "series_recent_views", ["last_viewed_at"])


def downgrade() -> None:
    op.drop_index("ix_series_recent_views_last_viewed_at", table_name="series_recent_views")
    op.drop_table("series_recent_views")
    op.drop_column("reading_progress", "last_read_at")
