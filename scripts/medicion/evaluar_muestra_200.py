"""Mide parser y matcher contra la muestra etiquetada de 200.

Uso:
    python scripts/medicion/evaluar_muestra_200.py \
        --labels .../muestra_biblioteca_200_2026-11-11_etiquetada_revisada.csv \
        --db-url postgresql+asyncpg://... --json resultados.json

Las filas con ``excluir_benchmark=TRUE`` (dudosas) se separan y no entran en
las métricas principales. No escribe en la base.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import Counter
from pathlib import Path

from zascarr.core.importer_triage import TriageResult
from zascarr.core.matcher import SeriesMatcher, _base_title
from zascarr.utils.naming import ANNUAL_PATTERN, parse_comic_filename


def _canon_serie(s: str) -> str:
    return _base_title(ANNUAL_PATTERN.sub("Annual", s or ""))


def _norm_num(n: str | None) -> str:
    valor = (n or "").strip().lower().replace(" ", "")
    return str(int(valor)) if valor.isdigit() else valor


def _leer(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _parser(rows: list[dict]) -> dict:
    c = Counter()
    for r in rows:
        p = parse_comic_filename(r["archivo"], carpeta=Path(r["ruta"]).parent.name)
        serie = _canon_serie(p.series) == _canon_serie(r["serie_real"])
        numero = _norm_num(p.issue_number) == _norm_num(r["numero_real"])
        c["serie"] += serie
        c["numero"] += numero
        c["ambos"] += serie and numero
        if p.issue_number and not r["numero_real"]:
            c["numero_en_tipo_sin_numero"] += 1
    return dict(c)


async def _matcher(rows: list[dict], db_url: str) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    c = Counter()
    try:
        async with session_factory() as session:
            matcher = SeriesMatcher(session)
            for r in rows:
                p = parse_comic_filename(r["archivo"], carpeta=Path(r["ruta"]).parent.name)
                tr = TriageResult(path=Path(r["ruta"]))
                res = await matcher.decide(
                    tr, extractor=lambda _n, p=p: (p.series, p.issue_number, p.year),
                    annual=p.is_annual,
                    series_alternativa=p.series_alternativa or None)
                c[str(res.status)] += 1
                serie_t = numero_t = None
                if res.series_id:
                    row = (await session.execute(
                        text("SELECT title FROM series WHERE id=:id"),
                        {"id": res.series_id})).first()
                    serie_t = row[0] if row else None
                if res.issue_id:
                    row = (await session.execute(
                        text("SELECT issue_number FROM issues WHERE id=:id"),
                        {"id": res.issue_id})).first()
                    numero_t = row[0] if row else None
                    c["con_issue"] += 1
                serie_ok = bool(serie_t and _canon_serie(serie_t) == _canon_serie(r["serie_real"]))
                numero_ok = _norm_num(numero_t) == _norm_num(r["numero_real"])
                c["serie_ok"] += serie_ok
                c["numero_ok"] += numero_ok
                c["ambos"] += serie_ok and numero_ok
                if r["tipo_real"] in ("pack", "tomo", "obra_unica", "especial") and res.issue_id:
                    c["falso_positivo_tipo_sin_numero"] += 1
    finally:
        await engine.dispose()
    return dict(c)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    rows_todas = _leer(Path(args.labels))
    rows = [r for r in rows_todas
            if (r.get("excluir_benchmark") or "").strip().upper() != "TRUE"]
    resumen = {
        "total": len(rows_todas),
        "excluidas": len(rows_todas) - len(rows),
        "parser": _parser(rows),
    }
    if args.db_url:
        resumen["matcher"] = asyncio.run(_matcher(rows, args.db_url))
    else:
        resumen["matcher"] = "sin --db-url"
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(
            json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
