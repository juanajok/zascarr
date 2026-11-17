"""Modo de las operaciones de duplicados: apartar o enlazar (#265).

Revision ID: 0044
Revises: 0043

Aditiva y reversible. Las operaciones existentes quedan como `apartar`.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "apartado_operaciones",
        sa.Column("modo", sa.String(20), nullable=False, server_default="apartar"),
    )


def downgrade() -> None:
    op.drop_column("apartado_operaciones", "modo")
