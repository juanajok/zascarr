#!/usr/bin/env python3
"""Modelo reproducible de U15 (#202): qué sugeriría el código actual para 20 títulos.

NO consulta fuentes externas. Lee `titulos.json` (fixtures sintéticos) y aplica el
mapeo que hoy hace `services/discovery.py`: la tradición se deriva de la FUENTE,
no de la obra. Sirve para demostrar el riesgo estructural y para fijar el contrato
de presentación; no sustituye la medición con respuestas reales.

Uso:
    python3 docs/design/ui-u15/medir_u15.py
"""
from __future__ import annotations

import json
from pathlib import Path

DOC = Path(__file__).parent

# Mapeo actual de `services/discovery.py` (2026-10-21, origin/main 8589b47).
SUGERENCIA_POR_FUENTE = {
    "comic_vine": "american",
    "anilist": "manga",
    "tebeosfera": "tebeo",
}

ETIQUETA = {
    "american": "Grapa americana",
    "franco_belgian": "Franco-belga (BD)",
    "manga": "Manga",
    "tebeo": "Tebeo español",
    "fumetti": "Fumetti",
    "manhwa": "Manhwa",
    "manhua": "Manhua",
    "british": "Británico",
    "other": "Otra",
}


def main() -> None:
    datos = json.loads((DOC / "titulos.json").read_text(encoding="utf-8"))
    filas = []
    for t in datos["titulos"]:
        sugerida = SUGERENCIA_POR_FUENTE[t["fuente"]]
        filas.append((t["titulo"], t["referencia"], t["fuente"], sugerida, sugerida == t["referencia"]))

    print("| Título | Referencia | Fuente simulada | Sugerencia actual | ¿Coincide? |")
    print("|---|---|---|---|---|")
    for titulo, ref, fuente, sug, ok in filas:
        print(f"| {titulo} | {ETIQUETA[ref]} | {fuente} | {ETIQUETA[sug]} | {'sí' if ok else 'NO'} |")

    total = len(filas)
    aciertos = sum(1 for *_, ok in filas if ok)
    print()
    print(f"Total: {total}. Coincidencias: {aciertos}. Discrepancias: {total - aciertos}.")
    for fuente in sorted({f for _, _, f, _, _ in filas}):
        sub = [x for x in filas if x[2] == fuente]
        print(f"- {fuente}: {sum(1 for *_, ok in sub if ok)}/{len(sub)} coincidencias.")
    tebeo = [x for x in filas if x[1] == "tebeo"]
    print(f"- tebeo español: {sum(1 for *_, ok in tebeo if ok)}/{len(tebeo)} coincidencias "
          f"(todas las de este fixture vienen de Comic Vine).")


if __name__ == "__main__":
    main()
