"""CUR4: idioma y tipo de edición de serie (2026-11-16).

Revision ID: 0043
Revises: 0042
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

edition_kind = postgresql.ENUM(
    "oficial", "tradumaqueta", "escaneo_propio", "otro",
    name="edition_kind", create_type=False,
)


def upgrade() -> None:
    edition_kind.create(op.get_bind(), checkfirst=True)
    op.add_column("series", sa.Column("language", sa.String(length=10), nullable=True))
    op.add_column("series", sa.Column("edition_kind", edition_kind, nullable=True))


def downgrade() -> None:
    op.drop_column("series", "edition_kind")
    op.drop_column("series", "language")
    edition_kind.drop(op.get_bind(), checkfirst=True)
