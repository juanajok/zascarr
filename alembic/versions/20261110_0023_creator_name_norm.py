"""#448 BL-INF2: nombre normalizado único de Creator.

Normaliza minúsculas, acentos y espacios. Es una columna generada por
Postgres para que cualquier alta (servicio, enricher, importación) quede
normalizada sin depender de que cada camino se acuerde.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION f_creator_name_norm(value text) RETURNS text
        LANGUAGE sql IMMUTABLE AS $$
          SELECT regexp_replace(
            lower(translate(btrim(value),
              'ÁÉÍÓÚÜÑÇáéíóúüñç', 'AEIOUUNCAEIOUUNC')),
            '\\s+', ' ', 'g')
        $$
    """)
    op.add_column("creators", sa.Column(
        "name_norm", sa.String(255),
        sa.Computed("f_creator_name_norm(name)", persisted=True)))
    # Bases con datos: antes del índice único hay que fusionar los creadores que
    # normalizan igual (p. ej. «Ana» y «ana»). Se conserva el más antiguo y se
    # repuntan sus créditos, con ON CONFLICT para no chocar con el PK
    # (issue_id, creator_id, role).
    op.execute("""
        WITH ranked AS (
            SELECT id, name_norm,
                   first_value(id) OVER (
                       PARTITION BY name_norm ORDER BY created_at NULLS FIRST, id
                   ) AS keep_id,
                   row_number() OVER (
                       PARTITION BY name_norm ORDER BY created_at NULLS FIRST, id
                   ) AS rn
            FROM creators WHERE name_norm IS NOT NULL
        )
        INSERT INTO issue_creators (issue_id, creator_id, role)
        SELECT ic.issue_id, r.keep_id, ic.role
        FROM issue_creators ic JOIN ranked r ON r.id = ic.creator_id
        WHERE r.rn > 1
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id, name_norm,
                   row_number() OVER (
                       PARTITION BY name_norm ORDER BY created_at NULLS FIRST, id
                   ) AS rn
            FROM creators WHERE name_norm IS NOT NULL
        )
        DELETE FROM issue_creators ic USING ranked r
        WHERE ic.creator_id = r.id AND r.rn > 1
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id, name_norm,
                   row_number() OVER (
                       PARTITION BY name_norm ORDER BY created_at NULLS FIRST, id
                   ) AS rn
            FROM creators WHERE name_norm IS NOT NULL
        )
        DELETE FROM creators c USING ranked r
        WHERE c.id = r.id AND r.rn > 1
    """)
    op.create_index("uq_creators_name_norm", "creators", ["name_norm"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_creators_name_norm", table_name="creators")
    op.drop_column("creators", "name_norm")
    op.execute("DROP FUNCTION IF EXISTS f_creator_name_norm(text)")
