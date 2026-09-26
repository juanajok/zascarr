"""Wishlist.last_error — D9: por qué una búsqueda no avanza.

Revision ID: 0013
Revises: 0012

Sin timestamp propio: se correlaciona con `last_searched_at` (ya
existente, se marca en el mismo punto del orquestador donde se decide
la causa) — un campo nuevo `last_error_at` habría sido redundante.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wishlist", sa.Column("last_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("wishlist", "last_error")
