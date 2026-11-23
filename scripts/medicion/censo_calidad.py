# ruff: noqa: E501
#!/usr/bin/env python3
"""censo_calidad.py — catálogo de comprobaciones de calidad del dato de ZascArr.

Solo lectura: la conexión entera corre dentro de `BEGIN TRANSACTION READ ONLY`,
así que Postgres rechaza cualquier escritura aunque este script se equivocara.
No vuelca el catálogo: imprime agregados y una muestra pequeña. Por defecto
**seudonimiza** títulos y rutas (hash SHA-256 truncado); con `--local` enseña
los valores originales para que el PO etiquete a mano (esa salida no se pega
en un issue).

Qué mide: el catálogo de `docs/design/calidad-dato-*.md`, una fila por
comprobación con id estable:

    [B1] Homónimos resueltos a ciegas — S1
      Población: 412 series con id de fuente · Casos: 7 (1,7 %)
      · 9f2c1a03  <detalle seudonimizado>

Uso:

    DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \\
        python3 scripts/medicion/censo_calidad.py            # COMPARTIBLE
    DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --local
    DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --json > censo.json
    DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --perfil
    DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --solo B1,A4
    DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --local \\
        --csv ~/calidad-muestra.csv --muestreo 20 --semilla 42

La variable `TEST_DATABASE_URL` también vale. No escribe en la base; el CSV
(--csv) es un fichero local tuyo y no se versiona.

Salida estable para comparar: `--json` ordena las comprobaciones por id e
incluye `huella`, un SHA-256 de los resultados (sin la fecha), para saber si
dos ejecuciones dicen lo mismo. Un cambio de `poblacion` o `casos` cambia la
huella; un cambio de muestra ordenada también.

Lo que NO mide este script (marcado NOT RUN en el informe): el número que
extrae el parser del nombre (C1/D1) y la existencia de copias locales de
portada (I3), porque exigen leer los nombres con la versión desplegada o
recorrer el disco. El catálogo deja la comprobación y el informe dice por qué
no se ejecutó.

Sin dependencias nuevas: `asyncpg`, como `censo_identidad.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


#: Claves cuyo VALOR identifica una obra o una ruta: se seudonimizan por defecto.
#: Un hash truncado no es anonimización fuerte (se puede comprobar contra un
#: diccionario de títulos conocidos), así que se llama seudonimización.
_CLAVES_SECRETAS = frozenset({
    "titulo", "titulo_a", "titulo_b", "titulo_serie", "titulo_fuente",
    "nombre", "nombre_a", "nombre_b", "file_name", "ruta", "file_path",
    "sinopsis", "descripcion", "texto", "detalle", "patron", "carpeta",
    "serie", "serie_a", "serie_b", "editorial", "editorial_a", "editorial_b",
    "publisher", "imprint", "creador", "creador_a", "creador_b",
    "raiz", "raiz_a", "raiz_b", "ruta_normalizada", "carpeta", "rutas",
    "file_names", "nombres", "sinopsis_fuente",
})


def _seudonimo(valor: object, largo: int = 8) -> str:
    if valor is None or valor == "":
        return "(vacío)"
    return hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:largo]


def _json_estable(valor: object) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def _seudonimizar(detalle: Any) -> Any:
    """Copia el detalle cambiando por seudónimos los valores de las claves secretas.

    Una clave secreta con lista (`rutas`, `file_names`) seudonimiza cada elemento:
    si no, una lista de rutas se colaría tal cual en la salida compartible."""
    if isinstance(detalle, dict):
        salida = {}
        for k, v in detalle.items():
            if k in _CLAVES_SECRETAS:
                if isinstance(v, list):
                    salida[k] = [_seudonimo(x) if not isinstance(x, (dict, list))
                                 else _seudonimizar(x) for x in v]
                elif isinstance(v, dict):
                    salida[k] = _seudonimizar(v)
                else:
                    salida[k] = _seudonimo(v)
            else:
                salida[k] = _seudonimizar(v)
        return salida
    if isinstance(detalle, list):
        return [_seudonimizar(v) for v in detalle]
    return detalle


def _fila(valor: object) -> Any:
    """asyncpg devuelve UUID/fechas/Decimal: JSON no los serializa."""
    if isinstance(valor, dict):
        return {k: _fila(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_fila(v) for v in valor]
    if isinstance(valor, (datetime,)):
        return valor.isoformat()
    if isinstance(valor, (bytes, bytearray)):
        return "<bytes>"
    if hasattr(valor, "hex") and type(valor).__name__ == "UUID":
        return str(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


@dataclass(frozen=True)
class Check:
    """Una comprobación del catálogo.

    `poblacion` es un escalar (cuántas filas podrían tener el defecto);
    `casos` devuelve dos columnas: `caso_id` (texto estable) y `detalle`
    (JSONB). El runner ordena por `caso_id` y recorta la muestra.
    """

    id: str
    titulo: str
    severidad: str
    poblacion: str
    casos: str
    nota: str = ""
    #: Etiqueta que se escribe ANTES de mirar la muestra (defecto/legítimo/no sé).
    #: El PO rellena `etiqueta_po` en el CSV; esta columna evita el sesgo de
    #: confirmación y se puede cambiar por comprobación si la hipótesis difiere.
    hipotesis: str = "defecto"
    #: Tope de filas que se traen para contar. Si se alcanza, se avisa y se
    #: cuenta aparte con `SELECT count(*)` (evita traer un catálogo entero).
    tope: int = 5_000
    #: `False` = la comprobación no se puede ejecutar solo con SQL (parser,
    #: disco). Se informa como NOT RUN con el motivo.
    ejecutable: bool = True
    motivo_no_ejecutable: str = ""


# ── Perfil del dato (fase 1) ──────────────────────────────────────────────────
# Consultas de contexto, no defectos: recuentos, distribuciones y nulos.
# Ninguna toca el disco ni imprime títulos ni rutas.

PERFIL: list[tuple[str, str]] = [
    (
        "Recuento por tabla",
        """
        SELECT 'series' AS tabla, count(*) AS filas FROM series
        UNION ALL SELECT 'issues', count(*) FROM issues
        UNION ALL SELECT 'files', count(*) FROM files
        UNION ALL SELECT 'wishlist', count(*) FROM wishlist
        UNION ALL SELECT 'collections', count(*) FROM collections
        UNION ALL SELECT 'publishers', count(*) FROM publishers
        UNION ALL SELECT 'imprints', count(*) FROM imprints
        UNION ALL SELECT 'creators', count(*) FROM creators
        UNION ALL SELECT 'story_arcs', count(*) FROM story_arcs
        UNION ALL SELECT 'story_arc_issues', count(*) FROM story_arc_issues
        UNION ALL SELECT 'reading_progress', count(*) FROM reading_progress
        UNION ALL SELECT 'upgrade_proposals', count(*) FROM upgrade_proposals
        UNION ALL SELECT 'entity_source_records', count(*) FROM entity_source_records
        UNION ALL SELECT 'field_provenance', count(*) FROM field_provenance
        UNION ALL SELECT 'library_roots', count(*) FROM library_roots
        UNION ALL SELECT 'import_runs', count(*) FROM import_runs
        UNION ALL SELECT 'http_cache', count(*) FROM http_cache
        UNION ALL SELECT 'local_aliases', count(*) FROM local_aliases
        UNION ALL SELECT 'alias_importado', count(*) FROM alias_importado
        ORDER BY tabla
        """,
    ),
    (
        "Series por kind",
        "SELECT kind::text AS kind, count(*) AS series FROM series GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Series por tradición",
        "SELECT coalesce(tradition::text, '(sin tradición)') AS tradicion, count(*) AS series "
        "FROM series GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Series por metadata_source",
        "SELECT coalesce(metadata_source, '(sin fuente)') AS fuente, count(*) AS series "
        "FROM series GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Series por número de ids de fuente presentes",
        """
        SELECT n AS ids_de_fuente, count(*) AS series FROM (
          SELECT (comic_vine_id IS NOT NULL)::int + (anilist_id IS NOT NULL)::int
               + (tebeosfera_slug IS NOT NULL)::int + (gcd_id IS NOT NULL)::int
               + (metron_id IS NOT NULL)::int + (open_library_id IS NOT NULL)::int
               + (fandom_dc_slug IS NOT NULL)::int + (fandom_marvel_slug IS NOT NULL)::int AS n
          FROM series
        ) t GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "Issues por format",
        "SELECT coalesce(format::text, '(sin formato)') AS format, count(*) AS issues "
        "FROM issues GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Archivos por file_format (extensión declarada)",
        "SELECT file_format::text AS file_format, count(*) AS archivos FROM files "
        "GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Archivos por formato_contenido (firma real, #307)",
        """
        SELECT coalesce(metadata->'formato_contenido'->>'firma', '(sin rellenar)') AS firma,
               coalesce(metadata->'formato_contenido'->>'clase', '(sin clase)') AS clase,
               count(*) AS archivos
        FROM files GROUP BY 1, 2 ORDER BY 3 DESC
        """,
    ),
    (
        "Nulos por columna clave",
        """
        SELECT 'series.start_year' AS columna, count(*) FILTER (WHERE start_year IS NULL) AS nulos, count(*) AS total FROM series
        UNION ALL SELECT 'series.total_issues', count(*) FILTER (WHERE total_issues IS NULL), count(*) FROM series
        UNION ALL SELECT 'series.publisher_id', count(*) FILTER (WHERE publisher_id IS NULL), count(*) FROM series
        UNION ALL SELECT 'issues.issue_number', count(*) FILTER (WHERE issue_number IS NULL), count(*) FROM issues
        UNION ALL SELECT 'issues.format', count(*) FILTER (WHERE format IS NULL), count(*) FROM issues
        UNION ALL SELECT 'issues.page_count', count(*) FILTER (WHERE page_count IS NULL), count(*) FROM issues
        UNION ALL SELECT 'files.issue_id', count(*) FILTER (WHERE issue_id IS NULL), count(*) FROM files
        UNION ALL SELECT 'files.sha256_hash', count(*) FILTER (WHERE sha256_hash IS NULL), count(*) FROM files
        UNION ALL SELECT 'files.root_id', count(*) FILTER (WHERE root_id IS NULL), count(*) FROM files
        ORDER BY columna
        """,
    ),
    (
        "Último ciclo del importador y última comprobación válida de la biblioteca",
        """
        SELECT 'ultimo_ciclo' AS dato,
               max(started_at)::text AS valor,
               count(*) AS ciclos
        FROM import_runs
        WHERE NOT (details ? 'kind')
        UNION ALL
        SELECT 'ultima_comprobacion_valida',
               max((details->'comprobacion_biblioteca'->>'fecha'))::text,
               count(*)
        FROM import_runs
        WHERE NOT (details ? 'kind')
          AND details->'comprobacion_biblioteca'->>'resultado' = 'comprobada'
        """,
    ),
    (
        "Portadas externas (solo contexto de I3; no dice si hay copia local)",
        "SELECT count(*) FILTER (WHERE cover_url ~* '^https?://') AS externas, "
        "count(*) AS series FROM series",
    ),
    (
        "Evidencia de fuente guardada (cobertura de B1/B7)",
        "SELECT source, count(*) AS registros, count(DISTINCT entity_id) AS entidades "
        "FROM entity_source_records WHERE entity_type = 'series' GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "Fuentes activas apagadas/encendidas (runtime_settings)",
        """
        SELECT clave, valor::text AS valor
        FROM runtime_settings, jsonb_each_text(values) AS t(clave, valor)
        WHERE clave IN ('comicvine_enabled','anilist_enabled','tebeosfera_enabled','gcd_enabled',
                        'metron_enabled','open_library_enabled','fandom_dc_enabled',
                        'fandom_marvel_enabled','fuentes_heredadas')
        ORDER BY clave
        """,
    ),
]


# ── Catálogo de comprobaciones (fase 2) ───────────────────────────────────────
# Los ids son estables entre ejecuciones. Se añaden subcomprobaciones con
# sufijo (A1a, A1b…) cuando el defecto necesita una población distinta.

CHECKS: list[Check] = []


# ── A. Integridad referencial y estructural ───────────────────────────────────

