"""File.is_missing/missing_since + ImportRun.disappeared_count — B7: un
tebeo borrado a mano del disco deja de contar como "lo tienes".

Revision ID: 0014
Revises: 0013

El File nunca se borra por esto, solo se marca — Importer.scan_and_import()
lo detecta y lo revierte solo si el fichero reaparece (disco de red que
estuvo desmontado, etc.).
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("is_missing", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("files", sa.Column("missing_since", sa.DateTime(timezone=True)))
    op.add_column("import_runs", sa.Column("disappeared_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("import_runs", "disappeared_count")
    op.drop_column("files", "missing_since")
    op.drop_column("files", "is_missing")
