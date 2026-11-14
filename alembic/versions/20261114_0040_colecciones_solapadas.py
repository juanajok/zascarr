"""Colecciones solapadas: una serie puede estar en varias (BL-D6, 2026-11-14).

Revision ID: 0040
Revises: 0039

Migra la pertenencia única (`series.collection_id`) a la tabla puente
`collection_series` sin perder asignaciones; después retira la columna.
El downgrade conserva una colección por serie (la primera) porque el modelo
anterior no puede representar el solapamiento.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_series",
        sa.Column("collection_id", UUID(as_uuid=True),
                  sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("series_id", UUID(as_uuid=True),
                  sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_collection_series_series", "collection_series", ["series_id"])
    op.execute(
        "INSERT INTO collection_series (collection_id, series_id) "
        "SELECT collection_id, id FROM series WHERE collection_id IS NOT NULL "
        "ON CONFLICT DO NOTHING"
    )
    op.drop_column("series", "collection_id")


def downgrade() -> None:
    op.add_column("series", sa.Column("collection_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "series_collection_id_fkey", "series", "collections",
        ["collection_id"], ["id"], ondelete="SET NULL")
    op.execute(
        "UPDATE series s SET collection_id = ("
        "SELECT cs.collection_id FROM collection_series cs "
        "WHERE cs.series_id = s.id ORDER BY cs.created_at, cs.collection_id LIMIT 1)"
    )
    op.drop_index("ix_collection_series_series", table_name="collection_series")
    op.drop_table("collection_series")
