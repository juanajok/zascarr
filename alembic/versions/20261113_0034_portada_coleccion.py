"""Portada de colección: serie miembro elegida como override (2026-11-13).

Migración aditiva y reversible (#155, benchmark portada). Añade
`collections.cover_series_id` con FK `ON DELETE SET NULL`; la ausencia de valor
significa mosaico automático de portadas ya cacheadas. No toca series ni
archivos.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column(
        "cover_series_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_collections_cover_series_id", "collections", "series",
        ["cover_series_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_collections_cover_series_id", "collections", ["cover_series_id"])


def downgrade() -> None:
    op.drop_index("ix_collections_cover_series_id", table_name="collections")
    op.drop_constraint("fk_collections_cover_series_id", "collections", type_="foreignkey")
    op.drop_column("collections", "cover_series_id")
