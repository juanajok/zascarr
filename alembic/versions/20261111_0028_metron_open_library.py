"""Metron y Open Library: identidad externa de Series (2026-11-11).

Migración aditiva. Añade `series.metron_id` y `series.open_library_id`, únicos y
NULL-ables, sin tocar filas existentes. No crea tipos ni enums: `metadata_source`
es texto y las fuentes nuevas son valores de aplicación.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("metron_id", sa.BigInteger(), nullable=True, unique=True))
    op.add_column("series", sa.Column(
        "open_library_id", sa.String(length=64), nullable=True, unique=True))


def downgrade() -> None:
    op.drop_column("series", "open_library_id")
    op.drop_column("series", "metron_id")
