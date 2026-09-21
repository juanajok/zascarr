"""Matcher metadata fixes — peer review v2 (H1 + H2 + H3).

Revision ID: 0006
Revises: 0005

H1 — Tildes en el matcher (exact-match imposible con titulos acentuados):
  matcher.find_series normaliza en Python (NFKD, sin acentos, sin puntuacion,
  sin articulo inicial/pospuesto, sin puntos de abreviacion) pero comparaba
  contra lower(title) CRUDO de la BD. Esta migracion crea la funcion SQL
  f_title_norm() (espejo inmutable de core.matcher.normalize_title) y la
  columna generada almacenada series.title_norm. El matcher pasa a consultar
  contra title_norm y todo casa ("Nausicaa" file vs "Nausicaä" BD;
  "Sandman, The" = "The Sandman"; "S.H.I.E.L.D." = "shield").

  Detalle tecnico: public.unaccent() es STABLE, no IMMUTABLE, asi que no se
  puede usar directamente en una columna generada ni en un indice de
  expresion. f_unaccent() es el wrapper IMMUTABLE estandar para eso.

  Paridad con Python verificada campo a campo contra una bateria de titulos
  patologicos (no solo los que traia la propuesta original del review),
  encontrando y corrigiendo dos divergencias reales antes de dar la funcion
  por buena:
  1. normalize_title() quita los puntos entre letras ANTES de la limpieza
     general de puntuacion ("S.H.I.E.L.D." -> "SHIELD", no "S H I E L D");
     f_title_norm() replica ese paso con un regexp_replace de look-around
     antes de colapsar el resto de puntuacion a espacios — si no, diverge
     justo en tests/test_naming_core.py::test_abreviaciones_shield.
  2. El patron de articulo inicial en Python acepta fin-de-cadena ademas de
     espacio (`(?:\\s+|$)`) para cubrir un titulo que ES solo el articulo
     ("The" a secas -> ""); la primera version de f_title_norm() exigia
     espacio despues del articulo, así que "The" se quedaba como "the" en
     vez de "" — diverge de tests/test_naming_core.py::
     test_titulo_solo_articulo. Corregido con el mismo `(?:\\s+|$)`.

  Divergencia conocida y aceptada (documentada aqui a proposito): el matcher
  Python solo quita el articulo POSPUESTO si iba tras coma ("Sandman, The");
  f_title_norm lo quita tambien sin coma ("Sandman The"). Colisiona solo con
  titulos que terminan literalmente en un articulo sin coma; caso borde
  inexistente en la practica y asumido.

H2 — Cache negativa del enricher:
  Antes: una serie sin match entraba en enrich_series_batch en CADA ciclo
  para siempre (todas las FK de fuente a NULL y metadata_source a NULL),
  quemando rate limit de APIs externas en busquedas condenadas.
  Ahora: enrichment_attempted_at marca "lo intentamos"; la seleccion pasa a
  `enrichment_attempted_at IS NULL OR enrichment_attempted_at < now() - 30d`
  (30 dias: una serie recien publicada puede aparecer en la fuente tarde,
  conviene reintentar a plazo largo, no cada 2 horas).
  El enricher debe hacer `series.enrichment_attempted_at = utcnow()` en cada
  intento, TANTO si hay match como si no (ese es el punto de H2).

H3 — locked_fields donde toca:
  El diseno (dialecto lock granular vs bloqueo total por 'manual') ponia
  locked_fields en las entidades enriquecibles; por un descuido de la
  migracion 0001 aterrizo SOLO en wishlist, donde ningun codigo la lee.
  Ahora va a series/issues/creators/characters y sale de wishlist.
  Caso de uso inmediato (tension H3 del review): review.assign_to_series crea
  el Issue al vuelo con metadata_source='manual' para proteger LA ASIGNACION
  — pero eso bloqueaba tambien sinopsis/portada/creditos que el enricher
  deberia rellenar. Con locked_fields=['series_id','issue_number'] el
  enriquecimiento de contenido sigue funcionando.

CAMBIOS DE CODIGO QUE ACOMPANAN A ESTA MIGRACION (no van solos, ver
matcher.py / enricher.py / review.py / models/__init__.py en el mismo commit):

  matcher.py — find_series pasa a usar la columna nueva (title_norm en vez
    de lower(title); similarity()/% sobre title_norm en vez de lower(title)).

  enricher.py — la seleccion de pendientes en series/issues filtra por
    enrichment_attempted_at, y cada intento (con o sin match) lo actualiza.
    apply_series_match respeta locked_fields ademas de metadata_source
    ='manual' (bloqueo total).

  review.py — assign_to_series: el Issue creado al vuelo ya no usa
    metadata_source='manual'; usa locked_fields=['series_id','issue_number']
    para proteger solo la asignacion, no todo el registro.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ENRICHABLE_TABLES = ("series", "issues", "creators", "characters")


def upgrade() -> None:
    # ── H1: unaccent + funcion de normalizacion + columna generada ───────
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # Wrapper inmutable: unaccent() es STABLE y por tanto inutilizable en
    # columnas generadas/indices. El doble argumento hace la funcion
    # estable a cambios de configuracion del diccionario.
    op.execute("""
        CREATE OR REPLACE FUNCTION f_unaccent(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent', $1) $$
    """)

    # Espejo SQL de core.matcher.normalize_title. SI CAMBIA UNO, CAMBIA EL
    # OTRO: un test de paridad (normalizar N titulos en Python y comparar
    # contra f_title_norm en la DB de tests) vive en tests/test_title_norm.py.
    #
    # Orden de pasos (debe reflejar exactamente el de normalize_title):
    #   1. lower + f_unaccent (NFKD sin acentos, en Python; unaccent en SQL)
    #   2. quitar puntos ENTRE alfanumericos sin dejar espacio: "s.h.i.e.l.d."
    #      -> "shield", no "s h i e l d" (paso _ABBREV en Python)
    #   3. quitar articulo inicial
    #   4. quitar articulo pospuesto
    #   5. resto de puntuacion -> espacio
    #   6. colapsar espacios y btrim
    op.execute("""
        CREATE OR REPLACE FUNCTION f_title_norm(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$
            SELECT btrim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                lower(f_unaccent($1)),
                '(?<=[[:alnum:]])\\.(?=[[:alnum:]])', '', 'g'),
                '^(the|el|la|los|las|le|les|il|lo|die|der|das)(?:\\s+|$)', ''),
                '\\s*,?\\s+(the|el|la|los|las|le|les|il|lo)$', ''),
                '[^[:alnum:] ]', ' ', 'g'),
                '\\s+', ' ', 'g'))
        $$
    """)

    op.add_column("series", sa.Column(
        "title_norm", sa.Text,
        sa.Computed("f_title_norm(title)", persisted=True),
        comment="Espejo de core.matcher.normalize_title via f_title_norm(). "
                "Fuente unica de verdad para matching exacto y pg_trgm.",
    ))
    # Sustituye al indice trgm sobre title crudo: el fuzzy ahora opera sobre
    # el valor ya normalizado (acentos fuera, puntuacion fuera), que es como
    # llega :norm desde Python.
    op.execute("DROP INDEX IF EXISTS idx_series_title_trgm")
    op.execute(
        "CREATE INDEX idx_series_title_norm_trgm "
        "ON series USING GIN (title_norm gin_trgm_ops)"
    )

    # ── H2: cache negativa del enricher ──────────────────────────────────
    for table in ("series", "issues"):
        op.add_column(table, sa.Column(
            "enrichment_attempted_at", sa.DateTime(timezone=True),
            comment="Ultimo intento de enriquecimiento (con o sin exito). "
                    "NULL = nunca intentado. Seleccion: NULL o > 30 dias.",
        ))

    # ── H3: locked_fields en las entidades enriquecibles, fuera de wishlist
    for table in ENRICHABLE_TABLES:
        op.add_column(table, sa.Column(
            "locked_fields", ARRAY(sa.String), server_default="{}",
            nullable=False,
            comment="Campos que el enricher NUNCA sobrescribe aunque el "
                    "registro no sea 'manual'.",
        ))
    # La copia en wishlist (error de la 0001) no la lee ninguna ruta de
    # codigo; se elimina. Si existiera algun valor, no lo consume nadie.
    op.drop_column("wishlist", "locked_fields")


def downgrade() -> None:
    op.add_column("wishlist", sa.Column(
        "locked_fields", ARRAY(sa.String), server_default="{}",
    ))
    for table in ENRICHABLE_TABLES:
        op.drop_column(table, "locked_fields")

    for table in ("series", "issues"):
        op.drop_column(table, "enrichment_attempted_at")

    op.execute("DROP INDEX IF EXISTS idx_series_title_norm_trgm")
    op.execute(
        "CREATE INDEX idx_series_title_trgm ON series USING GIN (title gin_trgm_ops)"
    )
    op.drop_column("series", "title_norm")
    op.execute("DROP FUNCTION IF EXISTS f_title_norm(text)")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
