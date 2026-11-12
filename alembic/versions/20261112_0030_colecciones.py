"""Colecciones de series y política tri-estado de auto-búsqueda (2026-11-12).

Migración aditiva (#155/BL-D6). Crea `collections`, su enum de política y la FK
opcional `series.collection_id` (una serie, como máximo una colección). Sin
tocar filas existentes: las series quedan sin colección y conservan su
`wishlist_policy` (comportamiento actual de D8).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

collection_auto_search = postgresql.ENUM(
    "heredar", "incluir", "excluir", name="collection_auto_search", create_type=False)


def upgrade() -> None:
    collection_auto_search.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("auto_search", collection_auto_search, nullable=False,
                  server_default=sa.text("'heredar'::collection_auto_search")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ux_collections_name_lower", "collections",
        [sa.text("lower(name)")], unique=True)
    op.add_column("series", sa.Column(
        "collection_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_series_collection_id", "series", "collections",
        ["collection_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_series_collection_id", "series", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_series_collection_id", table_name="series")
    op.drop_constraint("fk_series_collection_id", "series", type_="foreignkey")
    op.drop_column("series", "collection_id")
    op.drop_index("ux_collections_name_lower", table_name="collections")
    op.drop_table("collections")
    collection_auto_search.drop(op.get_bind(), checkfirst=True)
