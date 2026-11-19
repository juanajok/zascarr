"""#993: índice único parcial de deseos de seguimiento (tras el enum).

Revision ID: 0048
Revises: 0047

En una migración aparte por claridad. El predicado no nombra el valor nuevo
(`origen <> 'manual'`), así que es inmutable y no usa `seguimiento` dentro de la
transacción que lo añade; cubre los deseos de política y de seguimiento y deja
fuera los manuales (que sí admiten duplicados a propósito).
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_wishlist_seguimiento_numero", "wishlist", ["series_id", "numero"],
        unique=True,
        postgresql_where=sa.text("origen <> 'manual' AND numero IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_wishlist_seguimiento_numero", table_name="wishlist")
