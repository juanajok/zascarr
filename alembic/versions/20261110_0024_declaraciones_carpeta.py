# ruff: noqa: E501
"""MIT-M7 (#130-a): declaraciones de carpeta versionadas.

Migración aditiva: solo crea los enums y la tabla `declaraciones_carpeta`
con su historial. No toca series, archivos, vínculos ni `local_aliases`.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

tipo_significado = postgresql.ENUM(
    "autor", "publicacion", name="tipo_significado_carpeta", create_type=False)
origen_regla = postgresql.ENUM("local", "importacion", name="origen_regla", create_type=False)
estado_regla = postgresql.ENUM(
    "activa", "desactivada", "retirada", name="estado_regla", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    tipo_significado.create(bind, checkfirst=True)
    origen_regla.create(bind, checkfirst=True)
    estado_regla.create(bind, checkfirst=True)

    op.create_table(
        "declaraciones_carpeta",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("declaracion_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contexto_raiz", sa.Text(), nullable=False),
        sa.Column("incluir_descendientes", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("tipo_de_significado", tipo_significado, nullable=False),
        sa.Column("origen", origen_regla, nullable=False),
        sa.Column("estado", estado_regla, nullable=False),
        sa.Column("vigente_desde", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("procedencia", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("declaracion_id", "version",
                            name="uq_declaraciones_carpeta_declaracion_version"),
    )
    op.create_index("uq_declaraciones_carpeta_vigente", "declaraciones_carpeta",
                    ["declaracion_id"], unique=True,
                    postgresql_where=sa.text("vigente_hasta IS NULL"))
    op.create_index("uq_declaraciones_carpeta_raiz_local_activa", "declaraciones_carpeta",
                    ["contexto_raiz"], unique=True,
                    postgresql_where=sa.text(
                        "vigente_hasta IS NULL AND origen = 'local' AND estado = 'activa'"))
    op.create_index("ix_declaraciones_carpeta_contexto_raiz", "declaraciones_carpeta",
                    ["contexto_raiz"])
    op.create_index("ix_declaraciones_carpeta_vigente_hasta", "declaraciones_carpeta",
                    ["vigente_hasta"])


def downgrade() -> None:
    op.drop_index("ix_declaraciones_carpeta_vigente_hasta", table_name="declaraciones_carpeta")
    op.drop_index("ix_declaraciones_carpeta_contexto_raiz", table_name="declaraciones_carpeta")
    op.drop_index("uq_declaraciones_carpeta_raiz_local_activa", table_name="declaraciones_carpeta")
    op.drop_index("uq_declaraciones_carpeta_vigente", table_name="declaraciones_carpeta")
    op.drop_table("declaraciones_carpeta")
    estado_regla.drop(op.get_bind(), checkfirst=True)
    origen_regla.drop(op.get_bind(), checkfirst=True)
    tipo_significado.drop(op.get_bind(), checkfirst=True)