CHECKS.extend([
    Check(
        "A1a", "Referencia vigente a una serie que ya no existe", "S2",
        poblacion="""
        SELECT count(*) FROM files f
        WHERE cardinality(f.covered_issue_ids) > 0
           OR jsonb_typeof(f.metadata->'vinculo') = 'object'
        """,
        casos="""
        WITH colgantes AS (
            SELECT f.id AS file_id, 'covered_issue_ids'::text AS tipo, x::text AS referencia
            FROM files f CROSS JOIN LATERAL unnest(f.covered_issue_ids) AS x
            WHERE NOT EXISTS (SELECT 1 FROM issues i WHERE i.id = x)
            UNION ALL
            SELECT f.id, 'vinculo.serie_id', f.metadata->'vinculo'->>'serie_id'
            FROM files f
            WHERE jsonb_typeof(f.metadata->'vinculo') = 'object'
              AND f.metadata->'vinculo' ? 'serie_id'
              AND NOT EXISTS (SELECT 1 FROM series s
                              WHERE s.id::text = lower(f.metadata->'vinculo'->>'serie_id'))
        )
        SELECT f.id::text AS caso_id,
               jsonb_build_object('tipo', c.tipo, 'referencia', c.referencia,
                                  'file_name', f.file_name, 'file_path', f.file_path) AS detalle
        FROM colgantes c JOIN files f ON f.id = c.file_id
        """,
        nota="La referencia VIGENTE apunta a una fila borrada: la ficha puede enseñar un vínculo "
             "que ya no existe. El historial se mide aparte (A1b) porque es append-only y puede "
             "ser legítimo.",
    ),
    Check(
        "A1b", "Referencia del historial a una fila borrada", "S3",
        poblacion="""
        SELECT count(*) FROM files
        WHERE jsonb_typeof(metadata->'vinculo_historial') = 'array'
        """,
        casos="""
        SELECT DISTINCT f.id::text AS caso_id,
               jsonb_build_object('tipo', x.tipo, 'referencia', x.referencia,
                                  'file_name', f.file_name) AS detalle
        FROM files f CROSS JOIN LATERAL (
            SELECT 'vinculo_historial.serie_id'::text AS tipo, e->>'serie_id' AS referencia
            FROM jsonb_array_elements(f.metadata->'vinculo_historial') e
            WHERE e ? 'serie_id'
            UNION ALL
            SELECT 'vinculo_historial.issue_id', e->>'issue_id'
            FROM jsonb_array_elements(f.metadata->'vinculo_historial') e
            WHERE e ? 'issue_id'
        ) x
        WHERE jsonb_typeof(f.metadata->'vinculo_historial') = 'array'
          AND ((x.tipo = 'vinculo_historial.serie_id'
                AND NOT EXISTS (SELECT 1 FROM series s
                                WHERE s.id::text = lower(x.referencia)))
            OR (x.tipo = 'vinculo_historial.issue_id'
                AND NOT EXISTS (SELECT 1 FROM issues i
                                WHERE i.id::text = lower(x.referencia))))
        """,
        nota="El historial conserva la procedencia de un vínculo que se deshizo o de una fila que "
             "se borró después (ADR 0014). No es un defecto por sí mismo; se mide para no contarlo.",
    ),
    Check(
        "A2", "Huérfanos lógicos (deseo, progreso, portada de colección)", "S2",
        poblacion="""
        SELECT (SELECT count(*) FROM wishlist)
             + (SELECT count(*) FROM reading_progress WHERE file_id IS NOT NULL)
             + (SELECT count(*) FROM collections)
        """,
        casos="""
        SELECT w.id::text AS caso_id,
               jsonb_build_object(
                   'subtipo', 'wishlist.issue_de_otra_serie',
                   'estado', w.status::text, 'origen', w.origen::text, 'numero', w.numero,
                   'serie_del_deseo', w.series_id, 'serie_del_numero', i.series_id) AS detalle
        FROM wishlist w JOIN issues i ON i.id = w.issue_id
        WHERE w.series_id IS NOT NULL AND w.series_id <> i.series_id
        UNION ALL
        SELECT w.id::text,
               jsonb_build_object('subtipo', 'wishlist.sin_destino',
                                  'estado', w.status::text, 'origen', w.origen::text)
        FROM wishlist w WHERE w.series_id IS NULL AND w.issue_id IS NULL
        UNION ALL
        SELECT rp.id::text,
               jsonb_build_object(
                   'subtipo', 'reading_progress.archivo_de_otro_numero',
                   'current_page', rp.current_page,
                   'file_name', f.file_name, 'file_path', f.file_path,
                   'issue_del_progreso', rp.issue_id, 'issue_del_archivo', f.issue_id)
        FROM reading_progress rp JOIN files f ON f.id = rp.file_id
        WHERE f.issue_id IS DISTINCT FROM rp.issue_id
        UNION ALL
        SELECT c.id::text,
               jsonb_build_object('subtipo', 'collection.portada_fuera',
                                  'nombre', c.name, 'cover_series_id', c.cover_series_id)
        FROM collections c
        WHERE c.cover_series_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM collection_series cs
                          WHERE cs.collection_id = c.id
                            AND cs.series_id = c.cover_series_id)
        """,
        nota="El deseo que apunta a un número de otra serie hace que la app busque en la serie "
             "equivocada; el progreso con archivo de otro número muestra una página que no es.",
    ),
    Check(
        "A3", "Ciclos e imposibles en series.parent_series_id", "S3",
        poblacion="SELECT count(*) FROM series WHERE parent_series_id IS NOT NULL",
        casos="""
        WITH RECURSIVE cadena(raiz, actual, camino, ciclo) AS (
            SELECT s.id, s.parent_series_id, ARRAY[s.id], false
            FROM series s WHERE s.parent_series_id IS NOT NULL
            UNION ALL
            SELECT c.raiz, s.parent_series_id, c.camino || s.id, s.id = ANY(c.camino)
            FROM cadena c JOIN series s ON s.id = c.actual
            WHERE c.actual IS NOT NULL AND NOT c.ciclo
              AND array_length(c.camino, 1) < 20
        )
        SELECT cid AS caso_id,
               jsonb_build_object('subtipo', 'ciclo_parent',
                                  'camino', min(camino_txt)) AS detalle
        FROM (
            SELECT (SELECT min(x::text) FROM unnest(camino) x) AS cid,
                   array_to_string(camino, ' -> ') AS camino_txt
            FROM cadena WHERE ciclo
        ) t
        GROUP BY cid
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('subtipo', 'hijo_de_one_shot',
                                  'titulo', s.title, 'padre', p.title)
        FROM series s JOIN series p ON p.id = s.parent_series_id
        WHERE p.kind::text = 'one_shot'
        """,
        nota="El CHECK solo impide la autorreferencia; A→B→A cuelga la ficha. Un hijo de una "
             "obra autoconclusiva tampoco tiene sentido (ADR 0022).",
    ),
    Check(
        "A4a", "Mismo número con volume NULL repetido (colisión efectiva)", "S2",
        poblacion="SELECT count(*) FROM issues WHERE volume IS NULL AND issue_number IS NOT NULL",
        casos="""
        SELECT i.series_id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'issues', count(*), 'formats', jsonb_agg(i.format::text)) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.volume IS NULL AND i.issue_number IS NOT NULL
        GROUP BY i.series_id, i.issue_number, s.title
        HAVING count(*) > 1
        """,
        nota="El UNIQUE(series_id, issue_number, volume) no detiene dos NULL: dos números "
             "iguales en la misma serie, cada uno con su archivo. Es el caso de censo_identidad.",
    ),
    Check(
        "A4b", "Misma ruta de archivo normalizada (caja o barra final)", "S2",
        poblacion="SELECT count(*) FROM files",
        casos="""
        SELECT min(f.id::text) AS caso_id,
               jsonb_build_object('ruta_normalizada', lower(rtrim(f.file_path, '/')),
                                  'rutas', jsonb_agg(f.file_path ORDER BY f.id),
                                  'n', count(*)) AS detalle
        FROM files f
        GROUP BY lower(rtrim(f.file_path, '/'))
        HAVING count(*) > 1
        """,
        nota="El UNIQUE es sobre el texto exacto. En un disco insensible a mayúsculas dos rutas "
             "así son el mismo archivo; el registro puede estar partido.",
    ),
    Check(
        "A4c", "Raíces de biblioteca solapadas", "S2",
        poblacion="SELECT count(*) FROM library_roots",
        casos="""
        SELECT a.id::text AS caso_id,
               jsonb_build_object('raiz_a', a.path, 'raiz_b', b.path) AS detalle
        FROM library_roots a JOIN library_roots b ON a.id < b.id
        WHERE a.path = b.path
           OR a.path LIKE b.path || '/%'
           OR b.path LIKE a.path || '/%'
        """,
        nota="Dos raíces solapadas hacen que un archivo pueda pertenecer a dos: la raíz elegida "
             "y la cuarentena dejan de ser únicas.",
    ),
    Check(
        "A5a", "El archivo no cuelga de la raíz que dice", "S2",
        poblacion="SELECT count(*) FROM files WHERE root_id IS NOT NULL",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('ruta', f.file_path, 'raiz', r.path,
                                  'root_id', f.root_id) AS detalle
        FROM files f JOIN library_roots r ON r.id = f.root_id
        WHERE f.file_path <> r.path AND f.file_path NOT LIKE r.path || '/%'
        """,
        nota="root_id manda en la cuarentena y en el movimiento (#156): si no corresponde a la "
             "ruta, una operación puede mover el archivo a otro sitio.",
    ),
    Check(
        "A5b", "Raíz deshabilitada con archivos activos", "S2",
        poblacion="SELECT count(*) FROM files WHERE root_id IS NOT NULL",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('ruta', f.file_path, 'raiz', r.path,
                                  'is_missing', f.is_missing) AS detalle
        FROM files f JOIN library_roots r ON r.id = f.root_id
        WHERE NOT r.enabled AND NOT f.is_missing
        """,
        nota="Una raíz deshabilitada no debería sostener archivos que cuentan como disponibles.",
    ),
    Check(
        "A5c", "Archivo bajo una raíz conocida con root_id NULL", "S3",
        poblacion="SELECT count(*) FROM files WHERE root_id IS NULL",
        casos="""
        SELECT DISTINCT ON (f.id) f.id::text AS caso_id,
               jsonb_build_object('ruta', f.file_path, 'raiz', r.path) AS detalle
        FROM files f JOIN library_roots r ON f.root_id IS NULL
         AND (f.file_path = r.path OR f.file_path LIKE r.path || '/%')
        ORDER BY f.id
        """,
        nota="Heredado: filas anteriores a #156 sin rellenar. No es un dato falso hoy, pero la "
             "operación por raíz no las ve.",
    ),
    Check(
        "A6", "Operaciones a medias y antiguas", "S2",
        poblacion="""
        SELECT (SELECT count(*) FROM asignacion_operaciones)
             + (SELECT count(*) FROM paquete_operaciones)
             + (SELECT count(*) FROM apartado_operaciones)
        """,
        casos="""
        SELECT a.id::text AS caso_id,
               jsonb_build_object('subtipo', 'asignacion', 'estado', a.estado::text,
                                  'creada', a.creada, 'actualizada', a.actualizada,
                                  'file_id', a.file_id, 'series_id', a.series_id) AS detalle
        FROM asignacion_operaciones a
        WHERE a.estado::text IN ('preparada', 'confirmada')
          AND a.actualizada < now() - interval '24 hours'
        UNION ALL
        SELECT p.id::text,
               jsonb_build_object('subtipo', 'paquete', 'estado', p.estado::text,
                                  'creada', p.creada, 'finalizada', p.finalizada)
        FROM paquete_operaciones p
        WHERE p.estado::text NOT IN ('importado', 'error')
          AND p.finalizada IS NULL
          AND p.creada < now() - interval '24 hours'
        UNION ALL
        SELECT a.id::text,
               jsonb_build_object('subtipo', 'apartado', 'estado', a.estado::text,
                                  'creada', a.creada)
        FROM apartado_operaciones a
        WHERE a.estado::text = 'en_curso'
          AND a.actualizada < now() - interval '24 hours'
        """,
        nota="ADR 0006: son recuperables, no basura. Se informa sin tocar nada; la recuperación "
             "tiene su propio camino. El umbral de 24 h es orientativo y se mide.",
    ),
])


# ── B. Identidad de serie frente a fuente (la más dañina) ─────────────────────

#: Expresión SQL que devuelve el id vigente de la fuente `h.source` para una fila
#: de `series s`. Se usa en varias comprobaciones; los valores son fijos.
_ID_VIGENTE = """
    CASE h.source
        WHEN 'comic_vine' THEN s.comic_vine_id::text
        WHEN 'anilist' THEN s.anilist_id::text
        WHEN 'tebeosfera' THEN s.tebeosfera_slug
        WHEN 'gcd' THEN s.gcd_id::text
        WHEN 'metron' THEN s.metron_id::text
        WHEN 'open_library' THEN s.open_library_id
        WHEN 'fandom_dc' THEN s.fandom_dc_slug
        WHEN 'fandom_marvel' THEN s.fandom_marvel_slug
    END
"""
_CUALQUIER_ID = """
    (s.comic_vine_id IS NOT NULL OR s.anilist_id IS NOT NULL
     OR s.tebeosfera_slug IS NOT NULL OR s.gcd_id IS NOT NULL
     OR s.metron_id IS NOT NULL OR s.open_library_id IS NOT NULL
     OR s.fandom_dc_slug IS NOT NULL OR s.fandom_marvel_slug IS NOT NULL)
"""

