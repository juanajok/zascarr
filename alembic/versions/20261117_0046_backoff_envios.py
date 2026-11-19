"""Backoff persistente tras fallos de envío de Deseados (T-62).

Revision ID: 0046
Revises: 0045

Aditiva y reversible. `retry_count` cuenta fallos de envío consecutivos y
`next_retry_at` es el momento antes del cual el ciclo automático no reintenta
ese deseo; las filas existentes quedan con 0 y NULL (elegibles como hasta
ahora).
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wishlist",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wishlist", "next_retry_at")
    op.drop_column("wishlist", "retry_count")
