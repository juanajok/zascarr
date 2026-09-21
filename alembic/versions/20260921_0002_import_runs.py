"""Add import_runs — historial de ciclos de Importer.scan_and_import() (B1/B3).

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("import_runs",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("started_at",       sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at",      sa.DateTime(timezone=True), nullable=False),
        sa.Column("files_scanned",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("imported_count",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicate_count",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("unsorted_count",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count",      sa.Integer, nullable=False, server_default="0"),
        sa.Column("details",          JSONB, server_default="{}"),
    )
    op.execute("CREATE INDEX idx_import_runs_started ON import_runs(started_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_runs CASCADE")
