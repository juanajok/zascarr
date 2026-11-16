"""BL-PACK1: operaciones durables de extracción de paquetes (#344).

Revision ID: 0044
Revises: 0043
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

paquete_estado = postgresql.ENUM(
    "listando", "extrayendo", "verificando", "verificado", "publicando",
    "importando", "importado", "error",
    name="paquete_estado", create_type=False,
)


def upgrade() -> None:
    paquete_estado.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "paquete_operaciones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paquete_clave", sa.String(length=200), nullable=False),
        sa.Column("paquete_path", sa.Text(), nullable=False),
        sa.Column("paquete_dev", sa.BigInteger(), nullable=False),
        sa.Column("paquete_ino", sa.BigInteger(), nullable=False),
        sa.Column("paquete_size", sa.BigInteger(), nullable=False),
        sa.Column("paquete_mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("firma", sa.String(length=10), nullable=False),
        sa.Column("estado", paquete_estado, nullable=False, server_default="listando"),
        sa.Column("temp_dir", sa.Text()),
        sa.Column("staging_dir", sa.Text()),
        sa.Column("destino_dir", sa.Text()),
        sa.Column("items", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("total_entradas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_codigo", sa.String(length=80)),
        sa.Column("error_mensaje", sa.Text()),
        sa.Column("creada", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("actualizada", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("finalizada", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_paquete_operaciones_clave", "paquete_operaciones", ["paquete_clave"])
    op.create_index("ix_paquete_operaciones_estado", "paquete_operaciones", ["estado"])
    op.create_index("ix_paquete_operaciones_creada", "paquete_operaciones", ["creada"])
    op.create_index(
        "uq_paquete_operaciones_viva", "paquete_operaciones", ["paquete_clave"],
        unique=True,
        postgresql_where=sa.text(
            "estado IN ('listando','extrayendo','verificando','publicando','importando')"))


def downgrade() -> None:
    op.drop_table("paquete_operaciones")
    paquete_estado.drop(op.get_bind(), checkfirst=True)
