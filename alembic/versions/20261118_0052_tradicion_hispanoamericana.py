"""#1115: valor `hispanoamericano` en el enum `comic_tradition` (sin DML).

Revision ID: 0052
Revises: 0051

Aditiva: solo añade el valor del enum. Al no poder retirar valores de un enum
PostgreSQL sin recrear el tipo, el `downgrade` es irreversible y queda
documentado (mismo criterio que 0049).
"""
from __future__ import annotations

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE comic_tradition ADD VALUE IF NOT EXISTS 'hispanoamericano'")


def downgrade() -> None:
    # Irreversible a propósito: exigiría recrear `comic_tradition` y todas sus
    # columnas. No se borran filas; el valor queda inerte si no se usa.
    pass
