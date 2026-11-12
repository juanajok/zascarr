"""BL-DUP1 (#264): comprobante de apartar copias idénticas a cuarentena.

Revision ID: 0030
Revises: 0029

Aditiva y reversible. No toca `files`, `series`, `issues` ni las tablas de
operaciones 0017-0019. Dos tablas propias: la cabecera de la operación y un
grupo por contenido idéntico, con su detalle JSONB de rutas/estados.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_ESTADOS_OPERACION = ("en_curso", "confirmada", "deshecha", "cancelada")
_ESTADOS_GRUPO = ("pendiente", "movido", "deshecho", "rechazado", "error")


def upgrade() -> None:
    op.execute(
        "CREATE TYPE apartado_estado AS ENUM "
        "('en_curso', 'confirmada', 'deshecha', 'cancelada')"
    )
    op.execute("CREATE TYPE apartado_grupo_estado AS ENUM "
               "('pendiente', 'movido', 'deshecho', 'rechazado', 'error')")
    op.create_table(
        "apartado_operaciones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("estado",
                  ENUM(*_ESTADOS_OPERACION, name="apartado_estado", create_type=False),
                  nullable=False, server_default="en_curso"),
        sa.Column("token_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creada", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("actualizada", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("total_grupos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_archivos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("resultado", JSONB, nullable=True),
    )
    op.create_table(
        "apartado_grupos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operacion_id", UUID(as_uuid=True),
                  sa.ForeignKey("apartado_operaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grupo_clave", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("estado",
                  ENUM(*_ESTADOS_GRUPO, name="apartado_grupo_estado", create_type=False),
                  nullable=False, server_default="pendiente"),
        sa.Column("detalle", JSONB, nullable=False),
        sa.UniqueConstraint(
            "operacion_id", "grupo_clave", name="uq_apartado_grupo_operacion_clave"),
    )
    op.create_index("ix_apartado_grupos_operacion", "apartado_grupos", ["operacion_id"])
    op.create_index("ix_apartado_grupos_estado", "apartado_grupos", ["estado"])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE apartado_operaciones IN ACCESS EXCLUSIVE MODE"))
    pendientes = bind.execute(sa.text(
        "SELECT count(*) FROM apartado_operaciones o "
        "LEFT JOIN apartado_grupos g ON g.operacion_id = o.id "
        "WHERE o.estado = 'en_curso' OR g.estado = 'movido'")).scalar()
    if pendientes:
        raise RuntimeError(
            "No se puede bajar de la 0030: hay apartados en curso o copias movidas "
            "en cuarentena. Termínalos o deshazlos antes de bajar la migración."
        )
    op.drop_table("apartado_grupos")
    op.drop_table("apartado_operaciones")
    op.execute("DROP TYPE IF EXISTS apartado_grupo_estado")
    op.execute("DROP TYPE IF EXISTS apartado_estado")
