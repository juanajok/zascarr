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
    op.create_index("uq_creators_name_norm", "creators", ["name_norm"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_creators_name_norm", table_name="creators")
    op.drop_column("creators", "name_norm")
    op.execute("DROP FUNCTION IF EXISTS f_creator_name_norm(text)")
