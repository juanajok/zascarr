"""Referencia normalizada de series e issues (fase 1, 2026-11-12).

Migración aditiva. No toca la identidad editorial (`Series.id`, `Issue.id`,
IDs externos) ni renombra archivos.

Añade:
- `series.volume`: volumen/edición cuando se conoce.
- `series.reference_name`: nombre normalizado de serie, generado.
- `issues.number_key`: clave canónica del número dentro de la serie.
- Vista `v_issue_reference`: referencia de issue (serie + número).

`sort_title` ya existía; se rellena para las filas que lo tengan vacío.
El `number_key` conserva sufijos, decimales y especiales, y quita ceros a la
izquierda: `012a` -> `12a`, `023.1` -> `23.1`, `001` -> `1`. No es una clave
única ni sustituye a `issue_number`.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clave canónica del número. No usa unaccent ni el título: solo el número.
    op.execute(r"""
        CREATE OR REPLACE FUNCTION f_number_key(value text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
            SELECT CASE
                WHEN value IS NULL OR btrim(value) = '' THEN NULL
                ELSE regexp_replace(lower(btrim(value)), '^0+(?=\d)', '')
            END
        $$
    """)

    # Referencia humana de serie. Si el título ya lleva «Vol. N», no se
    # duplica; si no, se añade el volumen conocido. El año va entre paréntesis.
    op.execute(r"""
        CREATE OR REPLACE FUNCTION f_series_reference(
            title text, start_year integer, volume integer
        )
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
            SELECT CASE
                WHEN title IS NULL OR btrim(title) = '' THEN NULL
                ELSE btrim(title)
                    || CASE WHEN start_year IS NOT NULL
                            THEN ' (' || start_year || ')' ELSE '' END
                    || CASE WHEN volume IS NOT NULL
                            AND btrim(title) !~* '\m(vol(umen)?|v|tomo)\.?\s*[0-9]+\M'
                            THEN ' Vol. ' || volume ELSE '' END
            END
        $$
    """)

    # Referencia humana de issue. Sin número no inventa uno: usa el título
    # editorial si existe y, si no, deja la serie como referencia.
    op.execute(r"""
        CREATE OR REPLACE FUNCTION f_issue_reference(
            series_reference text, number_key text, issue_title text
        )
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
            SELECT CASE
                WHEN series_reference IS NULL THEN NULL
                WHEN number_key IS NOT NULL
                    THEN series_reference || ' #' || number_key
                WHEN issue_title IS NOT NULL AND btrim(issue_title) <> ''
                    THEN series_reference || ' — ' || btrim(issue_title)
                ELSE series_reference
            END
        $$
    """)

    op.add_column("series", sa.Column("volume", sa.SmallInteger(), nullable=True))
    op.add_column("series", sa.Column(
        "reference_name", sa.Text(),
        sa.Computed("public.f_series_reference(title, start_year, volume)", persisted=True),
        comment="Referencia humana derivada; no única ni identidad.",
    ))
    op.add_column("issues", sa.Column(
        "number_key", sa.Text(),
        sa.Computed("public.f_number_key(issue_number)", persisted=True),
        comment="Clave canónica del número dentro de la edición; no única.",
    ))
    op.execute("CREATE INDEX ix_issues_series_number_key ON issues (series_id, number_key)")

    # Relleno conservador de atributos de presentación que no son identidad.
    # No se deduce `start_year`: requiere una fuente o la carpeta, y se hará
    # aparte. `volume` solo se rellena cuando el título lo declara de forma
    # explícita; nunca se inventa.
    op.execute(r"""
        UPDATE series
        SET sort_title = btrim(regexp_replace(
            title, '^(the|el|la|los|las|le|les|il|lo|die|der|das)\s+', '', 'i'))
        WHERE sort_title IS NULL
    """)
    # `exec_driver_sql`: SQLAlchemy interpretaría `(?:` del regex como
    # parámetros `:...` si se pasara por `text()`.
    op.get_bind().exec_driver_sql(r"""
        UPDATE series
        SET volume = (regexp_match(
            title, '(?i)\m(?:vol(?:umen)?\.?|v|tomo)\s*([0-9]+)\M'))[1]::integer
        WHERE volume IS NULL
          AND title ~* '\m(?:vol(?:umen)?\.?|v|tomo)\s*[0-9]+\M'
    """)

    op.execute("""
        CREATE VIEW v_issue_reference AS
        SELECT
            i.id AS issue_id,
            i.series_id,
            s.title AS series_title,
            s.reference_name AS series_reference,
            i.issue_number,
            i.number_key,
            i.title AS issue_title,
            public.f_issue_reference(s.reference_name, i.number_key, i.title) AS reference_name
        FROM issues i
        JOIN series s ON s.id = i.series_id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_issue_reference")
    op.execute("DROP INDEX IF EXISTS ix_issues_series_number_key")
    op.drop_column("issues", "number_key")
    op.drop_column("series", "reference_name")
    op.drop_column("series", "volume")
    op.execute("DROP FUNCTION IF EXISTS f_issue_reference(text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS f_series_reference(text, integer, integer)")
    op.execute("DROP FUNCTION IF EXISTS f_number_key(text)")
