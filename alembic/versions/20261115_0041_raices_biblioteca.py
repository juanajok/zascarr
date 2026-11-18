"""Raíces de biblioteca: tablas, mapeo tradición→raíz y root_id (#156, corte A).

Revision ID: 0041
Revises: 0040

Aditiva: crea una raíz por defecto con la `library_path` actual, asigna todas las
tradiciones a ella y rellena `files.root_id` por componentes. No reescribe
`files.file_path` ni mueve archivos. El downgrade falla cerrado si hay más de una
raíz o pertenencias que no son de la raíz 1.
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

from alembic import op
from zascarr.config import get_settings

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

# Valores históricos del enum en 0041. No se importa el enum vivo: una
# tradición añadida después (p. ej. `hispanoamericano` en 0052) no existía
# todavía y hacer INSERT con ella rompería esta migración.
TRADICIONES_0041 = (
    "american", "franco_belgian", "manga", "tebeo", "fumetti", "manhwa",
    "manhua", "british", "other",
)
TRADICION = ENUM(*TRADICIONES_0041, name="comic_tradition", create_type=False)


def _fila_raiz(conn) -> str | None:
    return conn.execute(
        sa.text("SELECT id FROM library_roots ORDER BY created_at, id LIMIT 1")
    ).scalar()


def upgrade() -> None:
    op.create_table(
        "library_roots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("host_path", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_library_roots_name"),
        sa.UniqueConstraint("path", name="uq_library_roots_path"),
        sa.CheckConstraint(
            "path LIKE '/%' AND path <> '/' "
            "AND path NOT LIKE '%/' AND path NOT LIKE '%//%' "
            "AND path NOT LIKE '%/../%' AND path NOT LIKE '%/..' "
            "AND path NOT LIKE '%/./%' AND path NOT LIKE '%/.' "
            "AND path NOT LIKE '%/.zascarr%'",
            name="ck_library_root_path",
        ),
        sa.CheckConstraint("is_default = false OR enabled = true",
                           name="ck_library_root_default_enabled"),
    )
    op.create_index("uq_library_roots_default", "library_roots", ["is_default"],
                    unique=True, postgresql_where=sa.text("is_default"))
    op.create_table(
        "library_root_traditions",
        sa.Column("root_id", UUID(as_uuid=True),
                  sa.ForeignKey("library_roots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tradition", TRADICION, primary_key=True),
        sa.UniqueConstraint("tradition", name="uq_library_root_traditions_tradition"),
    )
    op.create_index("ix_library_root_traditions_tradition",
                    "library_root_traditions", ["tradition"])

    settings = get_settings()
    path = os.path.normpath(str(settings.library_path))
    if path != "/":
        path = path.rstrip("/")
    conn = op.get_bind()
    root_id = conn.execute(
        sa.text(
            "INSERT INTO library_roots (name, path, host_path, enabled, is_default) "
            "VALUES (:name, :path, :host_path, true, true) RETURNING id"
        ),
        {"name": "Biblioteca", "path": path, "host_path": settings.host_library_dir or None},
    ).scalar_one()
    for tradicion in TRADICIONES_0041:
        conn.execute(
            sa.text(
                "INSERT INTO library_root_traditions (root_id, tradition) "
                "VALUES (:root_id, :tradition)"
            ),
            {"root_id": root_id, "tradition": tradicion},
        )

    op.add_column("files", sa.Column("root_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_files_root_id", "files", "library_roots",
                          ["root_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_files_root_id", "files", ["root_id"])
    # Por componentes: el prefijo incluye la barra, para que /media/library2 no caiga.
    conn.execute(
        sa.text(
            "UPDATE files SET root_id = :root_id WHERE root_id IS NULL "
            "AND (file_path = :path "
            "     OR left(file_path, length(:path) + 1) = :path || '/')"
        ),
        {"root_id": root_id, "path": path},
    )

    for tabla in ("asignacion_operaciones", "apartado_operaciones"):
        op.add_column(tabla, sa.Column("root_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tabla}_root_id", tabla, "library_roots",
                              ["root_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    conn = op.get_bind()
    total = conn.execute(sa.text("SELECT count(*) FROM library_roots")).scalar_one()
    if total > 1:
        raise RuntimeError(
            "0041 downgrade: hay más de una raíz; no se revierte para no perder pertenencias.")
    root_id = _fila_raiz(conn) if total == 1 else None
    if root_id is not None:
        for tabla in ("files", "asignacion_operaciones", "apartado_operaciones"):
            ajenas = conn.execute(
                sa.text(
                    f"SELECT count(*) FROM {tabla} "
                    "WHERE root_id IS NOT NULL AND root_id <> :root_id"
                ),
                {"root_id": root_id},
            ).scalar_one()
            if ajenas:
                raise RuntimeError(
                    f"0041 downgrade: {tabla} tiene filas de otra raíz; no se revierte."
                )
    for tabla in ("apartado_operaciones", "asignacion_operaciones"):
        op.drop_constraint(f"fk_{tabla}_root_id", tabla, type_="foreignkey")
        op.drop_column(tabla, "root_id")
    op.drop_index("ix_files_root_id", table_name="files")
    op.drop_constraint("fk_files_root_id", "files", type_="foreignkey")
    op.drop_column("files", "root_id")
    op.drop_index("ix_library_root_traditions_tradition",
                  table_name="library_root_traditions")
    op.drop_table("library_root_traditions")
    op.drop_index("uq_library_roots_default", table_name="library_roots")
    op.drop_table("library_roots")
