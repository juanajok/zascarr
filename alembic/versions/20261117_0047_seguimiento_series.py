"""#993: seguir una serie — flag, frontera, deseos SEGUIMIENTO y vistos.

Revision ID: 0047
Revises: 0046

Aditiva y reversible. El valor nuevo del enum `wishlist_origen` NO se usa en
esta migración (PG 15 no deja usar un valor añadido en la misma transacción);
solo se añade. El downgrade retira tabla, índice y columnas; el valor del enum
queda documentado como irreversible (no se puede quitar sin recrear el tipo).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "series",
        sa.Column("follow_new_issues", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.add_column(
        "series",
        sa.Column("follow_new_issues_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("ALTER TYPE wishlist_origen ADD VALUE IF NOT EXISTS 'seguimiento'")
    op.create_table(
        "seguimiento_vistos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fuente", sa.String(length=20), nullable=False),
        sa.Column("clave", sa.String(length=255), nullable=False),
        sa.Column("huella", sa.String(length=255)),
        sa.Column("visto_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("procesado_en", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("fuente", "clave",
                            name="uq_seguimiento_vistos_fuente_clave"),
    )
    op.create_index("ix_seguimiento_vistos_visto_en", "seguimiento_vistos", ["visto_en"])
    op.create_index(
        "uq_wishlist_seguimiento_numero", "wishlist", ["series_id", "numero"],
        unique=True,
        postgresql_where=sa.text("origen::text = 'seguimiento' AND numero IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_wishlist_seguimiento_numero", table_name="wishlist")
    op.drop_index("ix_seguimiento_vistos_visto_en", table_name="seguimiento_vistos")
    op.drop_table("seguimiento_vistos")
    op.drop_column("series", "follow_new_issues_since")
    op.drop_column("series", "follow_new_issues")
