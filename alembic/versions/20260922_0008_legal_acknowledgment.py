"""legal_acknowledgment — blindaje legal.

Revision ID: 0008
Revises: 0007

Sin user_id ni FK a ninguna tabla de usuarios: SecuenciArr es una
herramienta de un solo operador, sin autenticación (ver docs/BACKLOG.md,
Épica A). "¿Se ha aceptado el aviso legal?" es "¿existe una fila con
legal_version == la versión actual?" — un estado único del sistema, no
por usuario. legal_version es el hash del propio LEGAL.md empaquetado
(ver services/legal.py), no una constante que haya que recordar subir a
mano cada vez que cambie el fichero.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_acknowledgments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("legal_version", sa.String(64), nullable=False),
    )
    op.create_index("ix_legal_acknowledgments_legal_version", "legal_acknowledgments", ["legal_version"])


def downgrade() -> None:
    op.drop_index("ix_legal_acknowledgments_legal_version", table_name="legal_acknowledgments")
    op.drop_table("legal_acknowledgments")
