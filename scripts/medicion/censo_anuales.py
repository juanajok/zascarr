#!/usr/bin/env python3
"""censo_anuales.py — ¿cuántos anuales hay de verdad antes de tocar el modelo?

Solo lectura: toda la conexión corre dentro de `BEGIN TRANSACTION READ ONLY`,
así que Postgres rechaza cualquier escritura aunque el script se equivocara.
No abre archivos ni toca la biblioteca: lee `series`, `issues` y `files`.

Responde a lo que la fase 0 no puede decidir sola:
  1. Series cuyo título parece una línea anual («Batman Annual»).
  2. Issues cuyo `issue_number` parece anual/especial («Annual 1», «Anual 2»).
  3. Archivos con «Annual»/«Anual» en el nombre: cuántos están sin Issue y
     cuántos están enlazados a una serie que NO es anual (el caso que la fase 0
     deja de crear, pero que puede existir ya en la biblioteca).
  4. Muestra pequeña para revisar a mano. Por defecto, títulos y nombres
     **seudonimizados** (SHA-256 truncado); con `--local`, originales (no
     compartir esa salida).

Uso:

    DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \\
        python3 scripts/medicion/censo_anuales.py [--local]

También acepta `TEST_DATABASE_URL`. No escribe nada: solo lee.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys

import asyncpg

# Patrones de nombre. No se usa `unaccent`: «Annual» y «Anual» no llevan
# tilde y el catálogo guarda el título tal cual; si un título llevara una
# variante con tilde, la revisión manual de la muestra lo detecta.
_ANUAL_SQL = "(title ILIKE '%annual%' OR title ILIKE '%anual%')"
_ANUAL_SERIE_SQL = "(s.title ILIKE '%annual%' OR s.title ILIKE '%anual%')"
_ARCHIVO_ANUAL_SQL = "(file_name ILIKE '%annual%' OR file_name ILIKE '%anual%')"
_COLUMNAS_SECRETAS = {"titulo", "nombre", "file_name"}


def _url_asyncpg(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _seudonimo(valor: object, largo: int = 8) -> str:
    if valor is None or valor == "":
        return "(vacío)"
    return hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:largo]


async def _tabla(conn: asyncpg.Connection, etiqueta: str, sql: str) -> None:
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
    conn: asyncpg.Connection, etiqueta: str, sql: str, limite: int, local: bool
) -> None:
    filas = await conn.fetch(sql)
    modo = "LOCAL (originales; no compartir)" if local else "compartible (seudonimizado)"
    print(f"\n{etiqueta} (hasta {limite}) [{modo}]")
    if not filas:
        print("  (sin filas)")
        return
    columnas = list(filas[0].keys())
    print("  " + " | ".join(columnas))
    for fila in filas:
        valores = []
        for columna in columnas:
            valor = fila[columna]
            if columna in _COLUMNAS_SECRETAS and not local:
                valores.append(_seudonimo(valor))
            else:
                valores.append(str(valor))
        print("  " + " | ".join(valores))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Censo de anuales de la biblioteca (solo lectura)."
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Muestra títulos/nombres ORIGINALES (solo revisión local; no compartir).",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        await conn.execute("BEGIN TRANSACTION READ ONLY")

        print("=" * 72)
        print("Censo de anuales — solo lectura")
        print("=" * 72)

        await _tabla(
            conn,
            "Series con título anual",
            f"SELECT count(*) AS series_anuales FROM series WHERE {_ANUAL_SQL}",
        )
        await _tabla(
            conn,
            "Issues con número anual/especial",
            "SELECT coalesce(i.format::text, '(sin formato)') AS formato, count(*) AS issues "
            "FROM issues i "
            "WHERE i.issue_number ILIKE '%annual%' OR i.issue_number ILIKE '%anual%' "
            "   OR i.issue_number ILIKE '%especial%' "
            "GROUP BY 1 ORDER BY 2 DESC",
        )
        await _tabla(
            conn,
            "Archivos con Annual/Anual en el nombre",
            f"SELECT count(*) AS archivos, "
            f"count(*) FILTER (WHERE issue_id IS NULL) AS sin_issue, "
            f"count(*) FILTER (WHERE issue_id IS NOT NULL) AS con_issue "
            f"FROM files WHERE {_ARCHIVO_ANUAL_SQL}",
        )
        await _tabla(
            conn,
            "Archivos anuales enlazados a una serie NO anual (posible falso vínculo)",
            f"SELECT count(*) AS posibles_falsos_vinculos "
            f"FROM files f JOIN issues i ON i.id = f.issue_id "
            f"JOIN series s ON s.id = i.series_id "
            f"WHERE {_ARCHIVO_ANUAL_SQL} "
            f"  AND NOT (s.title ILIKE '%annual%' OR s.title ILIKE '%anual%')",
        )
        await _tabla(
            conn,
            "Archivos anuales enlazados a una serie anual",
            f"SELECT count(*) AS en_serie_anual "
            f"FROM files f JOIN issues i ON i.id = f.issue_id "
            f"JOIN series s ON s.id = i.series_id "
            f"WHERE {_ARCHIVO_ANUAL_SQL} "
            f"  AND (s.title ILIKE '%annual%' OR s.title ILIKE '%anual%')",
        )
        await _tabla(
            conn,
            "Series anuales con más de un Issue (varias líneas o ruido)",
            f"SELECT count(*) AS series_con_varios FROM ("
            f"  SELECT s.id FROM series s JOIN issues i ON i.series_id = s.id "
            f"  WHERE {_ANUAL_SERIE_SQL} GROUP BY s.id HAVING count(*) > 1"
            f") t",
        )

        await _muestra(
            conn,
            "Muestra: series con título anual",
            f"SELECT title AS titulo, start_year, "
            f"       coalesce(metadata_source, '(sin fuente)') AS fuente, total_issues "
            f"FROM series WHERE {_ANUAL_SQL} ORDER BY title LIMIT 20",
            20,
            args.local,
        )
        await _muestra(
            conn,
            "Muestra: archivos anuales (serie, número y nombre)",
            f"SELECT s.title AS titulo, i.issue_number, f.file_name AS nombre, "
            f"       coalesce(i.format::text, '(sin formato)') AS formato, "
            f"       (f.issue_id IS NULL) AS sin_issue "
            f"FROM files f "
            f"LEFT JOIN issues i ON i.id = f.issue_id "
            f"LEFT JOIN series s ON s.id = i.series_id "
            f"WHERE {_ARCHIVO_ANUAL_SQL} ORDER BY f.file_name LIMIT 20",
            20,
            args.local,
        )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(_args())))
