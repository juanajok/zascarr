"""local_aliases — B13: alias local de nombre de archivo aprendido de
asignaciones manuales en Pendientes.

Revision ID: 0012
Revises: 0011

pattern_norm (normalize_title del título que naming.py extrajo del
nombre de archivo) → series_id. SeriesMatcher.decide() lo consulta
ANTES del matcher fuzzy (pg_trgm), y ReviewService.assign_to_series
escribe/actualiza la fila cada vez que el coleccionista confirma una
asignación manual desde Pendientes (B2/B12). Alias LOCAL de esta
instalación, no una regla global — CLAUDE.md §5.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_aliases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pattern_norm", sa.String(500), nullable=False, unique=True),
        sa.Column("series_id", UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_local_aliases_series_id", "local_aliases", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_local_aliases_series_id", table_name="local_aliases")
    op.drop_table("local_aliases")