CHECKS.extend([
    Check(
        "B1a", "Homónimos resueltos a ciegas: varios exactos sin año", "S1",
        poblacion=f"""
        SELECT count(*) FROM series s
        WHERE s.start_year IS NULL AND {_CUALQUIER_ID}
        """,
        casos=f"""
        WITH fuente_titulo AS (
            SELECT esr.source,
                   f_title_norm(coalesce(
                       esr.payload->'normalizado'->'edition_scope'->>'title',
                       s.title)) AS titulo_norm,
                   count(DISTINCT esr.external_id) AS volumenes
            FROM entity_source_records esr
            JOIN series s ON s.id = esr.entity_id AND esr.entity_type = 'series'
            GROUP BY 1, 2
        ), homonimos AS (
            SELECT * FROM fuente_titulo WHERE volumenes > 1
        )
        SELECT s.id::text AS caso_id,
               jsonb_build_object(
                   'titulo', s.title, 'anio', s.start_year, 'tradicion', s.tradition::text,
                   'fuente', h.source, 'volumenes_en_la_fuente', h.volumenes,
                   'id_vigente', {_ID_VIGENTE}) AS detalle
        FROM series s
        JOIN homonimos h ON h.titulo_norm = s.title_norm
        WHERE s.start_year IS NULL
          AND ((h.source = 'comic_vine' AND s.comic_vine_id IS NOT NULL)
            OR (h.source = 'anilist' AND s.anilist_id IS NOT NULL)
            OR (h.source = 'tebeosfera' AND s.tebeosfera_slug IS NOT NULL)
            OR (h.source = 'gcd' AND s.gcd_id IS NOT NULL)
            OR (h.source = 'metron' AND s.metron_id IS NOT NULL)
            OR (h.source = 'open_library' AND s.open_library_id IS NOT NULL)
            OR (h.source = 'fandom_dc' AND s.fandom_dc_slug IS NOT NULL)
            OR (h.source = 'fandom_marvel' AND s.fandom_marvel_slug IS NOT NULL))
        """,
        nota="P1: `_pick_by_year` devuelve matches[0] si no hay año. La evidencia es "
             "`entity_source_records`: el mismo título normalizado tiene varios volúmenes en la "
             "fuente y la serie no tiene con qué desempatar. Sin evidencia guardada no se mide.",
    ),
    Check(
        "B1b", "Año de la serie a más de 1 del año de la fuente", "S1",
        poblacion="""
        SELECT count(*) FROM series s
        JOIN entity_source_records esr ON esr.entity_type = 'series' AND esr.entity_id = s.id
        WHERE s.start_year IS NOT NULL AND s.comic_vine_id IS NOT NULL
          AND esr.external_id = s.comic_vine_id::text
          AND (esr.payload->'normalizado'->'edition_scope'->>'start_year') ~ '^[0-9]{4}$'
        """,
        casos="""
        SELECT DISTINCT ON (s.id) s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'anio_local', s.start_year,
                                  'anio_fuente',
                                  esr.payload->'normalizado'->'edition_scope'->>'start_year',
                                  'fuente', esr.source, 'id', esr.external_id) AS detalle
        FROM series s
        JOIN entity_source_records esr ON esr.entity_type = 'series' AND esr.entity_id = s.id
        WHERE s.start_year IS NOT NULL AND s.comic_vine_id IS NOT NULL
          AND esr.external_id = s.comic_vine_id::text
          AND (esr.payload->'normalizado'->'edition_scope'->>'start_year') ~ '^[0-9]{4}$'
          AND abs(s.start_year
                  - (esr.payload->'normalizado'->'edition_scope'->>'start_year')::int) > 1
        ORDER BY s.id
        """,
        nota="Solo se compara el registro de la fuente cuyo id es el VIGENTE; la evidencia de ids "
             "anteriores es histórica y se mide en B8. Sin ese filtro, 8 de los 9 casos del "
             "2026-11-20 eran registros viejos, no defectos de esta comprobación.",
    ),
    Check(
        "B1c", "Homónimos sin evidencia guardada (cobertura de B1)", "S3",
        poblacion=f"""
        SELECT count(*) FROM series s WHERE s.start_year IS NULL AND {_CUALQUIER_ID}
        """,
        casos=f"""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'metadata_source', coalesce(s.metadata_source, '(sin fuente)'))
        FROM series s
        WHERE s.start_year IS NULL AND {_CUALQUIER_ID}
          AND NOT EXISTS (SELECT 1 FROM entity_source_records esr
                          WHERE esr.entity_type = 'series' AND esr.entity_id = s.id)
        """,
        nota="No es un defecto: es la parte de B1a que no se puede medir sin red. Se informa para "
             "que «0 casos» no se lea como «no hay homónimos».",
    ),
    Check(
        "B2a", "Edición española con id de Comic Vine (volumen original)", "S1",
        poblacion="SELECT count(*) FROM series WHERE comic_vine_id IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'tradicion', s.tradition::text,
                                  'comic_vine_id', s.comic_vine_id,
                                  'total_issues', s.total_issues,
                                  'editorial', p.name,
                                  'wishlist_policy', s.wishlist_policy::text) AS detalle
        FROM series s LEFT JOIN publishers p ON p.id = s.publisher_id
        WHERE s.comic_vine_id IS NOT NULL
          AND s.tradition::text IN ('tebeo', 'hispanoamericano')
        """,
        nota="P2: el total de Comic Vine es el del volumen USA. En una edición española la "
             "numeración no coincide. Falso positivo: una edición española que de verdad "
             "reproduzca el volumen USA con su misma numeración.",
    ),
    Check(
        "B2b", "Otra tradición no americana con id de Comic Vine", "S2",
        poblacion="SELECT count(*) FROM series WHERE comic_vine_id IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'tradicion', s.tradition::text,
                                  'comic_vine_id', s.comic_vine_id,
                                  'total_issues', s.total_issues, 'editorial', p.name) AS detalle
        FROM series s LEFT JOIN publishers p ON p.id = s.publisher_id
        WHERE s.comic_vine_id IS NOT NULL
          AND s.tradition::text NOT IN ('american', 'british', 'tebeo', 'hispanoamericano')
        """,
        nota="Comic Vine también indexa álbumes europeos; el caso no es tan claro como B2a. Se "
             "mide la precisión antes de contar como defecto.",
    ),
    Check(
        "B3a", "anilist_id en una serie que no es manga", "S2",
        poblacion="SELECT count(*) FROM series WHERE anilist_id IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'tradicion', s.tradition::text,
                                  'anilist_id', s.anilist_id) AS detalle
        FROM series s
        WHERE s.anilist_id IS NOT NULL
          AND s.tradition::text NOT IN ('manga', 'manhwa', 'manhua')
        """,
        nota="AniList cuenta capítulos de manga; un id de AniList en otra tradición casi siempre "
             "es una asociación equivocada.",
    ),
    Check(
        "B3b", "Tebeosfera en una grapa americana", "S2",
        poblacion="SELECT count(*) FROM series WHERE tebeosfera_slug IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'tradicion', s.tradition::text,
                                  'tebeosfera_slug', s.tebeosfera_slug,
                                  'editorial', p.name, 'pais', p.country) AS detalle
        FROM series s LEFT JOIN publishers p ON p.id = s.publisher_id
        WHERE s.tebeosfera_slug IS NOT NULL
          AND s.tradition::text IN ('american', 'british')
        """,
        nota="Tebeosfera es una fuente española. Falso positivo: una edición española de material "
             "USA catalogada como `american`; el país de la editorial desempata.",
    ),
    Check(
        "B3c", "Slug de Fandom en una editorial que no corresponde", "S2",
        poblacion="""
        SELECT count(*) FROM series
        WHERE fandom_dc_slug IS NOT NULL OR fandom_marvel_slug IS NOT NULL
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'editorial', p.name,
                                  'fandom_dc_slug', s.fandom_dc_slug,
                                  'fandom_marvel_slug', s.fandom_marvel_slug) AS detalle
        FROM series s LEFT JOIN publishers p ON p.id = s.publisher_id
        WHERE (s.fandom_dc_slug IS NOT NULL
               AND (p.name IS NULL OR f_title_norm(p.name) NOT LIKE '%dc%'))
           OR (s.fandom_marvel_slug IS NOT NULL
               AND (p.name IS NULL OR f_title_norm(p.name) NOT LIKE '%marvel%'))
        """,
        nota="DC Database y Marvel Database son wikis de editorial; un slug suyo en otra "
             "editorial apunta a una página que no es la obra. La editorial puede faltar.",
    ),
    Check(
        "B4a", "Asociación de fuente incoherente con la columna", "S1",
        poblacion="""
        SELECT count(*) FROM series s
        WHERE jsonb_typeof(s.metadata->'asociaciones') = 'array'
          AND jsonb_array_length(s.metadata->'asociaciones') > 0
        """,
        casos="""
        WITH entradas AS (
            SELECT s.id AS series_id, s.title,
                   e->>'fuente' AS fuente, e->>'id_externo' AS id_externo,
                   e->>'operacion_id' AS operacion_id
            FROM series s CROSS JOIN LATERAL jsonb_array_elements(s.metadata->'asociaciones') e
            WHERE jsonb_typeof(s.metadata->'asociaciones') = 'array'
        )
        SELECT en.series_id::text AS caso_id,
               jsonb_build_object('titulo', en.title, 'fuente', en.fuente,
                                  'id_externo', en.id_externo,
                                  'columna_actual', CASE en.fuente
                                      WHEN 'comic_vine' THEN s.comic_vine_id::text
                                      WHEN 'anilist' THEN s.anilist_id::text
                                      WHEN 'tebeosfera' THEN s.tebeosfera_slug
                                      WHEN 'gcd' THEN s.gcd_id::text
                                      WHEN 'metron' THEN s.metron_id::text
                                      WHEN 'open_library' THEN s.open_library_id
                                      WHEN 'fandom_dc' THEN s.fandom_dc_slug
                                      WHEN 'fandom_marvel' THEN s.fandom_marvel_slug
                                  END,
                                  'operacion_id', en.operacion_id) AS detalle
        FROM entradas en JOIN series s ON s.id = en.series_id
        WHERE (en.fuente = 'comic_vine' AND s.comic_vine_id::text IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'anilist' AND s.anilist_id::text IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'tebeosfera' AND s.tebeosfera_slug IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'gcd' AND s.gcd_id::text IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'metron' AND s.metron_id::text IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'open_library' AND s.open_library_id IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'fandom_dc' AND s.fandom_dc_slug IS DISTINCT FROM en.id_externo)
           OR (en.fuente = 'fandom_marvel' AND s.fandom_marvel_slug IS DISTINCT FROM en.id_externo)
        """,
        nota="R1 (#129): la columna es la verdad del id vigente y el JSONB es el registro. Si no "
             "coinciden, la asociación que se enseñó al confirmar ya no es la que hay.",
    ),
    Check(
        "B4b", "Dos asociaciones activas de la misma fuente", "S1",
        poblacion="""
        SELECT count(*) FROM series s
        WHERE jsonb_typeof(s.metadata->'asociaciones') = 'array'
          AND jsonb_array_length(s.metadata->'asociaciones') > 0
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'fuente', e->>'fuente',
                                  'ids_externos', jsonb_agg(e->>'id_externo'),
                                  'operaciones', jsonb_agg(e->>'operacion_id')) AS detalle
        FROM series s CROSS JOIN LATERAL jsonb_array_elements(s.metadata->'asociaciones') e
        WHERE jsonb_typeof(s.metadata->'asociaciones') = 'array'
        GROUP BY s.id, s.title, e->>'fuente'
        HAVING count(*) > 1
        """,
        nota="El contrato es una por (serie, fuente). Dos activas apuntan a dos fichas y la "
             "columna solo puede guardar una.",
    ),
    Check(
        "B5a", "Número con id de Comic Vine en una serie sin id de volumen", "S1",
        poblacion="SELECT count(*) FROM issues WHERE comic_vine_id IS NOT NULL",
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'comic_vine_id', i.comic_vine_id,
                                  'serie', s.title, 'serie_sin_comic_vine_id', s.comic_vine_id,
                                  'metadata_source', i.metadata_source) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.comic_vine_id IS NOT NULL AND s.comic_vine_id IS NULL
        """,
        nota="El id de número se busca dentro de `series.comic_vine_id` (P3). Si la serie no "
             "tiene volumen, ese id salió de otro sitio y no hay con qué comprobarlo.",
    ),
    Check(
        "B5b", "Número local distinto del número de la fuente para su id", "S1",
        poblacion="""
        SELECT count(*) FROM issues i
        JOIN entity_source_records esr
          ON esr.entity_type = 'issue' AND esr.entity_id = i.id AND esr.source = 'comic_vine'
        WHERE i.issue_number IS NOT NULL
          AND esr.payload->'raw_acotado'->>'issue_number' IS NOT NULL
        """,
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('numero_local', i.issue_number,
                                  'numero_fuente',
                                  esr.payload->'raw_acotado'->>'issue_number',
                                  'comic_vine_id', i.comic_vine_id,
                                  'serie', s.title) AS detalle
        FROM issues i
        JOIN series s ON s.id = i.series_id
        JOIN entity_source_records esr
          ON esr.entity_type = 'issue' AND esr.entity_id = i.id AND esr.source = 'comic_vine'
        WHERE i.issue_number IS NOT NULL
          AND esr.payload->'raw_acotado'->>'issue_number' IS NOT NULL
          AND f_number_key(i.issue_number)
              IS DISTINCT FROM f_number_key(esr.payload->'raw_acotado'->>'issue_number')
        """,
        nota="La ficha guardada de ese id dice otro número. `f_number_key` evita el ruido de "
             "«4» frente a «04».",
    ),
    Check(
        "B6a", "La fuente declarada no tiene su id", "S2",
        poblacion="""
        SELECT (SELECT count(*) FROM series WHERE metadata_source IS NOT NULL)
             + (SELECT count(*) FROM issues WHERE metadata_source IS NOT NULL)
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('subtipo', 'serie', 'titulo', s.title,
                                  'metadata_source', s.metadata_source) AS detalle
        FROM series s
        WHERE (s.metadata_source = 'comic_vine' AND s.comic_vine_id IS NULL)
           OR (s.metadata_source = 'anilist' AND s.anilist_id IS NULL)
           OR (s.metadata_source = 'tebeosfera' AND s.tebeosfera_slug IS NULL)
           OR (s.metadata_source = 'gcd' AND s.gcd_id IS NULL)
           OR (s.metadata_source = 'metron' AND s.metron_id IS NULL)
           OR (s.metadata_source = 'open_library' AND s.open_library_id IS NULL)
           OR (s.metadata_source = 'fandom_dc' AND s.fandom_dc_slug IS NULL)
           OR (s.metadata_source = 'fandom_marvel' AND s.fandom_marvel_slug IS NULL)
        UNION ALL
        SELECT i.id::text,
               jsonb_build_object('subtipo', 'issue', 'numero', i.issue_number,
                                  'metadata_source', i.metadata_source)
        FROM issues i
        WHERE (i.metadata_source = 'comic_vine' AND i.comic_vine_id IS NULL)
           OR (i.metadata_source = 'gcd' AND i.gcd_id IS NULL)
           OR (i.metadata_source = 'anilist' AND i.anilist_id IS NULL)
           OR (i.metadata_source = 'tebeosfera' AND i.tebeosfera_slug IS NULL)
           OR (i.metadata_source = 'fandom_dc' AND i.fandom_dc_slug IS NULL)
           OR (i.metadata_source = 'fandom_marvel' AND i.fandom_marvel_slug IS NULL)
        """,
        nota="`metadata_source='comicinfo_xml'` sin `comic_vine_id` es legítimo (el archivo trae "
             "los datos): la comprobación solo mira las fuentes de ficha.",
    ),
    Check(
        "B6b", "Ids de varias fuentes con años incompatibles", "S2",
        poblacion="""
        SELECT count(*) FROM (
            SELECT entity_id FROM entity_source_records
            WHERE entity_type = 'series'
            GROUP BY entity_id HAVING count(DISTINCT source) > 1
        ) t
        """,
        casos="""
        WITH pares AS (
            SELECT esr.entity_id, esr.source,
                   esr.payload->'normalizado'->'edition_scope'->>'start_year' AS anio
            FROM entity_source_records esr
            WHERE esr.entity_type = 'series'
        )
        SELECT a.entity_id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'fuente_a', a.source, 'anio_a', a.anio,
                                  'fuente_b', b.source, 'anio_b', b.anio) AS detalle
        FROM pares a
        JOIN pares b ON a.entity_id = b.entity_id AND a.source < b.source
        JOIN series s ON s.id = a.entity_id
        WHERE a.anio ~ '^[0-9]{4}$' AND b.anio ~ '^[0-9]{4}$'
          AND abs(a.anio::int - b.anio::int) > 1
        """,
        nota="Dos fuentes que dicen años distintos de la «misma» serie describen obras distintas. "
             "Una de las dos asociaciones sobra; decide el PO.",
    ),
    Check(
        "B6c", "Ids puestos sin intento de enriquecimiento registrado", "S2",
        poblacion=f"""
        SELECT count(*) FROM series s
        WHERE s.enrichment_attempted_at IS NULL AND {_CUALQUIER_ID}
        """,
        casos=f"""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'metadata_source', coalesce(s.metadata_source, '(sin fuente)'),
                                  'locked_fields', s.locked_fields,
                                  'ids', jsonb_build_object(
                                      'comic_vine', s.comic_vine_id, 'anilist', s.anilist_id,
                                      'tebeosfera', s.tebeosfera_slug, 'gcd', s.gcd_id,
                                      'metron', s.metron_id, 'open_library', s.open_library_id,
                                      'fandom_dc', s.fandom_dc_slug,
                                      'fandom_marvel', s.fandom_marvel_slug)) AS detalle
        FROM series s
        WHERE s.enrichment_attempted_at IS NULL
          AND coalesce(s.metadata_source, '') <> 'manual'
          AND jsonb_typeof(s.metadata->'alta') IS DISTINCT FROM 'object'
          AND (
            (s.comic_vine_id IS NOT NULL AND NOT ('comic_vine_id' = ANY(s.locked_fields))
             AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
                 CASE WHEN jsonb_typeof(s.metadata->'asociaciones') = 'array'
                      THEN s.metadata->'asociaciones' ELSE '[]'::jsonb END) e
                 WHERE e->>'fuente' = 'comic_vine'))
            OR (s.anilist_id IS NOT NULL AND NOT ('anilist_id' = ANY(s.locked_fields))
             AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
                 CASE WHEN jsonb_typeof(s.metadata->'asociaciones') = 'array'
                      THEN s.metadata->'asociaciones' ELSE '[]'::jsonb END) e
                 WHERE e->>'fuente' = 'anilist'))
            OR (s.tebeosfera_slug IS NOT NULL AND NOT ('tebeosfera_slug' = ANY(s.locked_fields))
             AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
                 CASE WHEN jsonb_typeof(s.metadata->'asociaciones') = 'array'
                      THEN s.metadata->'asociaciones' ELSE '[]'::jsonb END) e
                 WHERE e->>'fuente' = 'tebeosfera'))
            OR (s.gcd_id IS NOT NULL AND NOT ('gcd_id' = ANY(s.locked_fields))
             AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
                 CASE WHEN jsonb_typeof(s.metadata->'asociaciones') = 'array'
                      THEN s.metadata->'asociaciones' ELSE '[]'::jsonb END) e
                 WHERE e->>'fuente' = 'gcd'))
          )
        """,
        nota="Un id de enriquecimiento se escribe junto a `enrichment_attempted_at`. Sin ese "
             "sello no consta qué pasó; se excluyen las altas y las asociaciones confirmadas, "
             "que sí son caminos legítimos.",
    ),
    Check(
        "B7", "Ficha de fuente con un título que no casa con la serie", "S2",
        poblacion="""
        SELECT count(*) FROM series s
        JOIN entity_source_records esr ON esr.entity_type = 'series' AND esr.entity_id = s.id
        WHERE esr.payload->'normalizado'->'edition_scope'->>'title' IS NOT NULL
        """,
        casos="""
        SELECT DISTINCT ON (s.id) s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'titulo_fuente',
                                  esr.payload->'normalizado'->'edition_scope'->>'title',
                                  'fuente', esr.source, 'id', esr.external_id) AS detalle
        FROM series s
        JOIN entity_source_records esr ON esr.entity_type = 'series' AND esr.entity_id = s.id
        WHERE esr.payload->'normalizado'->'edition_scope'->>'title' IS NOT NULL
          AND f_title_norm(esr.payload->'normalizado'->'edition_scope'->>'title')
              IS DISTINCT FROM s.title_norm
          AND f_title_norm(esr.payload->'normalizado'->'edition_scope'->>'title')
              NOT LIKE '%' || s.title_norm || '%'
          AND s.title_norm
              NOT LIKE '%' || f_title_norm(
                  esr.payload->'normalizado'->'edition_scope'->>'title') || '%'
        ORDER BY s.id
        """,
        nota="Heurístico: una variante legítima («Batman» / «Batman Vol 1») queda fuera por la "
             "contención, pero un subtítulo puede colarse. Precisión obligatoria antes de contar.",
    ),
])


# ── C. Números y ediciones ────────────────────────────────────────────────────

