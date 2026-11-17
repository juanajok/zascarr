"""BL-LEC1 (#824): qué archivo se estaba leyendo en `reading_progress`.

Revision ID: 0049
Revises: 0048

Aditiva y reversible. `file_id` es opcional: los progresos antiguos no lo tienen.
No cambia la unicidad por `issue_id`.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reading_progress", sa.Column("file_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "reading_progress_file_id_fkey", "reading_progress", "files",
        ["file_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_reading_progress_file_id", "reading_progress", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_reading_progress_file_id", table_name="reading_progress")
    op.drop_constraint("reading_progress_file_id_fkey", "reading_progress", type_="foreignkey")
    op.drop_column("reading_progress", "file_id")
