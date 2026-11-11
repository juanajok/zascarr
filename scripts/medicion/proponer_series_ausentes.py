"""Propuesta de series ausentes para archivos sin Issue.

Lee la biblioteca en READ ONLY, parsea los archivos sin Issue con la carpeta
como contexto y agrupa los que no encuentran serie en el catálogo. No crea
series, Issues ni enlaces. Escribe un JSON de propuesta para revisión.

Uso:
    python scripts/medicion/proponer_series_ausentes.py --db-url ... --output ...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zascarr.core.matcher import CATALOG_ALIASES, _base_title, normalize_title  # noqa: E402
from zascarr.utils.naming import parse_comic_filename  # noqa: E402


def _catalogo(series: list[dict]) -> dict[str, str]:
    por_titulo: dict[str, str] = {}
    for s in series:
        for key in {normalize_title(s["title"]), _base_title(s["title"])}:
            por_titulo.setdefault(key, s["title"])
    return por_titulo


def _canon(s: str, catalogo: dict[str, str]) -> str | None:
    norm = normalize_title(s)
    if norm in CATALOG_ALIASES:
        norm = normalize_title(CATALOG_ALIASES[norm])
    if norm in catalogo:
        return catalogo[norm]
    base = _base_title(s)
    return catalogo.get(base)


def _tradicion(ruta: str) -> str:
    if "/Manga/" in ruta:
        return "manga"
    if "/Tebeos/" in ruta:
        return "tebeo"
    if "/Graphic Novels/" in ruta:
        return "franco_belgian"
    return "american"


def _confianza(n: int, issues: list[str]) -> str:
    numericos = [x for x in issues if x.isdigit()]
    if n >= 10 and len(numericos) >= 5:
        return "alta"
    if n >= 3:
        return "media"
    return "baja"


async def _leer(db_url: str) -> tuple[list[dict], list[dict]]:
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("BEGIN TRANSACTION READ ONLY")
        files = await conn.fetch("""
            SELECT id, file_name, file_path FROM files
            WHERE issue_id IS NULL AND is_missing = false
            ORDER BY file_name
        """)
        series = await conn.fetch("""
            SELECT id, title, kind::text AS kind FROM series ORDER BY title
        """)
        return [dict(r) for r in files], [dict(r) for r in series]
    finally:
        await conn.close()


def _titulo_con_contexto(series: str, carpeta: str) -> str:
    """Título propuesto sin mezclar ediciones de la misma serie."""
    ns, nc = normalize_title(series), normalize_title(carpeta)
    if nc and ns and ns in nc:
        return carpeta.strip(" -_.,")
    if re.search(r"\b(?:año|ano|vol(?:umen)?|tomo)\b", carpeta, re.IGNORECASE):
        return f"{series} ({carpeta.strip(' -_.,')})"
    return series


def _grupos(files: list[dict], catalogo: dict[str, str]) -> list[dict]:
    grupos: dict[str, list[tuple[dict, object]]] = defaultdict(list)
    for f in files:
        p = parse_comic_filename(f["file_name"], carpeta=Path(f["file_path"]).parent.name)
        if not p.series:
            continue
        if _canon(p.series, catalogo) is not None:
            continue
        carpeta = Path(f["file_path"]).parent.name
        grupos[(normalize_title(p.series), normalize_title(carpeta))].append((f, p))

    propuestas = []
    for items in grupos.values():
        carpeta = Path(items[0][0]["file_path"]).parent.name
        titulo = _titulo_con_contexto(items[0][1].series, carpeta)
        issues = sorted({p.issue_number for _, p in items if p.issue_number},
                        key=lambda x: (not x.isdigit(), x))
        kinds = Counter("annual" if p.is_annual else "special" if p.is_special else "regular"
                        for _, p in items)
        carpetas = Counter(Path(f["file_path"]).parent.name for f, _ in items)
        anios = sorted({int(m.group(1)) for f, _ in items
                        for m in [re.search(r"\b(19|20)\d{2}\b", f["file_path"])] if m})
        propuestas.append({
            "titulo_propuesto": titulo,
            "archivos": len(items),
            "issues": issues,
            "kind": kinds.most_common(1)[0][0],
            "kinds": dict(kinds),
            "tradicion": Counter(_tradicion(f["file_path"]) for f, _ in items).most_common(1)[0][0],
            "carpeta": carpeta,
            "carpetas": [c for c, _ in carpetas.most_common(3)],
            "anios": anios[-3:],
            "confianza": _confianza(len(items), issues),
            "accion": "crear_serie" if len(items) >= 3 else "revisar",
            "motivo": ("serie no presente en catálogo; "
                       f"{len(items)} archivos sin Issue"),
        })
    propuestas.sort(key=lambda p: (-p["archivos"], p["titulo_propuesto"].lower()))
    return propuestas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    if not args.db_url:
        raise SystemExit("Falta --db-url o DATABASE_URL")
    files, series = asyncio.run(_leer(args.db_url))
    propuestas = _grupos(files, _catalogo(series))
    resumen = {
        "total_archivos_sin_issue": len(files),
        "series_ausentes": len(propuestas),
        "archivos_en_grupos": sum(p["archivos"] for p in propuestas),
        "crear_serie": sum(1 for p in propuestas if p["accion"] == "crear_serie"),
        "revisar": sum(1 for p in propuestas if p["accion"] == "revisar"),
        "por_confianza": dict(Counter(p["confianza"] for p in propuestas)),
        "top": propuestas[:20],
        "propuestas": propuestas,
    }
    Path(args.output).write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: resumen[k] for k in resumen if k != "top" and k != "propuestas"},
                     ensure_ascii=False, indent=2))
    print("top:")
    for p in resumen["top"]:
        print(f"  {p['archivos']:3} | {p['titulo_propuesto']} | "
              f"{p['kind']} | {p['tradicion']} | {p['confianza']}")


if __name__ == "__main__":
    main()
