"""Clasificación de series anuales: `Series.kind` y `Series.parent_series_id`.

Migración **aditiva y reversible**. No mueve datos, no crea series anuales y no
toca archivos ni Issues. Las filas existentes quedan como `regular`; un anual
solo se marca cuando la fase 1 lo cree con su serie propia y el enlace al padre.

`kind` es una clasificación de SERIE (un anual es una línea de numeración
propia), no de `Issue.format`: una grapa y un anual pueden compartir formato de
publicación. `parent_series_id` es una relación de presentación, no identidad.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

series_kind = postgresql.ENUM(
    "regular", "annual", "special", name="series_kind", create_type=False)


def upgrade() -> None:
    series_kind.create(op.get_bind(), checkfirst=True)
    op.add_column("series", sa.Column(
        "kind", series_kind, nullable=False,
        server_default=sa.text("'regular'::series_kind")))
    op.add_column("series", sa.Column(
        "parent_series_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_series_parent_series_id", "series", "series",
        ["parent_series_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_series_parent_series_id", "series", ["parent_series_id"])
    op.create_check_constraint(
        "ck_series_parent_no_self", "series",
        "parent_series_id IS NULL OR parent_series_id <> id")


def downgrade() -> None:
    op.drop_constraint("ck_series_parent_no_self", "series", type_="check")
    op.drop_index("ix_series_parent_series_id", table_name="series")
    op.drop_constraint("fk_series_parent_series_id", "series", type_="foreignkey")
    op.drop_column("series", "parent_series_id")
    op.drop_column("series", "kind")
    series_kind.drop(op.get_bind(), checkfirst=True)