CHECKS.extend([
    Check(
        "B8", "Evidencia de fuente de un id que ya no es el vigente", "S3",
        poblacion="""
        SELECT count(*) FROM entity_source_records esr
        JOIN series s ON s.id = esr.entity_id AND esr.entity_type = 'series'
        WHERE (esr.source = 'comic_vine' AND s.comic_vine_id IS NOT NULL)
           OR (esr.source = 'anilist' AND s.anilist_id IS NOT NULL)
           OR (esr.source = 'tebeosfera' AND s.tebeosfera_slug IS NOT NULL)
           OR (esr.source = 'gcd' AND s.gcd_id IS NOT NULL)
           OR (esr.source = 'metron' AND s.metron_id IS NOT NULL)
           OR (esr.source = 'open_library' AND s.open_library_id IS NOT NULL)
           OR (esr.source = 'fandom_dc' AND s.fandom_dc_slug IS NOT NULL)
           OR (esr.source = 'fandom_marvel' AND s.fandom_marvel_slug IS NOT NULL)
        """,
        casos="""
        SELECT esr.id::text AS caso_id,
               jsonb_build_object('serie', s.title, 'fuente', esr.source,
                                  'id_del_registro', esr.external_id,
                                  'id_vigente', CASE esr.source
                                      WHEN 'comic_vine' THEN s.comic_vine_id::text
                                      WHEN 'anilist' THEN s.anilist_id::text
                                      WHEN 'tebeosfera' THEN s.tebeosfera_slug
                                      WHEN 'gcd' THEN s.gcd_id::text
                                      WHEN 'metron' THEN s.metron_id::text
                                      WHEN 'open_library' THEN s.open_library_id
                                      WHEN 'fandom_dc' THEN s.fandom_dc_slug
                                      WHEN 'fandom_marvel' THEN s.fandom_marvel_slug
                                  END,
                                  'fecha', esr.fetched_at) AS detalle
        FROM entity_source_records esr
        JOIN series s ON s.id = esr.entity_id AND esr.entity_type = 'series'
        WHERE ((esr.source = 'comic_vine' AND s.comic_vine_id IS NOT NULL)
               OR (esr.source = 'anilist' AND s.anilist_id IS NOT NULL)
               OR (esr.source = 'tebeosfera' AND s.tebeosfera_slug IS NOT NULL)
               OR (esr.source = 'gcd' AND s.gcd_id IS NOT NULL)
               OR (esr.source = 'metron' AND s.metron_id IS NOT NULL)
               OR (esr.source = 'open_library' AND s.open_library_id IS NOT NULL)
               OR (esr.source = 'fandom_dc' AND s.fandom_dc_slug IS NOT NULL)
               OR (esr.source = 'fandom_marvel' AND s.fandom_marvel_slug IS NOT NULL))
          AND esr.external_id IS DISTINCT FROM (CASE esr.source
                  WHEN 'comic_vine' THEN s.comic_vine_id::text
                  WHEN 'anilist' THEN s.anilist_id::text
                  WHEN 'tebeosfera' THEN s.tebeosfera_slug
                  WHEN 'gcd' THEN s.gcd_id::text
                  WHEN 'metron' THEN s.metron_id::text
                  WHEN 'open_library' THEN s.open_library_id
                  WHEN 'fandom_dc' THEN s.fandom_dc_slug
                  WHEN 'fandom_marvel' THEN s.fandom_marvel_slug
              END)
        """,
        nota="No es un defecto por sí mismo: el registro es evidencia histórica de una asociación "
             "anterior. Se mide para no usarlo como la ficha vigente (B1b) y para decidir si se "
             "purga o se marca. En la medición del 2026-11-20 son 8 registros.",
    ),
    Check(
        "C1", "El número del nombre del archivo contradice el del número", "S2",
        poblacion="""
        SELECT count(*) FROM files f JOIN issues i ON i.id = f.issue_id
        WHERE i.issue_number ~ '^[0-9]+$'
        """,
        casos="""
        WITH candidatos AS (
            SELECT f.id, f.file_name, i.issue_number,
                   f.metadata->>'match_status' AS match_status,
                   (regexp_match(
                       f.file_name,
                       '(?:^|[^0-9])([0-9]{1,4})(?:\\s*\\([^)]*\\))?\\s*(?:\\[[^]]*\\])?\\.[A-Za-z0-9]+$'
                   ))[1] AS num_final
            FROM files f JOIN issues i ON i.id = f.issue_id
            WHERE i.issue_number ~ '^[0-9]+$'
              AND f.file_name !~ '[0-9]\\s*[-–]\\s*[0-9]'
              AND f.file_name !~* '(annual|anual|especial|special|omnigold|integral|tomo|volumen)'
              AND coalesce(f.metadata->>'match_status', '')
                  NOT IN ('manual', 'manual_especial', 'manual_one_shot')
              AND NOT ('issue_number' = ANY(coalesce(i.locked_fields, '{}'::varchar[])))
              AND NOT (coalesce(jsonb_typeof(f.metadata->'vinculo'), '') = 'object'
                       AND f.metadata->'vinculo' ? 'operacion_id')
        )
        SELECT id::text AS caso_id,
               jsonb_build_object('file_name', file_name, 'numero_issue', issue_number,
                                  'numero_del_nombre', num_final,
                                  'match_status', match_status) AS detalle
        FROM candidatos
        WHERE num_final IS NOT NULL AND num_final::int <> issue_number::int
        """,
        nota="Proxy: el último entero del nombre antes de la extensión, NO el parser de la "
             "versión desplegada (eso es D1b/C1-parser, NOT RUN en SQL). Se excluyen rangos, "
             "anuales/tomos y vínculos protegidos; la precisión se mide antes de corregir.",
    ),
    Check(
        "C2a", "Issue single_issue en una serie ONE_SHOT", "S2",
        poblacion="""
        SELECT count(*) FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.kind::text = 'one_shot'
        """,
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'format', i.format::text) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.kind::text = 'one_shot' AND i.format::text = 'single_issue'
        """,
        nota="ADR 0022: una obra autoconclusiva nunca es una grapa. `numero_de_grapa` la contaría "
             "como grapa y crearía un hueco del #1.",
    ),
    Check(
        "C2b", "Tomo/ómnibus registrado como grapa", "S2",
        poblacion="""
        SELECT count(*) FROM issues i JOIN files f ON f.issue_id = i.id
        WHERE i.format::text = 'single_issue'
        """,
        casos="""
        SELECT DISTINCT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'format', i.format::text,
                                  'edicion_del_archivo', f.metadata->>'edicion',
                                  'file_name', f.file_name) AS detalle
        FROM issues i
        JOIN series s ON s.id = i.series_id
        JOIN files f ON f.issue_id = i.id
        WHERE i.format::text = 'single_issue'
          AND f.metadata->>'edicion' IN
              ('omnigold', 'integral', 'omnibus', 'tomo', 'volumen', 'trade_paperback',
               'tpb', 'hardcover', 'hc', 'graphic_novel')
        """,
        nota="El nombre del archivo declara una edición recopilatoria y la fila dice grapa: "
             "`numero_de_grapa` la cuenta como grapa y tapa el hueco que no es.",
    ),
    Check(
        "C2c", "Annual o número decimal registrado como grapa", "S2",
        poblacion="""
        SELECT count(*) FROM issues WHERE format::text = 'single_issue'
        """,
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'format', i.format::text) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.format::text = 'single_issue'
          AND (i.issue_number ~* '^(annual|anual|especial|special|extra|almanaque)\\b'
               OR i.issue_number ~ '^[0-9]+[.,][0-9]+$')
        """,
        nota="ADR 0016/0022: anuales y decimales no ocupan el hueco de la grapa entera. Un "
             "`Annual 1` como grapa hace que el #1 aparezca poseído.",
    ),
    Check(
        "C3a", "Número #1 o 0 inventado en una obra única o especial", "S2",
        poblacion="""
        SELECT count(*) FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.kind::text IN ('one_shot', 'special')
        """,
        casos=f"""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'kind', s.kind::text,
                                  'ids', jsonb_build_object(
                                      'comic_vine', s.comic_vine_id, 'anilist', s.anilist_id,
                                      'tebeosfera', s.tebeosfera_slug, 'gcd', s.gcd_id),
                                  'metadata_source', s.metadata_source) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.kind::text IN ('one_shot', 'special')
          AND i.issue_number IN ('1', '0', '01', '00', '#1', '#0')
          AND NOT {_CUALQUIER_ID}
          AND NOT (coalesce(jsonb_typeof(s.metadata->'alta'), '') = 'object'
                   AND s.metadata->'alta' ? 'id_externo')
        """,
        nota="ADR 0016/0022: el número solo se copia si la fuente lo da. Falso positivo: una "
             "persona decidió el #1 a mano y no consta id; se etiqueta en la muestra.",
    ),
    Check(
        "C3b", "issue_number vacío o con espacios frente a NULL", "S2",
        poblacion="SELECT count(*) FROM issues",
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.issue_number IS NOT NULL
          AND (btrim(i.issue_number) = '' OR i.issue_number <> btrim(i.issue_number))
        """,
        nota="El hueco honesto es NULL (ADR 0016). Una cadena vacía o con espacios no ordena, no "
             "cuenta como número y no se ve como «sin número».",
    ),
    Check(
        "C4a", "Número poseído mayor que el total acreditado", "S3",
        poblacion="""
        SELECT count(*) FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.metadata_source = 'comic_vine' AND s.total_issues > 0
          AND i.format::text = 'single_issue' AND i.issue_number ~ '^[0-9]+$'
        """,
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'total_issues', s.total_issues,
                                  'file_disponible', EXISTS (
                                      SELECT 1 FROM files f
                                      WHERE f.issue_id = i.id AND NOT f.is_missing)) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE s.metadata_source = 'comic_vine' AND s.total_issues > 0
          AND i.format::text = 'single_issue' AND i.issue_number ~ '^[0-9]+$'
          AND i.issue_number::int > s.total_issues
          AND (EXISTS (SELECT 1 FROM files f
                       WHERE f.issue_id = i.id AND NOT f.is_missing)
               OR i.metadata ? 'cubierto_por_tomo')
        """,
        nota="O el total es de otra edición (B2/E2) o el número está mal. Un número fuera del "
             "total no rellena ningún hueco.",
    ),
    Check(
        "C4b", "Formatos de número extraños", "S3",
        poblacion="SELECT count(*) FROM issues WHERE issue_number IS NOT NULL",
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'number_key', i.number_key) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.issue_number IS NOT NULL
          AND (i.issue_number ~ '^0[0-9]+$'
               OR i.issue_number ~ '^[0-9]+ ?[A-Za-z]$'
               OR i.issue_number ~ '^[0-9]+/[0-9]+$'
               OR i.issue_number ~ '^[0-9]+[.,][0-9]+$')
        """,
        nota="No todos son defectos («12 B» puede ser un número real). Se mide para saber qué "
             "orden y qué huecos produce `number_key`.",
    ),
    Check(
        "C5a", "Serie ONE_SHOT con más de una publicación", "S3",
        poblacion="SELECT count(*) FROM series WHERE kind::text = 'one_shot'",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'issues', count(*),
                                  'numeros', jsonb_agg(i.issue_number)) AS detalle
        FROM series s JOIN issues i ON i.series_id = s.id
        WHERE s.kind::text = 'one_shot'
        GROUP BY s.id, s.title
        HAVING count(*) > 1
        """,
        nota="Una obra autoconclusiva tiene una publicación. Si tiene varias, o no es one-shot o "
             "hay números duplicados; decide el PO.",
    ),
    Check(
        "C5b", "Serie regular con una sola publicación y total 1 (propuesta)", "S3",
        poblacion="SELECT count(*) FROM series WHERE kind::text = 'regular' AND total_issues = 1",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'tradition', s.tradition::text,
                                  'format', i.format::text, 'numero', i.issue_number,
                                  'metadata_source', s.metadata_source) AS detalle
        FROM series s JOIN issues i ON i.series_id = s.id
        WHERE s.kind::text = 'regular' AND s.total_issues = 1
          AND (SELECT count(*) FROM issues i2 WHERE i2.series_id = s.id) = 1
        """,
        nota="Propuesta al PO, no corrección: puede ser una obra única mal clasificada (ADR 0022). "
             "No se cambia `kind` sin su decisión.",
    ),
    Check(
        "C6", "Ediciones mezcladas en el espacio de numeración de una serie", "S2",
        poblacion="""
        SELECT count(DISTINCT i.series_id) FROM issues i JOIN files f ON f.issue_id = i.id
        """,
        casos="""
        WITH por_serie AS (
            SELECT i.series_id,
                   bool_or(f.metadata->>'edicion' IN ('omnigold', 'integral', 'omnibus'))
                       AS tiene_recopilacion,
                   bool_or(i.format::text = 'single_issue'
                           AND coalesce(f.metadata->>'edicion', '') NOT IN
                               ('omnigold', 'integral', 'omnibus')) AS tiene_grapa
            FROM issues i JOIN files f ON f.issue_id = i.id
            GROUP BY i.series_id
        )
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'tiene_recopilacion', p.tiene_recopilacion,
                                  'tiene_grapa', p.tiene_grapa) AS detalle
        FROM por_serie p JOIN series s ON s.id = p.series_id
        WHERE p.tiene_recopilacion AND p.tiene_grapa
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('titulo', s.title, 'por_titulo', true,
                                  'issues_single', count(*))
        FROM series s JOIN issues i ON i.series_id = s.id
        WHERE s.title ~* '(omnigold|integral)'
          AND i.format::text = 'single_issue'
        GROUP BY s.id, s.title
        """,
        nota="ADR 0003 D2: la grapa y la reedición renumerada son ediciones distintas. Si "
             "comparten `(series_id, issue_number)`, el número 12 puede ser dos cosas.",
    ),
])


# ── D. Archivos frente a publicaciones ────────────────────────────────────────

CHECKS.extend([
    Check(
        "D1a", "Archivo en una carpeta declarada hacia otra serie o número", "S2",
        poblacion="""
        SELECT count(*) FROM files f
        WHERE EXISTS (
            SELECT 1 FROM correspondencias_contexto c
            WHERE c.vigente_hasta IS NULL AND c.estado::text = 'activa'
              AND c.origen::text = 'local'
              AND strpos(f.file_path, '/' || c.contexto_raiz || '/') > 0)
        """,
        casos="""
        SELECT DISTINCT ON (f.id) f.id::text AS caso_id,
               jsonb_build_object('ruta', f.file_path,
                                  'carpeta', c.contexto_raiz,
                                  'destino_tipo', c.destino_tipo::text,
                                  'destino_id', c.destino_id,
                                  'serie_del_numero', i.series_id,
                                  'issue_del_archivo', f.issue_id) AS detalle
        FROM correspondencias_contexto c
        JOIN files f ON strpos(f.file_path, '/' || c.contexto_raiz || '/') > 0
        JOIN issues i ON i.id = f.issue_id
        WHERE c.vigente_hasta IS NULL AND c.estado::text = 'activa'
          AND c.origen::text = 'local'
          AND NOT (coalesce(jsonb_typeof(f.metadata->'vinculo'), '') = 'object'
                   AND f.metadata->'vinculo' ? 'operacion_id')
          AND ((c.destino_tipo::text = 'serie' AND i.series_id <> c.destino_id)
               OR (c.destino_tipo::text = 'publicacion' AND i.id <> c.destino_id))
        ORDER BY f.id
        """,
        nota="La carpeta declarada dice un destino y el archivo está vinculado a otro. Se excluye "
             "el vínculo confirmado (protección humana). `incluir_descendientes` no se filtra: "
             "la muestra puede traer subcarpetas y se etiqueta.",
    ),
    Check(
        "D2a", "El mismo contenido vinculado a números distintos", "S1",
        poblacion="""
        SELECT count(*) FROM files
        WHERE issue_id IS NOT NULL
          AND (sha256_hash IS NOT NULL OR original_sha256 IS NOT NULL)
        """,
        casos="""
        WITH contenido AS (
            SELECT f.id AS file_id, f.issue_id, f.sha256_hash AS hash
            FROM files f WHERE f.issue_id IS NOT NULL AND f.sha256_hash IS NOT NULL
            UNION
            SELECT f.id, f.issue_id, f.original_sha256
            FROM files f WHERE f.issue_id IS NOT NULL AND f.original_sha256 IS NOT NULL
        ), compartido AS (
            SELECT hash FROM contenido
            GROUP BY hash HAVING count(DISTINCT issue_id) > 1
        )
        SELECT c.hash AS caso_id,
               jsonb_build_object('hash', c.hash,
                                  'archivos', jsonb_agg(jsonb_build_object(
                                      'file_id', c.file_id, 'issue_id', c.issue_id,
                                      'numero', i.issue_number, 'serie', s.title,
                                      'file_name', f.file_name) ORDER BY c.file_id)) AS detalle
        FROM contenido c
        JOIN compartido x ON x.hash = c.hash
        JOIN files f ON f.id = c.file_id
        JOIN issues i ON i.id = c.issue_id
        JOIN series s ON s.id = i.series_id
        GROUP BY c.hash
        """,
        nota="Mismos bytes no son dos publicaciones. Distinto de dos copias idénticas del mismo "
             "número (D2b), que es asunto de Duplicados y no un error de catálogo.",
    ),
    Check(
        "D2b", "Mismo contenido repetido en el mismo número (duplicado legítimo)", "S3",
        poblacion="""
        SELECT count(*) FROM files
        WHERE issue_id IS NOT NULL
          AND (sha256_hash IS NOT NULL OR original_sha256 IS NOT NULL)
        """,
        casos="""
        WITH contenido AS (
            SELECT f.id AS file_id, f.issue_id, f.sha256_hash AS hash
            FROM files f WHERE f.issue_id IS NOT NULL AND f.sha256_hash IS NOT NULL
            UNION
            SELECT f.id, f.issue_id, f.original_sha256
            FROM files f WHERE f.issue_id IS NOT NULL AND f.original_sha256 IS NOT NULL
        )
        SELECT c.hash AS caso_id,
               jsonb_build_object('hash', c.hash, 'issue_id', min(c.issue_id::text),
                                  'archivos', count(*)) AS detalle
        FROM contenido c
        GROUP BY c.hash
        HAVING count(DISTINCT c.issue_id) = 1 AND count(*) > 1
        """,
        nota="No es un defecto de catálogo: son copias idénticas del mismo número. Se cuenta para "
             "separarlo de D2a y para no sumarlo dos veces en el informe.",
    ),
    Check(
        "D3a", "Un pack no incluye su propio número", "S2",
        poblacion="SELECT count(*) FROM files WHERE cardinality(covered_issue_ids) > 0",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name, 'file_path', f.file_path,
                                  'issue_id', f.issue_id,
                                  'cubiertos', cardinality(f.covered_issue_ids)) AS detalle
        FROM files f
        WHERE f.issue_id IS NOT NULL
          AND cardinality(f.covered_issue_ids) > 0
          AND NOT (f.issue_id = ANY(f.covered_issue_ids))
        """,
        nota="Si el archivo contiene el número al que está vinculado, su lista de cobertura debe "
             "incluirlo; si no, la relación se contradice.",
    ),
    Check(
        "D3b", "Un pack cubre números de series distintas", "S2",
        poblacion="SELECT count(*) FROM files WHERE cardinality(covered_issue_ids) > 0",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name, 'series',
                                  count(DISTINCT i.series_id),
                                  'numeros', jsonb_agg(i.issue_number ORDER BY i.issue_number),
                                  'titulos', jsonb_agg(DISTINCT s.title)) AS detalle
        FROM files f CROSS JOIN LATERAL unnest(f.covered_issue_ids) x
        JOIN issues i ON i.id = x
        JOIN series s ON s.id = i.series_id
        WHERE cardinality(f.covered_issue_ids) > 0
        GROUP BY f.id, f.file_name
        HAVING count(DISTINCT i.series_id) > 1
        """,
        nota="Un archivo puede contener un crossover, pero la lista de cobertura mezcla series y "
             "el catálogo no dice a qué publicación pertenece cada parte.",
    ),
    Check(
        "D3c", "Un pack que solo cubre un número", "S3",
        poblacion="SELECT count(*) FROM files WHERE cardinality(covered_issue_ids) > 0",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name,
                                  'cubiertos', f.covered_issue_ids) AS detalle
        FROM files f
        WHERE cardinality(f.covered_issue_ids) = 1
        """,
        nota="No es un pack; probablemente una relación mal anotada. Se informa, no se corrige.",
    ),
    Check(
        "D4a", "is_missing y missing_since se contradicen", "S2",
        poblacion="SELECT count(*) FROM files",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name, 'is_missing', f.is_missing,
                                  'missing_since', f.missing_since) AS detalle
        FROM files f
        WHERE (f.is_missing AND f.missing_since IS NULL)
           OR (NOT f.is_missing AND f.missing_since IS NOT NULL)
        """,
        nota="La lista de «Archivos no disponibles» ordena por `missing_since`; sin fecha, la "
             "fila aparece al final y el estado no cuadra con lo que se ve.",
    ),
    Check(
        "D4b", "La última comprobación de la biblioteca no acredita presencia", "S2",
        poblacion="SELECT count(*) FROM import_runs WHERE NOT (details ? 'kind')",
        casos="""
        WITH ciclo AS (
            SELECT id, started_at, details->'comprobacion_biblioteca' AS c
            FROM import_runs
            WHERE NOT (details ? 'kind') AND details ? 'comprobacion_biblioteca'
            ORDER BY started_at DESC LIMIT 1
        )
        SELECT id::text AS caso_id,
               jsonb_build_object('resultado', c->>'resultado', 'fecha', c->>'fecha',
                                  'ausentes', c->>'ausentes',
                                  'ciclo', started_at) AS detalle
        FROM ciclo
        WHERE (c->>'resultado') IS DISTINCT FROM 'comprobada'
           OR (CASE WHEN (c->>'fecha') ~ '^[0-9]{4}-'
                    THEN (c->>'fecha')::timestamptz END) < now() - interval '7 days'
        """,
        nota="Si el último ciclo no miró o no se fió de las rutas, «presente» es una creencia. No "
             "se recorre el disco: se lee lo que el ciclo anotó (docs/design/disponibilidad-231.md).",
    ),
    Check(
        "D4c", "Número poseído cuyos archivos faltan todos", "S2",
        poblacion="SELECT count(*) FROM issues i WHERE EXISTS (SELECT 1 FROM files f WHERE f.issue_id = i.id)",
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('issue_number', i.issue_number, 'titulo', s.title,
                                  'archivos', count(*),
                                  'missing_since', max(f.missing_since)) AS detalle
        FROM issues i
        JOIN series s ON s.id = i.series_id
        JOIN files f ON f.issue_id = i.id
        WHERE NOT (i.metadata ? 'cubierto_por_tomo')
        GROUP BY i.id, i.issue_number, s.title
        HAVING bool_and(f.is_missing)
        """,
        nota="El número figura en el catálogo pero no hay ningún archivo disponible: no cuenta "
             "como poseído. Si además está en Deseados, es E4.",
    ),
    Check(
        "D5", "Extensión declarada frente a formato real (#307)", "S3",
        poblacion="SELECT count(*) FROM files WHERE metadata ? 'formato_contenido'",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name,
                                  'declarado', f.file_format::text,
                                  'firma', f.metadata->'formato_contenido'->>'firma',
                                  'clase', f.metadata->'formato_contenido'->>'clase') AS detalle
        FROM files f
        WHERE f.metadata ? 'formato_contenido'
          AND (
            (f.file_format::text IN ('cbz', 'cb7')
             AND f.metadata->'formato_contenido'->>'firma' IS DISTINCT FROM 'zip')
            OR (f.file_format::text = 'cbr'
                AND f.metadata->'formato_contenido'->>'firma' NOT IN ('rar', 'zip'))
            OR (f.file_format::text = 'epub'
                AND f.metadata->'formato_contenido'->>'firma' IS DISTINCT FROM 'zip')
          )
        """,
        nota="Informativo: la extensión no se corrige en la base de datos (contrato #307). Un "
             "`.cbz` que por dentro es RAR no es un error de catálogo; sí explica una portada sin leer.",
    ),
    Check(
        "D6a", "Pendiente con un estado que no es unsorted", "S2",
        poblacion="SELECT count(*) FROM files WHERE issue_id IS NULL",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name,
                                  'match_status', f.metadata->>'match_status',
                                  'review_dismissed', f.review_dismissed) AS detalle
        FROM files f
        WHERE f.issue_id IS NULL
          AND NOT f.review_dismissed
          AND coalesce(f.metadata->>'match_status', '') <> 'unsorted'
        """,
        nota="La cola de «Por revisar» exige `issue_id IS NULL` y `match_status=unsorted` (o "
             "descartado). Un estado distinto rompe los contadores y el archivo no aparece.",
    ),
    Check(
        "D6b", "Vinculado a un número con match_status unsorted", "S2",
        poblacion="SELECT count(*) FROM files WHERE issue_id IS NOT NULL",
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('file_name', f.file_name, 'issue_id', f.issue_id,
                                  'match_status', f.metadata->>'match_status') AS detalle
        FROM files f
        WHERE f.issue_id IS NOT NULL AND f.metadata->>'match_status' = 'unsorted'
        """,
        nota="El archivo está vinculado pero se declara sin ordenar: la ficha lo enseña poseído y "
             "la cola de revisión no lo lista.",
    ),
])


# ── B9. Identidad de la serie frente a la fuente ────────────────────────────

CHECKS.extend([
    Check(
        "B9", "Serie con fuente sin identidad verificable o edición contradictoria", "S2",
        poblacion="""
        SELECT count(*)
        FROM series s
        WHERE s.metadata_source IS NOT NULL AND s.metadata_source <> 'manual'
        """,
        casos="""
        WITH actuales AS (
            SELECT s.id, s.metadata_source,
                   CASE s.metadata_source
                       WHEN 'comic_vine' THEN s.comic_vine_id::text
                       WHEN 'tebeosfera' THEN s.tebeosfera_slug
                       WHEN 'gcd' THEN s.gcd_id::text
                   END AS id_actual,
                   p.name AS editorial
            FROM series s
            LEFT JOIN publishers p ON p.id = s.publisher_id
            WHERE s.metadata_source IS NOT NULL AND s.metadata_source <> 'manual'
        )
        SELECT a.id::text AS caso_id,
               jsonb_build_object(
                   'subtipo', 'sin_registro_actual',
                   'fuente', a.metadata_source,
                   'id_actual', a.id_actual,
                   'registro_de_otro_id', EXISTS (
                       SELECT 1 FROM entity_source_records e2
                       WHERE e2.entity_type = 'series' AND e2.entity_id = a.id
                         AND e2.source = a.metadata_source
                         AND e2.external_id <> a.id_actual)
               ) AS detalle
        FROM actuales a
        WHERE NOT EXISTS (
            SELECT 1 FROM entity_source_records e
            WHERE e.entity_type = 'series' AND e.entity_id = a.id
              AND e.source = a.metadata_source AND e.external_id = a.id_actual)
        UNION ALL
        SELECT a.id::text,
               jsonb_build_object(
                   'subtipo', 'edicion_contradictoria',
                   'editorial_local', a.editorial,
                   'editorial_fuente',
                   e.payload->'normalizado'->'edition_scope'->>'publisher_name') AS detalle
        FROM actuales a
        JOIN entity_source_records e
          ON e.entity_type = 'series' AND e.entity_id = a.id
         AND e.source = a.metadata_source AND e.external_id = a.id_actual
        WHERE a.editorial IS NOT NULL
          AND e.payload->'normalizado'->'edition_scope'->>'publisher_name' IS NOT NULL
          AND lower(btrim(a.editorial)) NOT LIKE '%' || lower(btrim(
              e.payload->'normalizado'->'edition_scope'->>'publisher_name')) || '%'
          AND lower(btrim(
              e.payload->'normalizado'->'edition_scope'->>'publisher_name'))
              NOT LIKE '%' || lower(btrim(a.editorial)) || '%'
        """,
        nota="El título puede diferir por la edición (original frente a edición española) y no se "
             "cuenta; los años ±1 tampoco. Se mide que el id vivo tenga registro de la fuente actual "
             "(identidad verificable) y que la editorial no contradiga la edición del id; una editorial "
             "vacía es completitud, no contradicción, y «Image Comics» contiene «Image».",
    ),
])


# ── E. Totales, completitud y huecos ──────────────────────────────────────────

#: Estados de un deseo que todavía puede disparar una búsqueda o una descarga.
#: `imported` y `retirado` son terminales; `downloaded` espera importación y
#: también se revisa porque un archivo redundante se descargó para nada.
_WISHLIST_ACTIVA = "('wanted', 'searching', 'downloading', 'downloaded', 'failed')"

CHECKS.extend([
    Check(
        "E1", "Total de números sin unidad acreditada", "S3",
        poblacion="""
        SELECT count(*) FROM series
        WHERE total_issues IS NOT NULL AND kind::text <> 'one_shot'
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'total_issues', s.total_issues,
                                  'metadata_source', coalesce(s.metadata_source, '(sin fuente)'),
                                  'tradition', s.tradition::text) AS detalle
        FROM series s
        WHERE s.total_issues IS NOT NULL AND s.kind::text <> 'one_shot'
          AND (s.metadata_source IS NULL
               OR s.metadata_source NOT IN ('comic_vine'))
        """,
        nota="`UNIDAD_DE_GRAPA` solo acredita Comic Vine. La app ya se niega a calcular huecos, "
             "pero la ficha sigue enseñando un total que puede ser de capítulos o de otra edición.",
    ),
    Check(
        "E2", "Total copiado del volumen original con Deseados activos", "S1",
        poblacion="""
        SELECT count(*) FROM series
        WHERE tradition::text IN ('tebeo', 'hispanoamericano')
          AND comic_vine_id IS NOT NULL AND total_issues IS NOT NULL
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'total_issues', s.total_issues,
                                  'total_de_la_fuente',
                                  esr.payload->'normalizado'->'edition_scope'->>'total_issues',
                                  'wishlist_policy', s.wishlist_policy::text,
                                  'deseos_activos', (
                                      SELECT count(*) FROM wishlist w
                                      WHERE w.series_id = s.id
                                        AND w.status::text IN ('wanted', 'searching',
                                                               'downloading', 'downloaded',
                                                               'failed'))) AS detalle
        FROM series s
        JOIN LATERAL (
            SELECT e.payload FROM entity_source_records e
            WHERE e.entity_type = 'series' AND e.entity_id = s.id
              AND e.source = 'comic_vine'
            ORDER BY e.fetched_at DESC LIMIT 1
        ) esr ON true
        WHERE s.tradition::text IN ('tebeo', 'hispanoamericano')
          AND s.comic_vine_id IS NOT NULL AND s.total_issues IS NOT NULL
          AND (esr.payload->'normalizado'->'edition_scope'->>'total_issues') ~ '^[0-9]+$'
          AND (esr.payload->'normalizado'->'edition_scope'->>'total_issues')::int
              = s.total_issues
          AND (s.wishlist_policy::text <> 'ninguno'
               OR EXISTS (SELECT 1 FROM wishlist w
                          WHERE w.series_id = s.id
                            AND w.status::text IN ('wanted', 'searching', 'downloading',
                                                   'downloaded', 'failed')))
        """,
        nota="B2 + P2: el total es el del volumen USA y hay Deseados que lo usan para pedir "
             "números que no existen en la edición española. S1 porque dispara búsquedas.",
    ),
    Check(
        "E3", "Decisión «no completar» con búsquedas de política vivas", "S2",
        poblacion="""
        SELECT count(*) FROM series
        WHERE metadata->'coleccion' ? 'no_completar'
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title,
                                  'no_completar', s.metadata->'coleccion'->>'no_completar',
                                  'wishlist_policy', s.wishlist_policy::text,
                                  'deseos_de_politica', (
                                      SELECT count(*) FROM wishlist w
                                      WHERE w.series_id = s.id
                                        AND w.origen::text = 'politica'
                                        AND w.status::text IN ('wanted', 'searching',
                                                               'downloading', 'failed'))) AS detalle
        FROM series s
        WHERE s.metadata->'coleccion'->>'no_completar' = 'true'
          AND (s.wishlist_policy::text <> 'ninguno'
               OR EXISTS (SELECT 1 FROM wishlist w
                          WHERE w.series_id = s.id
                            AND w.origen::text = 'politica'
                            AND w.status::text IN ('wanted', 'searching', 'downloading',
                                                   'failed')))
        """,
        nota="#340 no persiste «completa»/«faltan» (es derivado): lo único guardado es la "
             "decisión `no_completar`. La contradicción real es esa decisión con la política o "
             "los Deseados generados que la ignoran.",
    ),
    Check(
        "E4a", "Deseo activo de un número que ya tiene archivo disponible", "S1",
        poblacion=f"""
        SELECT count(*) FROM wishlist w JOIN issues i ON i.id = w.issue_id
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
        """,
        casos=f"""
        SELECT w.id::text AS caso_id,
               jsonb_build_object('status', w.status::text, 'origen', w.origen::text,
                                  'numero', i.issue_number, 'titulo', s.title,
                                  'archivos_disponibles', (
                                      SELECT count(*) FROM files f
                                      WHERE f.issue_id = i.id AND NOT f.is_missing)) AS detalle
        FROM wishlist w
        JOIN issues i ON i.id = w.issue_id
        JOIN series s ON s.id = i.series_id
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
          AND EXISTS (SELECT 1 FROM files f
                      WHERE f.issue_id = i.id AND NOT f.is_missing)
        """,
        nota="S1: el deseo hará buscar y descargar lo que ya está. Distinto de un deseo de "
             "política que el orquestador retira al detectar el archivo; aquí sigue activo.",
    ),
    Check(
        "E4b", "Deseo activo de un número fuera del total acreditado", "S1",
        poblacion=f"""
        SELECT count(*) FROM wishlist w
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
          AND (w.numero IS NOT NULL OR w.issue_id IS NOT NULL)
        """,
        casos=f"""
        SELECT w.id::text AS caso_id,
               jsonb_build_object('subtipo', 'numero_de_serie',
                                  'status', w.status::text, 'origen', w.origen::text,
                                  'numero', w.numero, 'titulo', s.title,
                                  'total_issues', s.total_issues) AS detalle
        FROM wishlist w JOIN series s ON s.id = w.series_id
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
          AND w.numero IS NOT NULL
          AND s.metadata_source = 'comic_vine' AND s.total_issues > 0
          AND (w.numero < 1 OR w.numero > s.total_issues)
        UNION ALL
        SELECT w.id::text,
               jsonb_build_object('subtipo', 'issue_fuera_del_total',
                                  'status', w.status::text, 'origen', w.origen::text,
                                  'numero', i.issue_number, 'titulo', s.title,
                                  'total_issues', s.total_issues)
        FROM wishlist w
        JOIN issues i ON i.id = w.issue_id
        JOIN series s ON s.id = i.series_id
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
          AND s.metadata_source = 'comic_vine' AND s.total_issues > 0
          AND i.issue_number ~ '^[0-9]+$'
          AND i.issue_number::int NOT BETWEEN 1 AND s.total_issues
        """,
        nota="S1: pide un número que la edición acreditada no tiene (por un total equivocado o "
             "porque el número está mal). Genera búsquedas que no pueden terminar bien.",
    ),
    Check(
        "E4c", "Deseo activo por número que ya está poseído", "S1",
        poblacion=f"""
        SELECT count(*) FROM wishlist w
        WHERE w.status::text IN {_WISHLIST_ACTIVA} AND w.numero IS NOT NULL
        """,
        casos=f"""
        SELECT w.id::text AS caso_id,
               jsonb_build_object('status', w.status::text, 'origen', w.origen::text,
                                  'numero', w.numero, 'titulo', s.title,
                                  'poseido', true) AS detalle
        FROM wishlist w JOIN series s ON s.id = w.series_id
        WHERE w.status::text IN {_WISHLIST_ACTIVA}
          AND w.numero IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM issues i
              WHERE i.series_id = s.id
                AND i.format::text = 'single_issue'
                AND i.issue_number ~ '^[0-9]+$'
                AND i.issue_number::int = w.numero
                AND (EXISTS (SELECT 1 FROM files f
                             WHERE f.issue_id = i.id AND NOT f.is_missing)
                     OR i.metadata ? 'cubierto_por_tomo'))
        """,
        nota="El item de política pide un número que la biblioteca ya tiene como grapa con "
             "archivo. Se distingue de E4a (deseo ligado a un `issue_id`) por pedirlo con "
             "`numero`.",
    ),
])


# ── F. Coherencia semántica de atributos ──────────────────────────────────────

CHECKS.extend([
    Check(
        "F1a", "start_year posterior a end_year", "S3",
        poblacion="""
        SELECT count(*) FROM series
        WHERE start_year IS NOT NULL AND end_year IS NOT NULL
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'inicio', s.start_year,
                                  'fin', s.end_year) AS detalle
        FROM series s
        WHERE s.start_year IS NOT NULL AND s.end_year IS NOT NULL
          AND s.start_year > s.end_year
        """,
        nota="Una serie que termina antes de empezar rompe el orden y el filtro por años.",
    ),
    Check(
        "F1b", "Año de serie imposible (antes de 1890 o en el futuro)", "S3",
        poblacion="""
        SELECT count(*) FROM series
        WHERE start_year IS NOT NULL OR end_year IS NOT NULL
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'inicio', s.start_year,
                                  'fin', s.end_year) AS detalle
        FROM series s
        WHERE (s.start_year IS NOT NULL
               AND (s.start_year < 1890 OR s.start_year > extract(year FROM now()) + 2))
           OR (s.end_year IS NOT NULL
               AND (s.end_year < 1890 OR s.end_year > extract(year FROM now()) + 2))
        """,
        nota="1890 es el límite inferior del proyecto; +2 años da margen a un anuncio ya "
             "publicado. No se corrige: se pregunta.",
    ),
    Check(
        "F1c", "Fecha de un número fuera de los años de su serie", "S3",
        poblacion="""
        SELECT count(*) FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.release_date IS NOT NULL
          AND (s.start_year IS NOT NULL OR s.end_year IS NOT NULL)
        """,
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('numero', i.issue_number, 'titulo', s.title,
                                  'release_date', i.release_date,
                                  'serie_desde', s.start_year, 'serie_hasta', s.end_year) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.release_date IS NOT NULL
          AND ((s.start_year IS NOT NULL
                AND extract(year FROM i.release_date) < s.start_year - 2)
               OR (s.end_year IS NOT NULL
                   AND extract(year FROM i.release_date) > s.end_year + 2))
        """,
        nota="Margen de 2 años (un anual o un recopilatorio puede salir después). Si la fecha es "
             "de otra edición, el número está mal vinculado o la fecha es de la fuente equivocada.",
    ),
    Check(
        "F1d", "end_year puesto con la serie en curso", "S3",
        poblacion="SELECT count(*) FROM series WHERE end_year IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'fin', s.end_year, 'status', s.status) AS detalle
        FROM series s
        WHERE s.end_year IS NOT NULL AND s.status = 'ongoing'
        """,
        nota="`status` es texto libre y puede venir de la fuente; el año de fin y «en curso» no "
             "pueden ser ciertos a la vez.",
    ),
    Check(
        "F2a", "Editorial española con tradición americana", "S3",
        poblacion="""
        SELECT count(*) FROM series s JOIN publishers p ON p.id = s.publisher_id
        WHERE s.tradition::text = 'american'
        """,
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'editorial', p.name,
                                  'pais', p.country, 'tradition', s.tradition::text,
                                  'language', s.language) AS detalle
        FROM series s JOIN publishers p ON p.id = s.publisher_id
        WHERE s.tradition::text = 'american'
          AND (p.country ~* '(espa|spain)'
               OR f_title_norm(p.name) ~
                  '(panini|ecc|planeta|norma|astiberri|dolmen|glenat|forum|zinco|bruguera|iberia)')
        """,
        nota="Una editorial española puede publicar material USA: la tradición `american` sería "
             "correcta para la obra y falsa para la edición. Es la misma frontera de B2; se mide "
             "antes de contarlo.",
    ),
    Check(
        "F2b", "Idioma japonés en una serie que no es manga", "S3",
        poblacion="SELECT count(*) FROM series WHERE language IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'language', s.language,
                                  'tradition', s.tradition::text) AS detalle
        FROM series s
        WHERE s.language = 'ja' AND s.tradition::text NOT IN ('manga', 'manhwa', 'manhua')
        """,
        nota="Solo el caso inequívoco: japonés fuera de manga. «Español» con `american` es una "
             "edición española legítima y no se cuenta.",
    ),
    Check(
        "F3a", "Serie anual sin serie madre", "S3",
        poblacion="SELECT count(*) FROM series WHERE kind::text = 'annual'",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'start_year', s.start_year,
                                  'parent_series_id', s.parent_series_id) AS detalle
        FROM series s
        WHERE s.kind::text = 'annual' AND s.parent_series_id IS NULL
        """,
        nota="El anual es una línea propia con padre (ADR 0003). Sin padre no se puede agrupar "
             "con su serie y la ficha lo enseña suelto.",
    ),
    Check(
        "F3b", "Serie anual con padre de otra editorial", "S3",
        poblacion="SELECT count(*) FROM series WHERE parent_series_id IS NOT NULL",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('titulo', s.title, 'padre', p.title,
                                  'editorial_hijo', ph.name, 'editorial_padre', pp.name) AS detalle
        FROM series s
        JOIN series p ON p.id = s.parent_series_id
        LEFT JOIN publishers ph ON ph.id = s.publisher_id
        LEFT JOIN publishers pp ON pp.id = p.publisher_id
        WHERE s.publisher_id IS NOT NULL AND p.publisher_id IS NOT NULL
          AND s.publisher_id <> p.publisher_id
        """,
        nota="Un anual de otra editorial puede existir (licencia), pero es raro y explica una "
             "relación mal puesta. Se pregunta.",
    ),
    Check(
        "F4a", "Sinopsis con HTML o entidades sin limpiar", "S3",
        poblacion="SELECT count(*) FROM issues WHERE synopsis IS NOT NULL",
        casos="""
        SELECT i.id::text AS caso_id,
               jsonb_build_object('numero', i.issue_number, 'titulo', s.title,
                                  'sinopsis', left(i.synopsis, 160)) AS detalle
        FROM issues i JOIN series s ON s.id = i.series_id
        WHERE i.synopsis ~ '&(amp|lt|gt|quot|#39|nbsp);|</?[a-zA-Z][^>]*>'
        """,
        nota="La sinopsis se copia de la fuente con su marcado (`<p>`, `<br>`, `&amp;`). Es un "
             "defecto vivo del enricher, no de la ficha; 583 casos en la medición del 2026-11-20.",
    ),
    Check(
        "F4b", "Títulos, orden y sinopsis con ruido de texto", "S3",
        poblacion="SELECT count(*) FROM series",
        casos="""
        SELECT s.id::text AS caso_id,
               jsonb_build_object('subtipo', 'titulo.espacios', 'titulo', s.title,
                                  'sort_title', s.sort_title) AS detalle
        FROM series s
        WHERE s.title ~ '\\s\\s' OR s.title <> btrim(s.title)
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('subtipo', 'titulo.sufijo_de_archivo', 'titulo', s.title)
        FROM series s
        WHERE s.title ~* '\\([12][0-9]{3}\\)|\\[digital\\]|\\yc2c\\y|\\yv[0-9]+\\y|\\y(scan|webrip|cbz|cbr)\\y'
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('subtipo', 'titulo.mayusculas', 'titulo', s.title)
        FROM series s
        WHERE s.title = upper(s.title) AND s.title ~ '[A-ZÁÉÍÓÚÑ]{4}'
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('subtipo', 'sort_title.no_corresponde', 'titulo', s.title,
                                  'sort_title', s.sort_title)
        FROM series s
        WHERE s.sort_title IS NOT NULL
          AND f_title_norm(s.sort_title) <> f_title_norm(
              regexp_replace(s.title, '^(el|la|los|las|the|a|an)\\s+', '', 'i'))
          AND f_title_norm(s.sort_title) <> f_title_norm(s.title)
        UNION ALL
        SELECT s.id::text,
               jsonb_build_object('subtipo', 'titulo.mojibake', 'titulo', s.title)
        FROM series s
        WHERE s.title ~ '(Ã.|Â.|â€)'
        """,
        nota="Ruido de superficie, no identidad. Los sufijos de archivo en el título son la "
             "huella de un alta desde el nombre; el sort_title solo se compara con artículos. "
             "En la medición del 2026-11-20 son 12 casos frente a los 583 de F4a.",
    ),
    Check(
        "F5", "locked_fields con nombres que no existen en el modelo", "S3",
        poblacion="""
        SELECT (SELECT count(*) FROM series WHERE cardinality(locked_fields) > 0)
             + (SELECT count(*) FROM issues WHERE cardinality(locked_fields) > 0)
             + (SELECT count(*) FROM creators WHERE cardinality(locked_fields) > 0)
             + (SELECT count(*) FROM characters WHERE cardinality(locked_fields) > 0)
        """,
        casos="""
        WITH validos(entidad, campo) AS (
            VALUES
            ('serie','id'),('serie','title'),('serie','sort_title'),('serie','title_norm'),
            ('serie','volume'),('serie','favorite'),('serie','language'),('serie','edition_kind'),
            ('serie','reference_name'),('serie','publisher_id'),('serie','imprint_id'),
            ('serie','universe_id'),('serie','tradition'),('serie','kind'),
            ('serie','parent_series_id'),('serie','start_year'),('serie','end_year'),
            ('serie','total_issues'),('serie','status'),('serie','description'),
            ('serie','comic_vine_id'),('serie','anilist_id'),('serie','tebeosfera_slug'),
            ('serie','gcd_id'),('serie','metron_id'),('serie','open_library_id'),
            ('serie','fandom_dc_slug'),('serie','fandom_marvel_slug'),('serie','cover_url'),
            ('serie','metadata'),('serie','metadata_source'),('serie','enrichment_attempted_at'),
            ('serie','locked_fields'),('serie','wishlist_policy'),('serie','follow_new_issues'),
            ('serie','follow_new_issues_since'),('serie','genres'),('serie','tags'),
            ('serie','characters'),
            ('issue','id'),('issue','series_id'),('issue','issue_number'),('issue','number_key'),
            ('issue','volume'),('issue','title'),('issue','release_date'),('issue','format'),
            ('issue','page_count'),('issue','isbn'),('issue','synopsis'),('issue','cover_url'),
            ('issue','comic_vine_id'),('issue','gcd_id'),('issue','metron_id'),
            ('issue','anilist_id'),('issue','tebeosfera_slug'),('issue','fandom_dc_slug'),
            ('issue','fandom_marvel_slug'),('issue','sort_order'),('issue','metadata'),
            ('issue','metadata_source'),('issue','enrichment_attempted_at'),
            ('issue','upgrade_scanned_at'),('issue','locked_fields'),('issue','characters'),
            ('issue','tags'),('issue','credits'),
            ('creator','id'),('creator','name'),('creator','name_norm'),('creator','sort_name'),
            ('creator','nationality'),('creator','birth_year'),('creator','death_year'),
            ('creator','biography'),('creator','comic_vine_id'),('creator','photo_url'),
            ('creator','metadata'),('creator','metadata_source'),('creator','locked_fields'),
            ('character','id'),('character','name'),('character','real_name'),
            ('character','universe_id'),('character','publisher_id'),
            ('character','first_appearance_year'),('character','description'),
            ('character','comic_vine_id'),('character','image_url'),('character','metadata'),
            ('character','metadata_source'),('character','locked_fields')
        )
        SELECT x.id::text AS caso_id,
               jsonb_build_object('entidad', 'serie', 'titulo', x.title,
                                  'campo', c.campo) AS detalle
        FROM series x CROSS JOIN LATERAL unnest(x.locked_fields) AS c(campo)
        WHERE c.campo <> ''
          AND NOT EXISTS (SELECT 1 FROM validos v
                          WHERE v.entidad = 'serie' AND v.campo = c.campo)
        UNION ALL
        SELECT x.id::text,
               jsonb_build_object('entidad', 'issue', 'numero', x.issue_number,
                                  'campo', c.campo)
        FROM issues x CROSS JOIN LATERAL unnest(x.locked_fields) AS c(campo)
        WHERE c.campo <> ''
          AND NOT EXISTS (SELECT 1 FROM validos v
                          WHERE v.entidad = 'issue' AND v.campo = c.campo)
        UNION ALL
        SELECT x.id::text,
               jsonb_build_object('entidad', 'creator', 'nombre', x.name, 'campo', c.campo)
        FROM creators x CROSS JOIN LATERAL unnest(x.locked_fields) AS c(campo)
        WHERE c.campo <> ''
          AND NOT EXISTS (SELECT 1 FROM validos v
                          WHERE v.entidad = 'creator' AND v.campo = c.campo)
        UNION ALL
        SELECT x.id::text,
               jsonb_build_object('entidad', 'character', 'nombre', x.name, 'campo', c.campo)
        FROM characters x CROSS JOIN LATERAL unnest(x.locked_fields) AS c(campo)
        WHERE c.campo <> ''
          AND NOT EXISTS (SELECT 1 FROM validos v
                          WHERE v.entidad = 'character' AND v.campo = c.campo)
        """,
        nota="Un nombre mal escrito en `locked_fields` no protege nada: el enricher lo pisa y la "
             "persona cree que está bloqueado.",
    ),
])


# ── G. Duplicados de entidades ────────────────────────────────────────────────

CHECKS.extend([
    Check(
        "G1", "Series duplicadas con título, año y editorial compatibles", "S2",
        poblacion="SELECT count(*) FROM series WHERE title_norm IS NOT NULL",
        casos="""
        SELECT (a.id::text || '|' || b.id::text) AS caso_id,
               jsonb_build_object('titulo_a', a.title, 'titulo_b', b.title,
                                  'anio_a', a.start_year, 'anio_b', b.start_year,
                                  'editorial_a', pa.name, 'editorial_b', pb.name,
                                  'id_a', a.id, 'id_b', b.id,
                                  'cv_a', a.comic_vine_id, 'cv_b', b.comic_vine_id) AS detalle
        FROM series a
        JOIN series b ON a.id < b.id AND a.title_norm = b.title_norm
        LEFT JOIN publishers pa ON pa.id = a.publisher_id
        LEFT JOIN publishers pb ON pb.id = b.publisher_id
        WHERE (a.start_year IS NULL OR b.start_year IS NULL
               OR abs(a.start_year - b.start_year) <= 1)
          AND (a.publisher_id IS NULL OR b.publisher_id IS NULL
               OR a.publisher_id = b.publisher_id)
          AND NOT (a.comic_vine_id IS NOT NULL AND b.comic_vine_id IS NOT NULL
                   AND a.comic_vine_id <> b.comic_vine_id)
          AND NOT (a.anilist_id IS NOT NULL AND b.anilist_id IS NOT NULL
                   AND a.anilist_id <> b.anilist_id)
          AND NOT (a.tebeosfera_slug IS NOT NULL AND b.tebeosfera_slug IS NOT NULL
                   AND a.tebeosfera_slug <> b.tebeosfera_slug)
        """,
        nota="ADR 0003: dos ediciones (original y reedición) son series distintas legítimas. "
             "Aquí solo se juntan las que comparten título normalizado, año ±1 y editorial, y "
             "no se distinguen por id de fuente. La fusión es siempre decisión del PO.",
    ),
    Check(
        "G2a", "Editoriales duplicadas", "S3",
        poblacion="SELECT count(*) FROM publishers",
        casos="""
        SELECT a.id::text AS caso_id,
               jsonb_build_object('nombre_a', a.name, 'nombre_b', b.name,
                                  'pais_a', a.country, 'pais_b', b.country) AS detalle
        FROM publishers a JOIN publishers b ON a.id < b.id
         AND f_title_norm(a.name) = f_title_norm(b.name)
        """,
        nota="«ECC» frente a «ECC Ediciones». No se fusiona: dos editoriales con el mismo nombre "
             "normalizado parten las series.",
    ),
    Check(
        "G2b", "Sellos duplicados dentro de la misma editorial", "S3",
        poblacion="SELECT count(*) FROM imprints",
        casos="""
        SELECT a.id::text AS caso_id,
               jsonb_build_object('sello_a', a.name, 'sello_b', b.name,
                                  'publisher_id', a.publisher_id,
                                  'editorial', p.name) AS detalle
        FROM imprints a
        JOIN imprints b ON a.id < b.id AND a.publisher_id = b.publisher_id
         AND f_title_norm(a.name) = f_title_norm(b.name)
        JOIN publishers p ON p.id = a.publisher_id
        """,
        nota="El UNIQUE es (publisher_id, name) exacto; la normalización descubre el duplicado "
             "con tilde o mayúsculas.",
    ),
    Check(
        "G2c", "Creadores duplicados (mismo nombre normalizado)", "S3",
        poblacion="SELECT count(*) FROM creators",
        casos="""
        SELECT a.id::text AS caso_id,
               jsonb_build_object('nombre_a', a.name, 'nombre_b', b.name,
                                  'norm', a.name_norm) AS detalle
        FROM creators a JOIN creators b ON a.id < b.id AND a.name_norm = b.name_norm
        WHERE a.name_norm IS NOT NULL AND a.name_norm <> ''
        """,
        nota="`name_norm` ya quita tildes y colapsa espacios: dos filas así son el mismo autor "
             "para el coleccionista y reparten los créditos.",
    ),
    Check(
        "G3", "Alias contradictorios entre la tabla local y la importada", "S2",
        poblacion="""
        SELECT count(*) FROM local_aliases
        WHERE estado::text IN ('activo', 'propuesto')
        """,
        casos="""
        SELECT la.id::text AS caso_id,
               jsonb_build_object('patron', la.pattern_norm,
                                  'scope_local', la.scope_path,
                                  'serie_local', la.series_id,
                                  'serie_importada', ai.series_id,
                                  'estado_local', la.estado::text,
                                  'alias_importado', ai.alias_id) AS detalle
        FROM local_aliases la
        JOIN alias_importado ai
          ON ai.patron_norm = la.pattern_norm
         AND coalesce(ai.scope_path, '') = coalesce(la.scope_path, '')
        WHERE la.estado::text IN ('activo', 'propuesto')
          AND ai.vigente_hasta IS NULL AND ai.estado::text = 'activo'
          AND ai.series_id <> la.series_id
        """,
        nota="Cada tabla impone su unicidad, pero no entre ellas: el mismo patrón y alcance "
             "apuntan a dos series. El matcher aplica la local; el inventario enseña la importada.",
    ),
    Check(
        "G4a", "Colecciones vacías", "S3",
        poblacion="SELECT count(*) FROM collections",
        casos="""
        SELECT c.id::text AS caso_id,
               jsonb_build_object('nombre', c.name, 'auto_search', c.auto_search::text) AS detalle
        FROM collections c
        WHERE NOT EXISTS (SELECT 1 FROM collection_series cs WHERE cs.collection_id = c.id)
        """,
        nota="Una colección sin series no agrupa nada; si tiene política de auto-búsqueda, "
             "tampoco puede aplicarla.",
    ),
    Check(
        "G4b", "Orden de lectura de una saga duplicado o con huecos", "S3",
        poblacion="""
        SELECT count(*) FROM story_arcs sa
        WHERE EXISTS (SELECT 1 FROM story_arc_issues sai WHERE sai.story_arc_id = sa.id)
        """,
        casos="""
        SELECT sai.story_arc_id::text AS caso_id,
               jsonb_build_object('subtipo', 'orden_duplicado',
                                  'orden', sai.reading_order, 'n', count(*),
                                  'saga', sa.title) AS detalle
        FROM story_arc_issues sai JOIN story_arcs sa ON sa.id = sai.story_arc_id
        GROUP BY sai.story_arc_id, sai.reading_order, sa.title
        HAVING count(*) > 1
        UNION ALL
        SELECT sai.story_arc_id::text,
               jsonb_build_object('subtipo', 'huecos_en_orden', 'saga', sa.title,
                                  'min', min(sai.reading_order),
                                  'max', max(sai.reading_order),
                                  'distintos', count(DISTINCT sai.reading_order))
        FROM story_arc_issues sai JOIN story_arcs sa ON sa.id = sai.story_arc_id
        GROUP BY sai.story_arc_id, sa.title
        HAVING max(sai.reading_order) - min(sai.reading_order) + 1
               <> count(DISTINCT sai.reading_order)
        """,
        nota="El orden es lo que lee la persona. Un empate o un hueco no rompe la app, pero "
             "hace que «Sagas en orden» mienta.",
    ),
])


# ── H. Procedencia y protección ───────────────────────────────────────────────

CHECKS.extend([
    Check(
        "H1", "Campos atribuidos a una fuente sin procedencia registrada", "S3",
        poblacion="""
        WITH campos(campo) AS (
            VALUES ('total_issues'), ('start_year'), ('end_year'), ('description'),
                   ('cover_url'), ('status')
        )
        SELECT count(*) FROM series s CROSS JOIN campos c
        WHERE s.metadata_source IS NOT NULL AND s.metadata_source <> 'manual'
          AND (CASE c.campo
                   WHEN 'total_issues' THEN s.total_issues IS NOT NULL
                   WHEN 'start_year' THEN s.start_year IS NOT NULL
                   WHEN 'end_year' THEN s.end_year IS NOT NULL
                   WHEN 'description' THEN s.description IS NOT NULL
                   WHEN 'cover_url' THEN s.cover_url IS NOT NULL
                   WHEN 'status' THEN s.status IS NOT NULL
               END)
        """,
        casos="""
        WITH campos(campo) AS (
            VALUES ('total_issues'), ('start_year'), ('end_year'), ('description'),
                   ('cover_url'), ('status')
        )
        SELECT (s.id::text || '|' || c.campo) AS caso_id,
               jsonb_build_object('titulo', s.title, 'campo', c.campo,
                                  'metadata_source', s.metadata_source) AS detalle
        FROM series s CROSS JOIN campos c
        WHERE s.metadata_source IS NOT NULL AND s.metadata_source <> 'manual'
          AND (CASE c.campo
                   WHEN 'total_issues' THEN s.total_issues IS NOT NULL
                   WHEN 'start_year' THEN s.start_year IS NOT NULL
                   WHEN 'end_year' THEN s.end_year IS NOT NULL
                   WHEN 'description' THEN s.description IS NOT NULL
                   WHEN 'cover_url' THEN s.cover_url IS NOT NULL
                   WHEN 'status' THEN s.status IS NOT NULL
               END)
          AND NOT EXISTS (SELECT 1 FROM field_provenance fp
                          WHERE fp.entity_type = 'series' AND fp.entity_id = s.id
                            AND fp.field = c.campo)
        """,
        nota="`procedencia.py` lo llama «origen no registrado». No se atribuye a «manual» por "
             "descarte: solo se cuenta lo que la fila declara de una fuente y no tiene registro.",
    ),
    Check(
        "H2", "field_provenance contradice el valor actual sin bloqueo", "S2",
        poblacion="""
        SELECT count(*) FROM field_provenance
        WHERE entity_type = 'series'
          AND field IN ('title', 'start_year', 'end_year', 'total_issues',
                        'description', 'cover_url', 'status')
        """,
        casos="""
        SELECT (s.id::text || '|' || fp.field) AS caso_id,
               jsonb_build_object('titulo', s.title, 'campo', fp.field,
                                  'valor_procedencia', fp.value,
                                  'valor_actual', CASE fp.field
                                      WHEN 'title' THEN to_jsonb(s.title)
                                      WHEN 'start_year' THEN to_jsonb(s.start_year)
                                      WHEN 'end_year' THEN to_jsonb(s.end_year)
                                      WHEN 'total_issues' THEN to_jsonb(s.total_issues)
                                      WHEN 'description' THEN to_jsonb(s.description)
                                      WHEN 'cover_url' THEN to_jsonb(s.cover_url)
                                      WHEN 'status' THEN to_jsonb(s.status)
                                  END,
                                  'procedencia', fp.source,
                                  'locked', fp.locked) AS detalle
        FROM field_provenance fp
        JOIN series s ON s.id = fp.entity_id
        WHERE fp.entity_type = 'series'
          AND fp.field IN ('title', 'start_year', 'end_year', 'total_issues',
                           'description', 'cover_url', 'status')
          AND NOT fp.locked
          AND NOT (fp.field = ANY(coalesce(s.locked_fields, '{}'::varchar[])))
          AND fp.value IS DISTINCT FROM (CASE fp.field
                  WHEN 'title' THEN to_jsonb(s.title)
                  WHEN 'start_year' THEN to_jsonb(s.start_year)
                  WHEN 'end_year' THEN to_jsonb(s.end_year)
                  WHEN 'total_issues' THEN to_jsonb(s.total_issues)
                  WHEN 'description' THEN to_jsonb(s.description)
                  WHEN 'cover_url' THEN to_jsonb(s.cover_url)
                  WHEN 'status' THEN to_jsonb(s.status)
              END)
        """,
        nota="La fuente trajo un valor y la fila tiene otro sin que el campo esté bloqueado: "
             "alguien o algo lo cambió sin registro. No se revierte: se señala.",
    ),
    Check(
        "H3", "Discrepancias pendientes acumuladas", "S3",
        poblacion="""
        SELECT count(*) FROM files
        WHERE jsonb_typeof(metadata->'discrepancias') = 'array'
        """,
        casos="""
        SELECT f.id::text AS caso_id,
               jsonb_build_object('pendientes', count(*),
                                  'mas_antigua', min(e->>'observada_en'),
                                  'origenes', jsonb_agg(DISTINCT e->>'origen'),
                                  'file_name', f.file_name) AS detalle
        FROM files f CROSS JOIN LATERAL jsonb_array_elements(f.metadata->'discrepancias') e
        WHERE jsonb_typeof(f.metadata->'discrepancias') = 'array'
          AND e->>'estado' = 'pendiente'
        GROUP BY f.id, f.file_name
        """,
        nota="Son trabajo para la persona, no defectos del catálogo. Se informa del volumen y la "
             "antigüedad para que el PO priorice; no se toca ninguna.",
    ),
])


# ── I. Estado derivado y caches ──────────────────────────────────────────────

CHECKS.extend([
    Check(
        "I1", "reading_progress incoherente", "S3",
        poblacion="SELECT count(*) FROM reading_progress",
        casos="""
        SELECT rp.id::text AS caso_id,
               jsonb_build_object('subtipo', 'pagina_mayor_que_total',
                                  'current_page', rp.current_page,
                                  'page_count', i.page_count) AS detalle
        FROM reading_progress rp JOIN issues i ON i.id = rp.issue_id
        WHERE i.page_count IS NOT NULL AND rp.current_page > i.page_count
        UNION ALL
        SELECT rp.id::text,
               jsonb_build_object('subtipo', 'completado_sin_fecha',
                                  'status', rp.status::text)
        FROM reading_progress rp
        WHERE rp.status::text = 'completed' AND rp.completed_at IS NULL
        UNION ALL
        SELECT rp.id::text,
               jsonb_build_object('subtipo', 'inicio_posterior_al_fin',
                                  'started_at', rp.started_at, 'completed_at', rp.completed_at)
        FROM reading_progress rp
        WHERE rp.started_at IS NOT NULL AND rp.completed_at IS NOT NULL
          AND rp.started_at > rp.completed_at
        UNION ALL
        SELECT rp.id::text,
               jsonb_build_object('subtipo', 'sin_ningun_archivo',
                                  'issue_id', rp.issue_id)
        FROM reading_progress rp
        WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.issue_id = rp.issue_id)
        """,
        nota="Estado derivado que se enseña en la ficha; una página imposible o un progreso sin "
             "archivo hacen que «continuar leyendo» lleve a un sitio que no existe.",
    ),
    Check(
        "I2", "Mejoras sobre archivos de otro número o pendientes viejas", "S3",
        poblacion="SELECT count(*) FROM upgrade_proposals",
        casos="""
        SELECT up.id::text AS caso_id,
               jsonb_build_object('subtipo', 'archivo_de_otro_numero',
                                  'issue_id', up.issue_id, 'file_id', up.file_id,
                                  'issue_del_archivo', f.issue_id,
                                  'status', up.status) AS detalle
        FROM upgrade_proposals up
        LEFT JOIN files f ON f.id = up.file_id
        WHERE up.file_id IS NOT NULL AND f.issue_id IS DISTINCT FROM up.issue_id
        UNION ALL
        SELECT up.id::text,
               jsonb_build_object('subtipo', 'pendiente_antigua',
                                  'status', up.status, 'created_at', up.created_at,
                                  'candidate_title', up.candidate_title)
        FROM upgrade_proposals up
        WHERE up.status = 'pendiente' AND up.created_at < now() - interval '30 days'
        """,
        nota="Una mejora sobre otro número propone sustituir lo que no es. Las pendientes viejas "
             "solo son deuda de revisión; se informa.",
    ),
    Check(
        "I3", "Portada externa sin copia local y fallos recordados", "S3",
        poblacion="",
        casos="",
        ejecutable=False,
        motivo_no_ejecutable=(
            "Requiere recorrer `covers/externa/` y `covers/v3/fallos/` en el disco de la Pi; "
            "este censo no recorre la biblioteca ni el disco salvo permiso expreso. El recuento "
            "de `series.cover_url` externas sí está en el perfil, pero no dice si hay copia."),
        nota="El hotlinking está prohibido (CLAUDE.md §3.1.4): la app resuelve en cascada, así "
             "que una portada externa sin copia no es un dato falso hoy; solo se informa.",
    ),
    Check(
        "D1b", "El título del parser contradice la serie del número", "S2",
        poblacion="",
        casos="",
        ejecutable=False,
        motivo_no_ejecutable=(
            "Requiere ejecutar `naming.parse_comic_filename` de la versión desplegada sobre "
            "`files.file_name` (sin abrir el archivo). Se hará en la fase de diagnóstico con el "
            "parser fijado al SHA de la Pi, no con el de este checkout."),
        nota="La carpeta declarada ya se mide en D1a. Esta mitad es la del nombre: el parser dice "
             "una serie y la fila está vinculada a otra sin relación protegida.",
    ),
])


#: Etiqueta ESPERADA por comprobación, escrita ANTES de mirar la muestra real.
#: Evita el sesgo de confirmación: el PO solo rellena `etiqueta_po` en el CSV.
#: "no sé" es una respuesta válida y obliga a mirar el caso, no a contar el check.
_HIPOTESIS = {
    "A1a": "defecto",
    "A1b": "legítimo",      # el historial conserva la procedencia de lo borrado
    "B1b": "defecto",
    "B2b": "no sé",         # Comic Vine también indexa álbumes europeos
    "B3b": "no sé",         # una edición española de material USA es legítima
    "B5a": "defecto",
    "B6c": "no sé",         # altas y asociaciones tienen otros caminos
    "B7": "no sé",          # variantes de título
    "B8": "no sé",          # evidencia histórica, no defecto
    "B9": "no sé",          # el id puede ser correcto aunque no conste el registro
    "C1": "no sé",          # proxy del parser, no el parser
    "C2a": "defecto",
    "C2b": "defecto",
    "C2c": "defecto",
    "C3a": "no sé",         # una persona pudo decidir el #1
    "C4b": "no sé",         # «12 B» puede ser un número real
    "D4c": "defecto",
    "D5": "legítimo",       # informativo: la extensión no se corrige
    "D6a": "defecto",
    "D6b": "legítimo",      # 77 % apunta a una convención, no a un defecto
    "E1": "no sé",          # el total puede ser correcto aunque la unidad no conste
    "F4a": "defecto",      # HTML en la sinopsis copiado de la fuente
    "F4b": "no sé",         # espacios, sufijos y mayúsculas
    "G1": "no sé",          # dos ediciones legítimas
    "H1": "no sé",          # origen no registrado, no necesariamente falso
    "H2": "defecto",
}
CHECKS = [replace(c, hipotesis=_HIPOTESIS.get(c.id, c.hipotesis)) for c in CHECKS]


# ── Runner ────────────────────────────────────────────────────────────────────

def _porcentaje(casos: int, poblacion: int) -> str:
    if not poblacion:
        return "—"
    return f"{100.0 * casos / poblacion:.1f} %"


def _filtradas(solo: str | None) -> list[Check]:
    if not solo:
        return list(CHECKS)
    prefijos = [p.strip().upper() for p in solo.split(",") if p.strip()]
    return [c for c in CHECKS if any(c.id.upper().startswith(p) for p in prefijos)]


async def _perfil(conn: Any) -> list[dict]:
    salida: list[dict] = []
    for etiqueta, sql in PERFIL:
        try:
            filas = await conn.fetch(sql)
        except Exception as exc:  # noqa: BLE001
            motivo = _motivo_de_esquema(exc)
            if motivo is None:
                raise
            # La Pi puede ir detrás de `origin/main`: el perfil completo no debe
            # impedir ver el resto; esta tabla se marca como no disponible.
            salida.append({
                "etiqueta": etiqueta, "columnas": ["aviso"],
                "filas": [{"aviso": motivo}],
            })
            continue
        columnas = list(filas[0].keys()) if filas else []
        salida.append({
            "etiqueta": etiqueta,
            "columnas": columnas,
            "filas": [_fila(dict(f)) for f in filas],
        })
    return salida


_FALLOS_DE_ESQUEMA = frozenset({
    "UndefinedColumnError", "UndefinedTableError", "UndefinedFunctionError",
    "DatatypeMismatchError",
})


def _motivo_de_esquema(exc: BaseException) -> str | None:
    """Si el fallo es «esta BD no tiene la columna/tabla/función», no es un defecto
    del catálogo: la comprobación queda NOT RUN con el motivo (la Pi puede ir
    detrás de `origin/main`)."""
    if type(exc).__name__ in _FALLOS_DE_ESQUEMA:
        return (f"la BD no tiene el objeto que la comprobación necesita "
                f"({type(exc).__name__}); probablemente la versión desplegada es anterior")
    return None


async def _ejecutar(conn: Any, check: Check) -> dict:
    """Ejecuta una comprobación. `casos` debe devolver caso_id + detalle."""
    if not check.ejecutable:
        return {
            "id": check.id, "titulo": check.titulo, "severidad": check.severidad,
            "poblacion": None, "casos": None, "porcentaje": None,
            "estado": "NOT RUN", "motivo": check.motivo_no_ejecutable,
            "nota": check.nota, "muestra": [], "truncado": False,
        }
    try:
        poblacion = int(await conn.fetchval(check.poblacion) or 0)
        sql = f"SELECT * FROM ({check.casos}) q ORDER BY caso_id"
        filas = await conn.fetch(f"{sql} LIMIT {check.tope + 1}")
    except Exception as exc:  # noqa: BLE001
        motivo = _motivo_de_esquema(exc)
        if motivo is None:
            raise
        return {
            "id": check.id, "titulo": check.titulo, "severidad": check.severidad,
            "poblacion": None, "casos": None, "instancias": None, "porcentaje": None,
            "estado": "NOT RUN", "motivo": motivo, "nota": check.nota,
            "muestra": [], "truncado": False,
        }
    truncado = len(filas) > check.tope
    if truncado:
        casos = int(await conn.fetchval(
            f"SELECT count(DISTINCT caso_id) FROM ({check.casos}) q") or 0)
        filas = filas[: check.tope]
    else:
        casos = len({f["caso_id"] for f in filas})
    instancias = len(filas)
    estado, motivo = "OK", ""
    if poblacion == 0:
        # No es un PASS: no hay filas que medir. Se distingue de «0 casos» a
        # propósito, para que un catálogo sin anilist_id no parezca sano.
        estado = "SIN POBLACION"
        motivo = ("la población es 0: no hay filas que medir en esta instalación; "
                  "no es un PASS")
    return {
        "id": check.id, "titulo": check.titulo, "severidad": check.severidad,
        "poblacion": poblacion, "casos": casos, "instancias": instancias,
        "porcentaje": (100.0 * casos / poblacion) if poblacion else None,
        "estado": estado, "motivo": motivo, "nota": check.nota,
        "muestra": [_fila(dict(f)) for f in filas],
        "truncado": truncado,
    }


async def _muestra_aleatoria(conn: Any, check: Check, n: int, semilla: int) -> list[dict]:
    sql = (f"SELECT * FROM ({check.casos}) q "
           f"ORDER BY md5(caso_id || ':' || $1) LIMIT {int(n)}")
    return [_fila(dict(f)) for f in await conn.fetch(sql, str(semilla))]


def _render_detalle(detalle: Any, local: bool) -> Any:
    return _fila(detalle) if local else _seudonimizar(_fila(detalle))


def _imprimir_perfil(perfil: list[dict]) -> None:
    for bloque in perfil:
        print(f"\n## {bloque['etiqueta']}")
        if not bloque["filas"]:
            print("  (sin filas)")
            continue
        print("  " + " | ".join(bloque["columnas"]))
        for fila in bloque["filas"]:
            print("  " + " | ".join(str(fila.get(c)) for c in bloque["columnas"]))


def _imprimir_check(resultado: dict, limite: int, local: bool) -> None:
    if resultado["estado"] in ("NOT RUN", "SIN POBLACION"):
        print(f"\n[{resultado['id']}] {resultado['titulo']} — {resultado['severidad']} — "
              f"{resultado['estado']}")
        print(f"  Motivo: {resultado['motivo']}")
        return
    extra = " (TRUNCADO)" if resultado["truncado"] else ""
    print(f"\n[{resultado['id']}] {resultado['titulo']} — {resultado['severidad']}{extra}")
    extra_casos = ("" if resultado.get("instancias") in (None, resultado["casos"])
                   else f" · Instancias: {resultado['instancias']}")
    print(f"  Población: {resultado['poblacion']} · Casos: {resultado['casos']} "
          f"({_porcentaje(resultado['casos'], resultado['poblacion'])}){extra_casos}")
    if resultado["nota"]:
        print(f"  Nota: {resultado['nota']}")
    for fila in resultado["muestra"][:limite]:
        detalle = _render_detalle(fila.get("detalle"), local)
        print(f"  · {fila.get('caso_id')}  {_json_estable(detalle)}")


def _huella(resultados: list[dict]) -> str:
    datos = [
        {"id": r["id"], "poblacion": r["poblacion"], "casos": r["casos"],
         "instancias": r.get("instancias"), "muestra": r["muestra"]}
        for r in resultados
    ]
    return hashlib.sha256(_json_estable(datos).encode("utf-8")).hexdigest()


def _escribir_csv(ruta: str, resultados: list[dict], local: bool, limite: int) -> None:
    import csv
    import contextlib

    destino = contextlib.nullcontext(sys.stdout) if ruta == "-" else open(
        ruta, "w", encoding="utf-8", newline="")
    with destino as fh:
        escritor = csv.writer(fh, lineterminator="\n")
        escritor.writerow(["comprobacion", "caso_id", "etiqueta_esperada", "etiqueta_po",
                           "detalle_json"])
        for r in resultados:
            if r["estado"] != "OK" or not r["casos"]:
                continue
            check = next((c for c in CHECKS if c.id == r["id"]), None)
            esperada = check.hipotesis if check else "defecto"
            for fila in r["muestra"][:limite]:
                detalle = _render_detalle(fila.get("detalle"), local)
                escritor.writerow([r["id"], fila.get("caso_id"), esperada, "",
                                   _json_estable(detalle)])


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Catálogo de comprobaciones de calidad del dato (solo lectura).")
    p.add_argument("--local", action="store_true",
                   help="Muestra títulos y rutas ORIGINALES (SOLO uso local; no compartir).")
    p.add_argument("--json", action="store_true", help="Salida JSON estable para comparar.")
    p.add_argument("--perfil", action="store_true", help="Solo el perfil del dato (fase 1).")
    p.add_argument("--solo", default=None,
                   help="Filtra por prefijo de id, separado por comas (p. ej. A,B1,C).")
    p.add_argument("--limite", type=int, default=5,
                   help="Ejemplos por comprobación en pantalla (por defecto 5).")
    p.add_argument("--muestreo", type=int, default=0,
                   help="Tamaño de la muestra aleatoria para etiquetar (0 = no muestrear).")
    p.add_argument("--semilla", type=int, default=42,
                   help="Semilla fija del muestreo (por defecto 42).")
    p.add_argument("--csv", default=None,
                   help="Escribe la muestra para etiquetar en un CSV local (no versionar).")
    return p.parse_args()


def _url_de_entorno() -> str | None:
    """URL de la BD: `DATABASE_URL`/`TEST_DATABASE_URL` o, dentro del contenedor de
    la app, la misma que construye Compose desde `ZASCARR_DB_PASSWORD`.

    El fallback importa el código desplegado (la versión de la Pi) para no repetir
    aquí el host/puerto/usuario de `docker-compose.yml`. No imprime credenciales.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    password = os.environ.get("ZASCARR_DB_PASSWORD")
    if not password:
        return None
    from zascarr.utils.credenciales import url_bd_compose

    return url_bd_compose(password).render_as_string(hide_password=False)


