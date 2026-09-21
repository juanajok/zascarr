"""Wishlist.download_ref/download_backend — D1 (orquestador).

Revision ID: 0007
Revises: 0006

Observabilidad de qué se envió a qué backend de descarga (Transmission o
aMule) para un item de la wishlist: hash de torrent, o hash ed2k extraído
de la propia URL ed2k://. No participan en detectar si algo terminó de
descargarse/importarse — eso se hace comprobando si ya existe un File
enlazado al Issue/Series pedido (ver Orchestrator.check_completions),
agnóstico de backend y sin depender de scraping de estado de aMule/
Transmission.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wishlist", sa.Column("download_ref", sa.String(255)))
    op.add_column("wishlist", sa.Column("download_backend", sa.String(20)))


def downgrade() -> None:
    op.drop_column("wishlist", "download_backend")
    op.drop_column("wishlist", "download_ref")
