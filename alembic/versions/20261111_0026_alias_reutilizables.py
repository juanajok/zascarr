# ruff: noqa: E501
"""MIT-M7 #132-a: ciclo de vida de alias aprendidos y alias importados.

Migración aditiva. Los alias existentes de B13 quedan `propuesto` (P-A), con
versión 1 e historial inicial; no se borra ninguna fila. No toca series,
archivos ni vínculos.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

origen_alias = postgresql.ENUM("aprendido", "importado", "manual",
                               name="origen_alias", create_type=False)
estado_alias = postgresql.ENUM("propuesto", "activo", "desactivado", "retirado",
                               name="estado_alias", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    origen_alias.create(bind, checkfirst=True)
    estado_alias.create(bind, checkfirst=True)

    op.add_column("local_aliases", sa.Column(
        "origen", origen_alias, nullable=False, server_default="aprendido"))
    op.add_column("local_aliases", sa.Column(
        "estado", estado_alias, nullable=False, server_default="propuesto"))
    op.add_column("local_aliases", sa.Column(
        "version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("local_aliases", sa.Column("scope_path", sa.Text(), nullable=True))
    op.add_column("local_aliases", sa.Column(
        "historial", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("local_aliases", sa.Column(
        "actualizado_en", sa.DateTime(timezone=True), nullable=False,
        server_default=sa.text("now()")))
    op.execute("UPDATE local_aliases SET actualizado_en = created_at")
    op.execute("""
        UPDATE local_aliases
        SET historial = jsonb_build_array(jsonb_build_object(
            'version', 1, 'estado', 'propuesto', 'origen', 'aprendido',
            'series_id', series_id::text, 'scope_path', NULL,
            'fecha', created_at, 'motivo', 'migracion'))
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
        sa.Column("origen", origen_alias, nullable=False, server_default="importado"),
        sa.Column("estado", estado_alias, nullable=False, server_default="propuesto"),
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
    op.execute("""
        CREATE UNIQUE INDEX uq_alias_importado_activo
        ON alias_importado (patron_norm, COALESCE(scope_path, ''))
        WHERE vigente_hasta IS NULL AND estado = 'activo'
    """)
    op.create_index("ix_alias_importado_patron", "alias_importado", ["patron_norm"])
    op.create_index("ix_alias_importado_scope", "alias_importado", ["scope_path"])
    op.create_index("ix_alias_importado_estado", "alias_importado", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_alias_importado_estado", table_name="alias_importado")
    op.drop_index("ix_alias_importado_scope", table_name="alias_importado")
    op.drop_index("ix_alias_importado_patron", table_name="alias_importado")
    op.execute("DROP INDEX IF EXISTS uq_alias_importado_activo")
    op.drop_index("uq_alias_importado_vigente", table_name="alias_importado")
    op.drop_table("alias_importado")
    for col in ("actualizado_en", "historial", "scope_path", "version", "estado", "origen"):
        op.drop_column("local_aliases", col)
    estado_alias.drop(op.get_bind(), checkfirst=True)
    origen_alias.drop(op.get_bind(), checkfirst=True)
