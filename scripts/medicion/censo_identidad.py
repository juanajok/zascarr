#!/usr/bin/env python3
"""censo_identidad.py — ¿qué hay de verdad en el catálogo para decidir B22?

Solo lectura: no emite INSERT/UPDATE/DELETE; toda la conexión corre dentro de
una transacción `READ ONLY`, de modo que Postgres rechaza cualquier escritura
aunque el script se equivocara. No vuelca el catálogo: imprime agregados y una
muestra pequeña con títulos/rutas **anonimizados** (hash SHA-256 truncado).

Responde, en orden:
  1. Recuentos de Issue por `format`, tradición y fuente de metadatos.
  2. Grupos con mismo `series_id + issue_number` y distinto `volume`/`format`,
     separando «colisión efectiva» (mismo número y volumen NULL repetido —
     duplicados ambiguos que el UNIQUE no detiene) de «misma número, otra
     edición posible» (volúmenes distintos).
  3. `Issue.volume IS NULL` y `File.covered_issue_ids` no vacíos.
  4. Tomos/ómnibus con archivo disponible, y cuántos tienen *evidencia* de
     cobertura (aquí `covered_issue_ids` no vacío — que NO es cobertura
     confirmada; es solo la pista existente, así que el número es una cota
     superior, no una prueba).
  5. Muestra estratificada y anonimizada de Omnigold/integral, tomo/volumen,
     manga por tomos y packs.

Uso:

    DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \\
        python3 scripts/medicion/censo_identidad.py

La variable TEST_DATABASE_URL también vale. No escribe nada: solo lee.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
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


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _anon(valor: object, largo: int = 8) -> str:
    """Anonimiza un título/ruta antes de imprimirlo. Sin el texto original."""
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


async def _muestra_anonimizada(
    conn: asyncpg.Connection,
    etiqueta: str,
    sql: str,
    limite: int,
) -> None:
    """Muestra estratificada con títulos/rutas anonimizados (solo hash)."""
    filas = await conn.fetch(sql)
    print(f"\n{etiqueta} (hasta {limite}, títulos/rutas anonimizados)")
    if not filas:
        print("  (sin filas)")
        return
    # columnas que sí se pueden enseñar tal cual (no identifican a nadie)
    visibles = ("format", "edicion", "issue_number", "volume", "fuente")
    print("  " + " | ".join(list(visibles) + ["titulo_anon", "ruta_anon"]))
    for fila in filas:
        vals = [str(fila.get(c)) if c in fila else "-" for c in visibles]
        titulo = _anon(fila.get("titulo")) if "titulo" in fila else "-"
        ruta = _anon(fila.get("ruta")) if "ruta" in fila else "-"
        print("  " + " | ".join(vals + [titulo, ruta]))


async def main() -> int:
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

        # ── 2. Grupos (series_id, issue_number) con más de un issue ──────────
        await _print_tabla(
            conn,
            "Grupos (serie + número) con MÁS de un issue",
            "SELECT count(*) AS grupos_con_multiples "
            "FROM (SELECT series_id, issue_number FROM issues "
            "      GROUP BY 1, 2 HAVING count(*) > 1) t",
        )
        await _print_tabla(
            conn,
            "Colisión efectiva: mismo serie+número con volume NULL repetido (duplicados ambiguos)",
            "SELECT count(*) AS colisiones_null "
            "FROM (SELECT series_id, issue_number FROM issues WHERE volume IS NULL "
            "      GROUP BY 1, 2 HAVING count(*) > 1) t",
        )
        await _print_tabla(
            conn,
            "Mismo serie+número con volúmenes DISTINTOS (otra edición posible)",
            "SELECT count(*) AS otras_ediciones_posibles "
            "FROM (SELECT series_id, issue_number FROM issues WHERE volume IS NOT NULL "
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

        await _muestra_anonimizada(
            conn,
            "Muestra: colisiones efectivas (volume NULL repetido)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format "
            "FROM issues i JOIN series s ON s.id = i.series_id "
            "WHERE i.volume IS NULL AND (i.series_id, i.issue_number) IN ("
            "  SELECT series_id, issue_number FROM issues WHERE volume IS NULL "
            "  GROUP BY 1, 2 HAVING count(*) > 1) "
            "ORDER BY i.series_id, i.issue_number LIMIT 20",
            20,
        )
        await _muestra_anonimizada(
            conn,
            "Muestra: misma serie+número, volúmenes distintos (otra edición posible)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format "
            "FROM issues i JOIN series s ON s.id = i.series_id "
            "WHERE i.volume IS NOT NULL AND (i.series_id, i.issue_number) IN ("
            "  SELECT series_id, issue_number FROM issues WHERE volume IS NOT NULL "
            "  GROUP BY 1, 2 HAVING count(*) > 1 AND count(DISTINCT volume) > 1) "
            "ORDER BY i.series_id, i.issue_number, i.volume LIMIT 20",
            20,
        )

        # ── 3. volume NULL y covered_issue_ids no vacíos ────────────────────
        await _print_tabla(
            conn,
            "Issues con volume IS NULL",
            "SELECT count(*) AS issues_volume_null FROM issues WHERE volume IS NULL",
        )
        await _print_tabla(
            conn,
            "Archivos con covered_issue_ids NO vacío (pista, no cobertura confirmada)",
            "SELECT count(*) AS files_con_covered FROM files "
            "WHERE cardinality(covered_issue_ids) > 0",
        )

        # ── 4. Recopilaciones con archivo disponible y evidencia ─────────────
        await _print_tabla(
            conn,
            "Recopilaciones (tomo/ómnibus/álbum) por formato: con archivo y con evidencia",
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
        await _muestra_anonimizada(
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
        )
        await _muestra_anonimizada(
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
        )
        await _muestra_anonimizada(
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
        )
        await _muestra_anonimizada(
            conn,
            "Muestra: packs (covered_issue_ids no vacío, si existen)",
            "SELECT s.title AS titulo, i.issue_number, i.volume, i.format, "
            "       f.file_path AS ruta, cardinality(f.covered_issue_ids) AS cubiertos "
            "FROM files f JOIN issues i ON i.id = f.issue_id "
            "JOIN series s ON s.id = i.series_id "
            "WHERE cardinality(f.covered_issue_ids) > 0 "
            "ORDER BY f.id LIMIT 10",
            10,
        )

        # ── Veredicto ────────────────────────────────────────────────────────
        total = await conn.fetchval("SELECT count(*) FROM issues")
        recop = await conn.fetchval(
            f"SELECT count(*) FROM issues WHERE format IN ({_RECOP_SQL})"
        )
        con_evidencia = await conn.fetchval(
            "SELECT count(*) FROM files WHERE cardinality(covered_issue_ids) > 0"
        )
        print("\n" + "=" * 72)
        print(f"VEREDICTO: {total} issues, {recop} recopilaciones, "
              f"{con_evidencia} archivos con covered_issue_ids no vacío.")
        print("  → 'Evidencia de cobertura' hoy se limita a covered_issue_ids (pista")
        print("    sin procedencia ni confirmación). Si es 0, ninguna cobertura es")
        print("    contrastable y el ADR debería valorar POSPONER la tabla de cobertura.")
        print("=" * 72)
    finally:
        await conn.execute("ROLLBACK")
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
