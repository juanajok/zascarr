"""BL-WK4 (#342): notas libres por serie y por número.

Tabla propia, aditiva. No toca `reading_progress.notes` ni `wishlist.notes`.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.CheckConstraint("(series_id IS NOT NULL) <> (issue_id IS NOT NULL)",
                           name="ck_notes_una_entidad"),
    )
    op.create_index(
        "uq_notes_series", "notes", ["series_id"], unique=True,
        postgresql_where=sa.text("series_id IS NOT NULL"))
    op.create_index(
        "uq_notes_issue", "notes", ["issue_id"], unique=True,
        postgresql_where=sa.text("issue_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_notes_issue", table_name="notes")
    op.drop_index("uq_notes_series", table_name="notes")
    op.drop_table("notes")
