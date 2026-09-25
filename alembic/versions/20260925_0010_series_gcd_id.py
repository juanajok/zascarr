"""Add series.gcd_id — C0: descubrimiento vía Grand Comics Database.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("gcd_id", sa.BigInteger, unique=True))


def downgrade() -> None:
    op.drop_column("series", "gcd_id")
