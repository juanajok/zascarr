# ruff: noqa: E501
"""MIT-M7 (#131-a): correspondencias locales versionadas carpeta → destino.

Migración aditiva. Reutiliza los enums `origen_regla`/`estado_regla` de 0024 y
añade `tipo_registro`/`tipo_destino`. No toca series, issues, archivos ni
declaraciones.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

tipo_registro = postgresql.ENUM(
    "archivo", "serie", "publicacion", name="tipo_registro", create_type=False)
tipo_destino = postgresql.ENUM(
    "serie", "publicacion", name="tipo_destino", create_type=False)
origen_regla = postgresql.ENUM("local", "importacion", name="origen_regla", create_type=False)
estado_regla = postgresql.ENUM(
    "activa", "desactivada", "retirada", name="estado_regla", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    tipo_registro.create(bind, checkfirst=True)
    tipo_destino.create(bind, checkfirst=True)

    op.create_table(
        "correspondencias_contexto",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("correspondencia_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("correspondencias_contexto.id", ondelete="SET NULL")),
        sa.Column("declaracion_version_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("declaraciones_carpeta.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("contexto_raiz", sa.Text(), nullable=False),
        sa.Column("incluir_descendientes", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("tipo_de_registro", tipo_registro, nullable=True),
        sa.Column("destino_tipo", tipo_destino, nullable=False),
        sa.Column("destino_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("origen", origen_regla, nullable=False),
        sa.Column("estado", estado_regla, nullable=False),
        sa.Column("vigente_desde", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("procedencia", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("correspondencia_id", "version",
                            name="uq_correspondencias_contexto_identidad_version"),
    )
    op.create_index("uq_correspondencias_contexto_vigente", "correspondencias_contexto",
                    ["correspondencia_id"], unique=True,
                    postgresql_where=sa.text("vigente_hasta IS NULL"))
    op.create_index("ix_correspondencias_contexto_declaracion", "correspondencias_contexto",
                    ["declaracion_version_id"])
    op.create_index("ix_correspondencias_contexto_estado", "correspondencias_contexto",
                    ["estado"])
    op.create_index("ix_correspondencias_contexto_destino", "correspondencias_contexto",
                    ["destino_tipo", "destino_id"])
    op.create_index("ix_correspondencias_contexto_raiz", "correspondencias_contexto",
                    ["contexto_raiz"])
    op.create_index("ix_correspondencias_contexto_vigente_hasta", "correspondencias_contexto",
                    ["vigente_hasta"])


def downgrade() -> None:
    op.drop_index("ix_correspondencias_contexto_vigente_hasta", table_name="correspondencias_contexto")
    op.drop_index("ix_correspondencias_contexto_raiz", table_name="correspondencias_contexto")
    op.drop_index("ix_correspondencias_contexto_destino", table_name="correspondencias_contexto")
    op.drop_index("ix_correspondencias_contexto_estado", table_name="correspondencias_contexto")
    op.drop_index("ix_correspondencias_contexto_declaracion", table_name="correspondencias_contexto")
    op.drop_index("uq_correspondencias_contexto_vigente", table_name="correspondencias_contexto")
    op.drop_table("correspondencias_contexto")
    tipo_destino.drop(op.get_bind(), checkfirst=True)
    tipo_registro.drop(op.get_bind(), checkfirst=True)
