"""Add series.tebeosfera_slug — enricher B4: fuente Tebeosfera para tebeo/BD en español.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("tebeosfera_slug", sa.String(255), unique=True))


def downgrade() -> None:
    op.drop_column("series", "tebeosfera_slug")
