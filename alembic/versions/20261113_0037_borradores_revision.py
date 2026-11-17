"""Borradores explícitos de revisión de carpeta (#725).

Aditiva. Una fila por carpeta+serie, con JSON validado por el servicio y
caducidad; no introduce sesión ni estado global.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revision_borradores",
        sa.Column("clave", sa.String(length=500), primary_key=True),
        sa.Column(
            "series_id", UUID(as_uuid=True),
            sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("datos", JSONB, nullable=False),
        sa.Column(
            "actualizado", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.Column("caduca", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revision_borradores_caduca", "revision_borradores", ["caduca"])


def downgrade() -> None:
    op.drop_index("ix_revision_borradores_caduca", table_name="revision_borradores")
    op.drop_table("revision_borradores")
