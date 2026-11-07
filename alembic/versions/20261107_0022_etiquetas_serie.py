# ruff: noqa: E501
"""Etiquetas por serie (BL-ETQ1a, #403): namespace, name_norm y series_tags.

Revision ID: 0022
Revises: 0021

Reutiliza `tags`/`issue_tags` (0001) y añade `series_tags`; no crea tablas
`tag`/`serie_tag`. El único namespace visible del MVP es `etiqueta` (D-1).
La normalización SQL `f_tag_norm` es espejo de `services/etiquetas.py::normalize_tag`;
`f_unaccent` ya existe desde 0006. `pg_trgm` ya está instalada desde 0001.

Downgrade: borra `series_tags` (sus asignaciones son lo nuevo y se pierden),
elimina índices/checks/columnas/función y recrea el UNIQUE global de `tags.name`.
No toca `issue_tags`, `series`, `genres` ni las extensiones.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Función de normalización (misma cadena que f_title_norm pero SIN quitar
    # artículos ni puntos entre letras: "The Walking Dead" conserva "the").
    op.execute("""
        CREATE OR REPLACE FUNCTION f_tag_norm(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$
            SELECT btrim(regexp_replace(
                regexp_replace(lower(f_unaccent($1)), '[^[:alnum:] ]', ' ', 'g'),
                '\\s+', ' ', 'g'
            ))
        $$
    """)

    # tags: namespace nullable → backfill → NOT NULL + CHECK.
    op.add_column("tags", sa.Column("namespace", sa.String(16), nullable=True))
    op.execute("UPDATE tags SET namespace = 'etiqueta' WHERE namespace IS NULL")
    op.alter_column("tags", "namespace", nullable=False, server_default="etiqueta")
    op.create_check_constraint("ck_tags_namespace", "tags", "namespace IN ('etiqueta')")

    # name_norm generada; el UNIQUE global de name deja paso al compuesto.
    op.execute(
        "ALTER TABLE tags ADD COLUMN name_norm TEXT "
        "GENERATED ALWAYS AS (f_tag_norm(name)) STORED"
    )
    op.drop_constraint("tags_name_key", "tags", type_="unique")
    op.create_unique_constraint("uq_tags_namespace_name_norm", "tags",
                                ["namespace", "name_norm"])
    op.create_check_constraint(
        "ck_tags_nombre", "tags",
        "char_length(name) BETWEEN 1 AND 64 AND name_norm <> ''",
    )
    op.create_index("ix_tags_name_norm_trgm", "tags", ["name_norm"],
                    postgresql_using="gin", postgresql_ops={"name_norm": "gin_trgm_ops"})

    op.create_table(
        "series_tags",
        sa.Column("series_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("weight", sa.SmallInteger, nullable=True),
        sa.Column("oculta", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "source IN ('comic_vine','gcd','anilist','tebeosfera','comicinfo_xml','manual')",
            name="ck_series_tags_source",
        ),
        sa.CheckConstraint("weight IS NULL OR weight BETWEEN 0 AND 100",
                           name="ck_series_tags_weight"),
    )
    op.create_index(
        "ix_series_tags_tag_visibles", "series_tags", ["tag_id", "series_id"],
        unique=False, postgresql_where=sa.text("oculta = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_series_tags_tag_visibles", table_name="series_tags")
    op.drop_table("series_tags")

    op.drop_index("ix_tags_name_norm_trgm", table_name="tags")
    op.drop_constraint("ck_tags_nombre", "tags", type_="check")
    op.drop_constraint("uq_tags_namespace_name_norm", "tags", type_="unique")
    op.drop_column("tags", "name_norm")
    op.drop_constraint("ck_tags_namespace", "tags", type_="check")
    op.drop_column("tags", "namespace")
    op.create_unique_constraint("tags_name_key", "tags", ["name"])
    op.execute("DROP FUNCTION IF EXISTS f_tag_norm(text)")