async def _main(args: argparse.Namespace) -> int:
    import asyncpg

    url = _url_de_entorno()
    if not url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL), y no hay ZASCARR_DB_PASSWORD "
              "para construirla como en Compose.", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        # JSONB como dict: si vuelve como texto, la seudonimización no entra en
        # `detalle` y una salida «compartible» llevaría títulos y rutas reales.
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        # Blindaje de solo lectura a nivel de BD: cualquier escritura fallaría.
        await conn.execute("BEGIN TRANSACTION READ ONLY")

        perfil = await _perfil(conn) if (args.perfil or args.json) else []
        seleccion = [] if args.perfil else _filtradas(args.solo)
        resultados: list[dict] = []
        muestras: dict[str, list[dict]] = {}
        for check in seleccion:
            resultados.append(await _ejecutar(conn, check))
            if args.muestreo and check.ejecutable:
                filas = await _muestra_aleatoria(conn, check, args.muestreo, args.semilla)
                muestras[check.id] = filas
                if args.csv:
                    resultados[-1]["muestra"] = filas
    finally:
        await conn.execute("ROLLBACK")
        await conn.close()

    if args.csv:
        if not args.local:
            print("AVISO: --csv sin --local escribe valores seudonimizados; el PO no podrá "
                  "etiquetar. Usa --local para el CSV local.", file=sys.stderr)
        _escribir_csv(args.csv, resultados, args.local, args.muestreo or args.limite)
        if args.csv == "-":
            # Solo el CSV en stdout: no se mezcla con el informe humano.
            return 0

    if args.json:
        salida = {
            "schema": 1,
            "generado": datetime.now(UTC).isoformat(timespec="seconds"),
            "filtro": args.solo,
            "semilla": args.semilla,
            "perfil": perfil,
            "checks": [
                {**r, "muestra": (_render_detalle(r["muestra"], args.local)
                                  if args.local else
                                  [{"caso_id": m.get("caso_id"),
                                    "detalle": _seudonimizar(m.get("detalle"))}
                                   for m in r["muestra"]])}
                for r in resultados
            ],
        }
        salida["huella"] = _huella(resultados)
        print(json.dumps(salida, ensure_ascii=False, sort_keys=True, indent=2, default=str))
        return 0

    print("=" * 78)
    print("Censo de calidad del dato — solo lectura")
    print("=" * 78)
    if perfil:
        _imprimir_perfil(perfil)
    for r in resultados:
        _imprimir_check(r, args.limite, args.local)
    if seleccion:
        print("\n" + "=" * 78)
        print(f"{len(resultados)} comprobaciones · huella {_huella(resultados)}")
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(_main(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
