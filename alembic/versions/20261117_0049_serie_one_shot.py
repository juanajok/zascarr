"""#1027/ADR 0022: valor `one_shot` en el enum `series_kind` (sin DML).

Revision ID: 0049
Revises: 0048

Aditiva: solo añade el valor del enum. No hay backfill ni DML; las series
existentes siguen `regular`. PG no permite retirar un valor de enum sin
recrear el tipo, así que el `downgrade` lo deja documentado.
"""
from __future__ import annotations

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE series_kind ADD VALUE IF NOT EXISTS 'one_shot'")


def downgrade() -> None:
    # Irreversible a propósito: quitar el valor exigiría recrear el tipo y todas
    # las columnas que lo usan. No se borran filas y el valor queda inerte.
    pass
