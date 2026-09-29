"""Integridad — `File.original_sha256`: el hash del fichero tal como se importó.

Revision ID: 0016
Revises: 0015

`File.sha256_hash` hace dos trabajos incompatibles (ficha
`benchmark-integridad-hash-dedupe`): identidad del original para el dedupe, y
huella de lo que hay ahora en disco para B6. Al escribir `ComicInfo.xml`, B6
cambia los bytes y recalcula `sha256_hash`, así que el mismo tebeo entrante deja
de coincidir y se reimporta como duplicado.

`original_sha256` guarda el hash **pre-reescritura** y nunca se sobrescribe. Es
nullable y con índice **no único**:

- nullable porque los ficheros ya etiquetados antes de esta migración no pueden
  reconstruir su hash original — se deja NULL y se dice, no se inventa;
- no único por el mismo motivo que `sha256_hash` (dos copias conocidas del mismo
  contenido deben poder representarse).

Nombre del índice: `idx_files_original_sha256` (siguiendo a `idx_files_hash` de
0001). El modelo declara `index=True`, que SQLAlchemy nombra
`ix_files_original_sha256` en su metadata — es el mismo desajuste ya existente
con `sha256_hash`/`idx_files_hash`; las migraciones son one-shot y no se
reescriben, así que un autogenerate futuro podrá proponer renombrarlo.
"""
import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("original_sha256", sa.String(64), nullable=True))
    op.create_index("idx_files_original_sha256", "files", ["original_sha256"])


def downgrade() -> None:
    op.drop_index("idx_files_original_sha256", table_name="files")
    op.drop_column("files", "original_sha256")
