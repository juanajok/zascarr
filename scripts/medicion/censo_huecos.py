#!/usr/bin/env python3
"""censo_huecos.py — ¿puede la vista de huecos decir la verdad con ESTOS datos?

`compute_missing_issues()` (api/series.py) calcula los huecos restando a
`Series.total_issues` el conjunto de `Issue.sort_order` de la serie. Son dos
entradas de naturaleza muy distinta y conviene mirarlas por separado:

  - `Issue.sort_order`  — posición del número. El código de `main` **no lo
    escribe en ningún sitio** (ver `_derive_sort_order`, que se quedó en una
    rama abandonada), así que la hipótesis a comprobar sobre una instalación
    real es "cero filas pobladas".
  - `Series.total_issues` — total esperado, que el enricher copia del catálogo
    externo (`services/enricher.py`), no del disco.

Si `sort_order` está vacío, `compute_missing_issues(N, ∅)` devuelve `[1..N]`:
la vista no dice "no lo sé", dice que **falta todo**. Este censo cuantifica
cuánto de eso hay en la instalación que se le pase.

Uso:

    DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \\
        python3 scripts/medicion/censo_huecos.py

No escribe nada: solo lee.
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


# (etiqueta, SQL) — cada consulta devuelve una sola fila de contadores.
CONSULTAS = [
    (
        "Issues y cuántos tienen sort_order poblado",
        """
        SELECT count(*)                                   AS issues,
               count(sort_order)                          AS con_sort_order,
               count(*) FILTER (WHERE format = 'single_issue') AS grapas
        FROM issues
        """,
    ),
    (
        "Series y cuántas tienen total_issues (el total esperado)",
        """
        SELECT count(*)              AS series,
               count(total_issues)   AS con_total_issues
        FROM series
        """,
    ),
    (
        "Fuente de total_issues (quién lo rellenó)",
        """
        SELECT coalesce(metadata_source, '(sin fuente)') AS fuente,
               count(*)                                  AS series
        FROM series
        WHERE total_issues IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    ),
    (
        "Series que hoy reportarían TODOS sus números como hueco",
        """
        SELECT count(*) AS series_afectadas,
               coalesce(sum(s.total_issues), 0) AS huecos_inventados
        FROM series s
        WHERE s.total_issues IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM issues i
              WHERE i.series_id = s.id AND i.sort_order IS NOT NULL
          )
        """,
    ),
    (
        "Lo que el disco SÍ tiene: issues con algún archivo disponible",
        """
        SELECT count(*) AS issues,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM files f
                   WHERE f.issue_id = i.id AND f.is_missing = false
               )) AS con_archivo_disponible
        FROM issues i
        """,
    ),
    (
        "Archivos por issue: cuántos números tienen 0, 1 o varios",
        """
        SELECT count(*) FILTER (WHERE n = 0) AS sin_archivo,
               count(*) FILTER (WHERE n = 1) AS un_archivo,
               count(*) FILTER (WHERE n > 1) AS varios_archivos
        FROM (
            SELECT i.id,
                   count(f.id) FILTER (WHERE f.is_missing = false) AS n
            FROM issues i
            LEFT JOIN files f ON f.issue_id = i.id
            GROUP BY i.id
        ) t
        """,
    ),
]


async def main() -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        print("=" * 72)
        print("Censo de huecos — ¿los datos dan para calcularlos?")
        print("=" * 72)
        for etiqueta, sql in CONSULTAS:
            filas = await conn.fetch(sql)
            print(f"\n{etiqueta}")
            if not filas:
                print("  (sin filas)")
                continue
            columnas = list(filas[0].keys())
            print("  " + " | ".join(f"{c}" for c in columnas))
            for fila in filas:
                print("  " + " | ".join(str(fila[c]) for c in columnas))

        # Veredicto explícito, que es lo que se viene a buscar.
        fila = await conn.fetchrow(
            "SELECT count(*) AS t, count(sort_order) AS c FROM issues"
        )
        issues, con_sort = fila["t"], fila["c"]
        print("\n" + "=" * 72)
        if issues:
            print(f"VEREDICTO: {con_sort}/{issues} issues con sort_order "
                  f"({con_sort / issues:.1%}).")
        else:
            print("VEREDICTO: no hay issues en la base de datos.")
        if issues and con_sort == 0:
            print("  → La vista de huecos NO puede calcular nada hoy: con el conjunto")
            print("    vacío, compute_missing_issues(N, ∅) devuelve [1..N] y presenta")
            print("    como 'faltante' todo lo que la serie tenga catalogado.")
        print("=" * 72)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
