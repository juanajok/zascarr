# ruff: noqa: E501
"""MIT-M7-US03 (#132-a): ciclo de consentimiento de alias y alias importado.

Migración aditiva. Amplía `local_aliases` (origen/estado/versión/historial/scope) y
crea `alias_importado` versionado por filas. No toca series, issues, archivos,
declaraciones ni correspondencias. Los alias aprendidos existentes quedan en
`propuesto` (P-A recomendada): no se aplican hasta que la persona los active.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

origen_alias = postgresql.ENUM(
    "aprendido", "importado", "manual", name="origen_alias", create_type=False)
estado_alias = postgresql.ENUM(
    "propuesto", "activo", "desactivado", "retirado", name="estado_alias", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    origen_alias.create(bind, checkfirst=True)
    estado_alias.create(bind, checkfirst=True)

    op.add_column("local_aliases", sa.Column(
        "origen", origen_alias, nullable=False, server_default=sa.text("'aprendido'")))
    op.add_column("local_aliases", sa.Column(
        "estado", estado_alias, nullable=False, server_default=sa.text("'propuesto'")))
    op.add_column("local_aliases", sa.Column(
        "version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("local_aliases", sa.Column("scope_path", sa.Text(), nullable=True))
    op.add_column("local_aliases", sa.Column(
        "historial", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb")))
    op.add_column("local_aliases", sa.Column(
        "actualizado_en", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.text("now()")))

    # Alias aprendidos anteriores a #132: quedan pendientes de activar (P-A) con su
    # instantánea inicial en el historial. No se borra ni se reescribe ninguna fila.
    op.execute("""
        UPDATE local_aliases
        SET historial = jsonb_build_array(jsonb_build_object(
                'version', 1,
                'estado', 'propuesto',
                'origen', 'aprendido',
                'series_id', series_id::text,
                'scope_path', NULL,
                'fecha', COALESCE(created_at, now()),
                'motivo', 'migracion')),
            actualizado_en = COALESCE(created_at, now())
        WHERE historial = '[]'::jsonb
    """)

    op.create_table(
        "alias_importado",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("alias_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("patron_norm", sa.Text(), nullable=False),
        sa.Column("scope_path", sa.Text(), nullable=True),
        sa.Column("series_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origen", origen_alias, nullable=False,
                  server_default=sa.text("'importado'")),
        sa.Column("estado", estado_alias, nullable=False,
                  server_default=sa.text("'propuesto'")),
        sa.Column("vigente_desde", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("procedencia", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("alias_id", "version", name="uq_alias_importado_alias_version"),
    )
    op.create_index("uq_alias_importado_vigente", "alias_importado", ["alias_id"],
                    unique=True, postgresql_where=sa.text("vigente_hasta IS NULL"))
    op.create_index(
        "uq_alias_importado_activo", "alias_importado",
        ["patron_norm", sa.text("COALESCE(scope_path, '')")], unique=True,
        postgresql_where=sa.text("vigente_hasta IS NULL AND estado = 'activo'"))
    op.create_index("ix_alias_importado_patron", "alias_importado", ["patron_norm"])
    op.create_index("ix_alias_importado_scope", "alias_importado", ["scope_path"])
    op.create_index("ix_alias_importado_estado", "alias_importado", ["estado"])
    op.create_index("ix_alias_importado_vigente_hasta", "alias_importado", ["vigente_hasta"])


def downgrade() -> None:
    op.drop_index("ix_alias_importado_vigente_hasta", table_name="alias_importado")
    op.drop_index("ix_alias_importado_estado", table_name="alias_importado")
    op.drop_index("ix_alias_importado_scope", table_name="alias_importado")
    op.drop_index("ix_alias_importado_patron", table_name="alias_importado")
    op.drop_index("uq_alias_importado_activo", table_name="alias_importado")
    op.drop_index("uq_alias_importado_vigente", table_name="alias_importado")
    op.drop_table("alias_importado")
    for columna in ("actualizado_en", "historial", "scope_path", "version",
                    "estado", "origen"):
        op.drop_column("local_aliases", columna)
    estado_alias.drop(op.get_bind(), checkfirst=True)
    origen_alias.drop(op.get_bind(), checkfirst=True)
