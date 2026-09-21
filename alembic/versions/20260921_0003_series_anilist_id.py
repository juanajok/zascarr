"""Add series.anilist_id — enricher B4: fuente AniList para manga/manhwa/manhua.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("anilist_id", sa.BigInteger, unique=True))


def downgrade() -> None:
    op.drop_column("series", "anilist_id")
