"""fix_title_norm_search_path — restauración de pg_dump rompía f_title_norm.

Revision ID: 0009
Revises: 0008

Hallazgo E2E (release 1.0): restaurar un pg_dump de esta base de datos en
una BD limpia fallaba siempre al crear/usar f_title_norm(), tumbando la
tabla series entera y todo lo que depende de ella (scripts/rollback.sh
abortaba con ON_ERROR_STOP=1 en el primer intento).

Causa raíz confirmada (no es un problema de orden de volcado, como se
sospechó al principio): pg_dump antepone
`SELECT pg_catalog.set_config('search_path', '', false)` al principio de
cada restore, para forzar que todo vaya cualificado por esquema. La
migración 0006 definió f_title_norm() llamando a `f_unaccent($1)` SIN
cualificar ("f_unaccent", no "public.f_unaccent") — con search_path vacío
esa referencia no resuelve, y CREATE FUNCTION/su inlining posterior falla
con "function f_unaccent(text) does not exist" aunque f_unaccent SÍ exista
en public. Reproducido de forma aislada contra Postgres 15 real antes de
escribir este fix.

0006 ya está aplicada (CLAUDE.md §7: no se reescribe una migración
aplicada) — este fix re-declara la función con CREATE OR REPLACE en vez
de tocar 0006. El cuerpo es idéntico al original, solo cambia
`f_unaccent($1)` por `public.f_unaccent($1)`.
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        CREATE OR REPLACE FUNCTION f_title_norm(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$
            SELECT btrim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                lower(public.f_unaccent($1)),
                '(?<=[[:alnum:]])\.(?=[[:alnum:]])', '', 'g'),
                '^(the|el|la|los|las|le|les|il|lo|die|der|das)(?:\s+|$)', ''),
                '\s*,?\s+(the|el|la|los|las|le|les|il|lo)$', ''),
                '[^[:alnum:] ]', ' ', 'g'),
                '\s+', ' ', 'g'))
        $$
    """)


def downgrade() -> None:
    # Vuelve al cuerpo original de 0006 (sin cualificar) — reproduce el bug
    # a propósito, coherente con "downgrade revierte exactamente lo que
    # aplicó la revisión".
    op.execute(r"""
        CREATE OR REPLACE FUNCTION f_title_norm(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$
            SELECT btrim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                lower(f_unaccent($1)),
                '(?<=[[:alnum:]])\.(?=[[:alnum:]])', '', 'g'),
                '^(the|el|la|los|las|le|les|il|lo|die|der|das)(?:\s+|$)', ''),
                '\s*,?\s+(the|el|la|los|las|le|les|il|lo)$', ''),
                '[^[:alnum:] ]', ' ', 'g'),
                '\s+', ' ', 'g'))
        $$
    """)
