# ruff: noqa: E501
"""Rescan de la biblioteca (BL-R9): persistir el instante de modificación de cada archivo registrado.

Revision ID: 0021
Revises: 0020

Por qué existe: el rescan debe distinguir «ruta registrada cuyo contenido cambió» sin abrir ningún CBZ
(CLAUDE.md §4, coste en la Pi). Para eso guarda, junto al hash, el stat que lo describe: el tamaño ya vive
en `files.file_size_bytes`; falta el instante. `st_mtime_ns` (nanosegundos, BigInteger) es exacto y no
depende de la resolución del reloj del sistema de ficheros.

Regla que acompaña a la columna (docs/design/especificacion-BL-R9-rescan-biblioteca.md §2): **todo
escritor de un hash guarda también el stat que lo describe** (`file_size_bytes` + `file_mtime_ns`):
importador, adoptador, reenlace, re-triaje y el reemplazo del etiquetador (B6).

NULL en filas existentes = línea de base sin fijar: el primer rescan re-tría esas rutas una vez y fija el
stat. Sin default: no se inventa un instante que no se midió.

Downgrade: quita la columna; no hay dato que conservar fuera de ella.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("file_mtime_ns", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "file_mtime_ns")
