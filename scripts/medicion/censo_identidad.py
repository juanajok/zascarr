#!/usr/bin/env python3
"""censo_identidad.py — ¿qué hay de verdad en el catálogo para decidir B22?

Solo lectura: no emite INSERT/UPDATE/DELETE; toda la conexión corre dentro de
una transacción `READ ONLY`, de modo que Postgres rechaza cualquier escritura
aunque el script se equivocara. No vuelca el catálogo: imprime agregados y una
muestra pequeña con títulos/rutas **seudonimizados** (hash SHA-256 truncado).

Dos salidas:
  - Por defecto (COMPARTIBLE): agregados + seudónimos. Un hash truncado no es
    anonimización fuerte (se puede comprobar contra un diccionario de títulos
    conocidos), así que se llama seudonimización, no anonimización.
  - Con `--local` (SOLO LOCAL, NO compartir): la misma muestra pero con los
    nombres/rutas originales, para que quien ejecuta pueda etiquetar esos pocos
    casos. No pegar rutas, credenciales ni la URL de conexión en el chat.

Responde, en orden:
  1. Recuentos de Issue por `format`, tradición y fuente de metadatos.
  2. Grupos con mismo `series_id + issue_number` (número no NULL) y distinto
     `volume`/`format`, separando «colisión efectiva» (mismo número y volume
     NULL repetido — duplicados ambiguos que el UNIQUE no detiene) de «mismo
     número, otra edición posible» (volúmenes distintos). Los issues SIN número
     (`issue_number IS NULL`) se cuentan aparte: «dos obras sin número» no
     demuestra una colisión del mismo número.
  3. `Issue.volume IS NULL` y `File.covered_issue_ids` no vacíos.
  4. Tomos/ómnibus con archivo disponible, y cuántos tienen *evidencia
     almacenada* (aquí `covered_issue_ids` no vacío). Cero en esa columna solo
     demuestra «no hay pistas en ESTA columna»; la evidencia fuera de la BD
     (ComicInfo, catálogos, revisión manual) se señala por separado, no se mide.
  5. Muestra estratificada y seudonimizada de Omnigold/integral, tomo/volumen,
     manga por tomos, packs con `covered_issue_ids` y archivos SIN Issue
     (candidatos a pack, sin inventarles un Issue).

Uso:

    DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \\
        python3 scripts/medicion/censo_identidad.py [--local]

La variable TEST_DATABASE_URL también vale. No escribe nada: solo lee.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import sys

import asyncpg

# formatos que representan una recopilación (tomo/ómnibus/álbum…), frente a la
# grapa suelta `single_issue`. «digital» se excluye por ambigüedad de unidad.
FORMATOS_RECOPILACION = (
    "trade_paperback",
    "omnibus",
    "hardcover",
    "graphic_novel",
    "album",
    "manga_tankobon",
)
# Lista literal para incrustar en SQL (valores fijos y seguros, no datos de usuario).
_RECOP_SQL = ", ".join(f"'{f}'" for f in FORMATOS_RECOPILACION)

# Patrón heurístico de "rango en el nombre" (p. ej. "001-010", "1 – 5", "12 a 24").
# Solo sirve para marcar CANDIDATOS a pack, nunca como cobertura cierta.
_RANGO = re.compile(r"\d+\s*[^0-9a-zA-Z]{1,6}\s*\d+")

# Columnas que identifican a una obra/archivo: se seudonimizan en modo
# compartible y se muestran originales solo con --local.
_COLUMNAS_SECRETAS = {"titulo", "ruta", "nombre", "file_name", "file_path"}


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _seudonimo(valor: object, largo: int = 8) -> str:
    """Seudonimiza un título/ruta. SHA-256 truncado = seudónimo, NO anonimato."""
    if valor is None or valor == "":
        return "(vacío)"
    return hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:largo]


async def _print_tabla(conn: asyncpg.Connection, etiqueta: str, sql: str) -> None:
    filas = await conn.fetch(sql)
    print(f"\n{etiqueta}")
    if not filas:
        print("  (sin filas)")
        return
    columnas = list(filas[0].keys())
    print("  " + " | ".join(columnas))
    for fila in filas:
        print("  " + " | ".join(str(fila[c]) for c in columnas))


async def _muestra(
    conn: asyncpg.Connection,
    etiqueta: str,
    sql: str,
    limite: int,
    local: bool,
) -> None:
    """Muestra estratificada. Compartible: seudónimos; --local: originales."""
    filas = await conn.fetch(sql)
    modo = "LOCAL (nombres originales — NO compartir)" if local else "compartible (seudonimizado)"
    print(f"\n{etiqueta} (hasta {limite}) [{modo}]")
    if not filas:
        print("  (sin filas)")
        return
    columnas = list(filas[0].keys())
    cabeceras = [
        (c + ("_original" if local else "_seud") if c in _COLUMNAS_SECRETAS else c)
        for c in columnas
    ]
    print("  " + " | ".join(cabeceras))
    for fila in filas:
        vals = []
        for c in columnas:
            if c in _COLUMNAS_SECRETAS:
                vals.append(str(fila[c]) if local else _seudonimo(fila[c]))
            else:
                vals.append(str(fila[c]))
        print("  " + " | ".join(vals))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Censo de identidad editorial (B22), solo lectura.")
    p.add_argument(
        "--local",
        action="store_true",
        help="Muestra nombres/rutas ORIGINALES en las muestras (SOLO revisión local; no compartir esta salida).",
    )
    return p.parse_args()


async def main(args: argparse.Namespace) -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        # Blindaje de solo lectura a nivel de BD: cualquier escritura fallaría.
        await conn.execute("BEGIN TRANSACTION READ ONLY")

        print("=" * 72)
        print("Censo de identidad editorial (B22) — solo lectura")
        print("=" * 72)

        # ── 1. Recuentos por formato / tradición / fuente ────────────────────
        await _print_tabla(
            conn,
            "Issues por format",
            "SELECT coalesce(format::text, '(sin formato)') AS format, count(*) AS issues "
            "FROM issues GROUP BY 1 ORDER BY 2 DESC",
        )
        await _print_tabla(
            conn,
            "Issues por tradición (de la serie)",
            "SELECT coalesce(s.tradition::text, '(sin tradición)') AS tradicion, count(*) AS issues "
            "FROM issues i LEFT JOIN series s ON s.id = i.series_id "
            "GROUP BY 1 ORDER BY 2 DESC",
        )
        await _print_tabla(
            conn,
            "Issues por fuente de metadatos",
            "SELECT coalesce(i.metadata_source, '(sin fuente)') AS fuente, count(*) AS issues "
            "FROM issues i GROUP BY 1 ORDER BY 2 DESC",
        )
        await _print_tabla(
            conn,
            "Series por tradición (contexto)",
            "SELECT coalesce(tradition::text, '(sin tradición)') AS tradicion, count(*) AS series "
            "FROM series GROUP BY 1 ORDER BY 2 DESC",
        )

        # ── 2. Grupos (series_id, issue_number NO NULL) con más de un issue ──
        await _print_tabla(
            conn,
            "Issues SIN número (issue_number IS NULL) — contados aparte",
            "SELECT count(*) AS issues_sin_numero FROM issues WHERE issue_number IS NULL",
        )
        await _print_tabla(
            conn,
            "Series con MÁS de un issue sin número (no es colisión de un mismo número)",
            "SELECT count(*) AS series_con_multiples_sin_numero "
            "FROM (SELECT series_id FROM issues WHERE issue_number IS NULL "
            "      GROUP BY 1 HAVING count(*) > 1) t",
        )
        await _print_tabla(
            conn,
            "Grupos (serie + número) con MÁS de un issue (número no NULL)",
            "SELECT count(*) AS grupos_con_multiples "
            "FROM (SELECT series_id, issue_number FROM issues "
            "      WHERE issue_number IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1) t",
        )
        await _print_tabla(
            conn,
            "Colisión efectiva: mismo serie+número con volume NULL repetido (duplicados ambiguos)",
            "SELECT count(*) AS colisiones_null "
            "FROM (SELECT series_id, issue_number FROM issues "
            "      WHERE volume IS NULL AND issue_number IS NOT NULL "
            "      GROUP BY 1, 2 HAVING count(*) > 1) t",
        )
        await _print_tabla(
            conn,
            "Mismo serie+número con volúmenes DISTINTOS (otra edición posible)",
            "SELECT count(*) AS otras_ediciones_posibles "
            "FROM (SELECT series_id, issue_number FROM issues "
            "      WHERE volume IS NOT NULL AND issue_number IS NOT NULL "
            "      GROUP BY 1, 2 HAVING count(*) > 1 AND count(DISTINCT volume) > 1) t",
        )
        await _print_tabla(
            conn,
            "Recopilaciones que comparten número con una grapa (distinto format, mismo volumen 1 — si existen)",
            "SELECT count(*) AS casos "
            "FROM issues a JOIN issues b ON a.series_id = b.series_id "
            "  AND a.issue_number = b.issue_number AND a.volume = b.volume "
            "WHERE a.format = 'single_issue' AND b.format <> 'single_issue'",
        )

        await _muestra(
            conn,
            "Muestra: colisiones efectivas (volume NULL repetido)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format "
            "FROM issues i JOIN series s ON s.id = i.series_id "
            "WHERE i.volume IS NULL AND i.issue_number IS NOT NULL AND (i.series_id, i.issue_number) IN ("
            "  SELECT series_id, issue_number FROM issues "
            "  WHERE volume IS NULL AND issue_number IS NOT NULL "
            "  GROUP BY 1, 2 HAVING count(*) > 1) "
            "ORDER BY i.series_id, i.issue_number LIMIT 20",
            20,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: misma serie+número, volúmenes distintos (otra edición posible)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format "
            "FROM issues i JOIN series s ON s.id = i.series_id "
            "WHERE i.volume IS NOT NULL AND i.issue_number IS NOT NULL AND (i.series_id, i.issue_number) IN ("
            "  SELECT series_id, issue_number FROM issues "
            "  WHERE volume IS NOT NULL AND issue_number IS NOT NULL "
            "  GROUP BY 1, 2 HAVING count(*) > 1 AND count(DISTINCT volume) > 1) "
            "ORDER BY i.series_id, i.issue_number, i.volume LIMIT 20",
            20,
            args.local,
        )

        # ── 3. volume NULL y covered_issue_ids no vacíos ────────────────────
        await _print_tabla(
            conn,
            "Issues con volume IS NULL",
            "SELECT count(*) AS issues_volume_null FROM issues WHERE volume IS NULL",
        )
        await _print_tabla(
            conn,
            "Archivos con covered_issue_ids NO vacío (evidencia ALMACENADA en esta columna)",
            "SELECT count(*) AS files_con_covered FROM files "
            "WHERE cardinality(covered_issue_ids) > 0",
        )
        await _print_tabla(
            conn,
            "Archivos con ComicInfo (metadata_source='comicinfo_xml') — evidencia EXTERNA posible, no medida aquí",
            "SELECT count(*) AS files_con_comicinfo FROM files "
            "WHERE metadata_source = 'comicinfo_xml'",
        )

        # ── 4. Recopilaciones con archivo disponible y evidencia ─────────────
        await _print_tabla(
            conn,
            "Recopilaciones (tomo/ómnibus/álbum) por formato: con archivo y con evidencia almacenada",
            "SELECT i.format, count(*) AS recopilaciones, "
            "  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM files f "
            "      WHERE f.issue_id = i.id AND f.is_missing = false)) AS con_archivo, "
            "  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM files f "
            "      WHERE f.issue_id = i.id AND cardinality(f.covered_issue_ids) > 0)) "
            "      AS con_evidencia_covered "
            "FROM issues i "
            f"WHERE i.format IN ({_RECOP_SQL}) "
            "GROUP BY 1 ORDER BY 2 DESC",
        )
        print("  (NOTA: 'con_evidencia_covered' = covered_issue_ids no vacío. No es")
        print("   cobertura confirmada: es una cota superior, no una prueba de que el")
        print("   tomo reproduzca esas grapas.)")

        # ── 5. Muestra estratificada ────────────────────────────────────────
        await _muestra(
            conn,
            "Muestra: Omnigold/Integral (edicion omnigold|integral o format omnibus)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format, "
            "       f.metadata->>'edicion' AS edicion, f.file_path AS ruta "
            "FROM files f JOIN issues i ON i.id = f.issue_id "
            "JOIN series s ON s.id = i.series_id "
            "WHERE f.metadata->>'edicion' IN ('omnigold','integral') "
            "   OR i.format = 'omnibus' "
            "ORDER BY f.id LIMIT 5",
            5,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: Tomo/Volumen (edicion tomo|volumen o format trade_paperback)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format, "
            "       f.metadata->>'edicion' AS edicion, f.file_path AS ruta "
            "FROM files f JOIN issues i ON i.id = f.issue_id "
            "JOIN series s ON s.id = i.series_id "
            "WHERE f.metadata->>'edicion' IN ('tomo','volumen') "
            "   OR i.format = 'trade_paperback' "
            "ORDER BY f.id LIMIT 5",
            5,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: manga por tomos (tradición manga/manhwa/manhua con recopilación)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format, "
            "       f.metadata->>'edicion' AS edicion, f.file_path AS ruta "
            "FROM files f JOIN issues i ON i.id = f.issue_id "
            "JOIN series s ON s.id = i.series_id "
            "WHERE s.tradition IN ('manga','manhwa','manhua') "
            f"  AND i.format IN ({_RECOP_SQL}) "
            "ORDER BY f.id LIMIT 5",
            5,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: packs con covered_issue_ids no vacío (si existen)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format, "
            "       f.file_path AS ruta, cardinality(f.covered_issue_ids) AS cubiertos "
            "FROM files f JOIN issues i ON i.id = f.issue_id "
            "JOIN series s ON s.id = i.series_id "
            "WHERE cardinality(f.covered_issue_ids) > 0 "
            "ORDER BY f.id LIMIT 10",
            10,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: CANDIDATOS a pack sin Issue asignado (issue_id IS NULL)",
            "SELECT f.file_name AS nombre, f.file_format, "
            "       coalesce(f.metadata_source, '(sin fuente)') AS fuente, "
            "       f.file_path AS ruta "
            "FROM files f WHERE f.issue_id IS NULL ORDER BY f.id LIMIT 20",
            20,
            args.local,
        )
        # Heurística de rango sobre la muestra de candidatos (solo informativa)
        candidatos = await conn.fetch(
            "SELECT file_name FROM files WHERE issue_id IS NULL ORDER BY id LIMIT 20"
        )
        con_rango = sum(1 for r in candidatos if _RANGO.search(r["file_name"] or ""))
        print(f"  (de la muestra de candidatos, {con_rango} nombres parecen rango — heurístico,")
        print("   no es cobertura cierta)")

        # ── Veredicto ────────────────────────────────────────────────────────
        total = await conn.fetchval("SELECT count(*) FROM issues")
        recop = await conn.fetchval(
            f"SELECT count(*) FROM issues WHERE format IN ({_RECOP_SQL})"
        )
        con_evidencia = await conn.fetchval(
            "SELECT count(*) FROM files WHERE cardinality(covered_issue_ids) > 0"
        )
        con_comicinfo = await conn.fetchval(
            "SELECT count(*) FROM files WHERE metadata_source = 'comicinfo_xml'"
        )
        sin_issue = await conn.fetchval(
            "SELECT count(*) FROM files WHERE issue_id IS NULL"
        )
        print("\n" + "=" * 72)
        print(f"VEREDICTO: {total} issues, {recop} recopilaciones.")
        print(f"  Evidencia ALMACENADA en BD: covered_issue_ids no vacío = {con_evidencia}")
        print(f"  Evidencia EXTERNA en archivo (ComicInfo) = {con_comicinfo}")
        print(f"  Archivos sin Issue (candidatos a pack) = {sin_issue}")
        print("  → covered_issue_ids=0 solo demuestra «no hay pistas en ESTA columna».")
        print("    Puede haber cobertura verificable en ComicInfo, catálogos o revisión")
        print("    manual, que este script NO mide. La decisión de posponer exige ambas.")
        print("=" * 72)
    finally:
        await conn.execute("ROLLBACK")
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(_parse_args())))
