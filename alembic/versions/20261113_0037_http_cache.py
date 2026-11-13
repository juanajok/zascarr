"""Caché HTTP condicional en PostgreSQL (SCR1, migración 0037).

Tabla `http_cache`: una fila por URL canónica y método. Guarda la respuesta positiva
comprimida (zlib, ≤2 MiB) con sus validadores (`etag`/`last_modified`) y dos horizontes:
`fresh_until` (se sirve sin red) y `retain_until` (hasta ahí se revalida; después se purga).
Las negativas cortas (`404`/`410` de la fuente o `missingtitle` de MediaWiki) no guardan
cuerpo. El `url_canonical` redacta credenciales (`api_key`, `token`…): el hash va sobre la
URL completa, de modo que dos claves distintas no colapsan y el secreto no llega a la BD.

Aditiva y reversible: no toca datos existentes ni crea tipos nuevos.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "http_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("url_canonical", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("is_negative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("body_zlib", sa.LargeBinary(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url_hash", name="uq_http_cache_url_hash"),
    )
    op.create_index("ix_http_cache_domain", "http_cache", ["domain"])
    op.create_index("ix_http_cache_retain_until", "http_cache", ["retain_until"])


def downgrade() -> None:
    op.drop_index("ix_http_cache_retain_until", table_name="http_cache")
    op.drop_index("ix_http_cache_domain", table_name="http_cache")
    op.drop_table("http_cache")
