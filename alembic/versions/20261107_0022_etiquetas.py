# ruff: noqa: E501
"""Etiquetas manuales por serie (BL-ETQ1a, #403): namespace, normalización y `series_tags`.

Revision ID: 0022
Revises: 0021

Por qué existe: `tags`/`issue_tags` existen desde 0001 pero están dormidas, y el MVP etiqueta a
nivel de **serie** (no de número). Esta migración:

1. añade `tags.namespace` (único valor visible en el MVP: `etiqueta`, D-1) y la columna generada
   `tags.name_norm`, espejo SQL de `services/etiquetas.py::normalize_tag`;
2. sustituye el UNIQUE global de `tags.name` por `UNIQUE (namespace, name_norm)` y añade el índice
   GIN trigram que usan las sugerencias;
3. crea `series_tags` (asignación serie↔etiqueta con `source`, `weight` y `oculta`).

`issue_tags` **no se toca**: queda dormida para una fase posterior. `Series.genres` e
`Issue.characters` tampoco se tocan (los géneros y personajes no se duplican como etiquetas).

`namespace` se añade en tres pasos (nullable → backfill → NOT NULL) porque no se asume que la tabla
esté vacía, aunque por construcción lo esté: una instalación antigua podría haber escrito en `tags`.

Downgrade: borra `series_tags` (las asignaciones se pierden: son lo nuevo), deduplica `tags` por
`name` conservando la fila con más referencias en `issue_tags` (empate: menor `id::text`) para poder
recrear el UNIQUE global, y elimina índices, checks, `name_norm`, `namespace` y `f_tag_norm`. No
toca `issue_tags`, `series`, `genres` ni `pg_trgm`/`unaccent`. La pérdida de asignaciones es
deliberada y queda documentada aquí, como en 0020.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Función de normalización (espejo de services/etiquetas.py::normalize_tag) ──────────
    # `f_unaccent` existe desde 0006. Se conserva el artículo inicial (a diferencia de
    # `f_title_norm`): «The Walking Dead» ≠ «walking dead».
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION f_tag_norm(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$
            SELECT btrim(regexp_replace(
                regexp_replace(lower(f_unaccent($1)), '[^[:alnum:] ]', ' ', 'g'),
                '\s+', ' ', 'g'))
        $$
        """
    )

    # ── 2. tags.namespace (nullable → backfill → NOT NULL → CHECK) ───────────────────────────
    op.add_column("tags", sa.Column("namespace", sa.String(16), nullable=True))
    op.execute("UPDATE tags SET namespace = 'etiqueta' WHERE namespace IS NULL")
    op.alter_column("tags", "namespace", nullable=False, server_default="etiqueta")
    op.create_check_constraint(
        "ck_tags_namespace", "tags", "namespace IN ('etiqueta')"
    )

    # ── 3. tags.name_norm generada ────────────────────────────────────────────────────────────
    op.add_column(
        "tags",
        sa.Column(
            "name_norm",
            sa.Text(),
            sa.Computed("f_tag_norm(name)", persisted=True),
        ),
    )

    # ── 4. Unicidad por (namespace, name_norm) y validación de longitud ──────────────────────
    op.drop_constraint("tags_name_key", "tags", type_="unique")
    op.create_unique_constraint(
        "uq_tags_namespace_name_norm", "tags", ["namespace", "name_norm"]
    )
    op.create_check_constraint(
        "ck_tags_name",
        "tags",
        "char_length(name) BETWEEN 1 AND 64 AND name_norm <> ''",
    )

    # ── 5. Índice trigram para sugerencias ────────────────────────────────────────────────────
    op.create_index(
        "ix_tags_name_norm_trgm",
        "tags",
        ["name_norm"],
        postgresql_using="gin",
        postgresql_ops={"name_norm": "gin_trgm_ops"},
    )

    # ── 6. series_tags ────────────────────────────────────────────────────────────────────────
    op.create_table(
        "series_tags",
        sa.Column(
            "series_id",
            UUID(as_uuid=True),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source", sa.String(20), nullable=False, server_default="manual"
        ),
        sa.Column("weight", sa.SmallInteger(), nullable=True),
        sa.Column(
            "oculta", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source IN ('comic_vine','gcd','anilist','tebeosfera','comicinfo_xml','manual')",
            name="ck_series_tags_source",
        ),
        sa.CheckConstraint(
            "weight IS NULL OR weight BETWEEN 0 AND 100",
            name="ck_series_tags_weight",
        ),
    )
    # Índice parcial para facetas y filtros: solo las asignaciones visibles.
    op.create_index(
        "ix_series_tags_tag_visible",
        "series_tags",
        ["tag_id", "series_id"],
        postgresql_where=sa.text("oculta = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_series_tags_tag_visible", table_name="series_tags")
    op.drop_table("series_tags")

    op.drop_index("ix_tags_name_norm_trgm", table_name="tags")
    op.drop_constraint("ck_tags_name", "tags", type_="check")
    op.drop_constraint("uq_tags_namespace_name_norm", "tags", type_="unique")

    # Recrear el UNIQUE global de `name` exige resolver los duplicados que el nuevo modelo
    # permitía: se conserva la fila con más referencias en `issue_tags` (empate: menor id) y se
    # reasignan las referencias de las demás antes de borrarlas.
    op.execute(
        """
        WITH ranked AS (
            SELECT t.id, t.name,
                   row_number() OVER (
                       PARTITION BY t.name
                       ORDER BY (SELECT count(*) FROM issue_tags it WHERE it.tag_id = t.id) DESC,
                                t.id::text
                   ) AS rn
            FROM tags t
        ),
        keep AS (SELECT id, name FROM ranked WHERE rn = 1),
        dup AS (SELECT id, name FROM ranked WHERE rn > 1)
        UPDATE issue_tags it
        SET tag_id = k.id
        FROM dup d
        JOIN keep k ON k.name = d.name
        WHERE it.tag_id = d.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT t.id,
                   row_number() OVER (
                       PARTITION BY t.name
                       ORDER BY (SELECT count(*) FROM issue_tags it WHERE it.tag_id = t.id) DESC,
                                t.id::text
                   ) AS rn
            FROM tags t
        )
        DELETE FROM tags WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    op.create_unique_constraint("tags_name_key", "tags", ["name"])

    op.drop_constraint("ck_tags_namespace", "tags", type_="check")
    op.drop_column("tags", "name_norm")
    op.drop_column("tags", "namespace")
    op.execute("DROP FUNCTION IF EXISTS f_tag_norm(text)")
