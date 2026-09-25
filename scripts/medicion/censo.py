"""Censo de la biblioteca real COMPLETA (785 archivos), no de una muestra
elegida a mano. Dos métricas distintas y honestas:

  COBERTURA — qué fracción produce (serie, número). No necesita verdad de
  referencia, así que se puede medir sobre el 100% sin sesgo. NO dice si
  el resultado es correcto, solo si el parser se moja.

  COHORTE   — cuántas "series" distintas salen y cómo se agrupan. Una
  serie que aparece 108 veces con números seguidos es casi con certeza
  una serie real; una que aparece UNA vez suelta es sospechosa. Es
  evidencia sacada de los propios datos del coleccionista.
"""
from __future__ import annotations

import collections
import zipfile
from pathlib import Path

from zascarr.core.matcher import normalize_title
from zascarr.services.importer import COMIC_EXTS
from zascarr.utils.naming import parse_comic_filename

RAIZ = Path("/mnt/Datos/Descargas/Tebeos")


def main() -> None:
    todos = [p for p in RAIZ.rglob("*") if p.is_file()]
    por_ext = collections.Counter(p.suffix.lower() for p in todos)
    comics = [p for p in todos if p.suffix.lower() in COMIC_EXTS]
    fuera = [p for p in todos if p.suffix.lower() not in COMIC_EXTS]

    print(f"ARCHIVOS TOTALES: {len(todos)}")
    print(f"  reconocidos como cómic : {len(comics)}")
    print(f"  fuera de COMIC_EXTS    : {len(fuera)}")
    print("\nPor extensión:")
    for ext, n in por_ext.most_common():
        marca = "ok" if ext in COMIC_EXTS else "XX"
        print(f"  {marca} {ext or '(sin)':<10} {n:>4}")

    # ── Cobertura ────────────────────────────────────────────────────
    con_ambos = con_serie = sin_nada = 0
    parseados = []
    for p in comics:
        r = parse_comic_filename(p.name)
        parseados.append((p, r))
        if r.series and r.issue_number:
            con_ambos += 1
        elif r.series:
            con_serie += 1
        else:
            sin_nada += 1

    total = len(comics)
    print(f"\nCOBERTURA sobre los {total} cómics reconocidos:")
    print(f"  serie + número (clasificable)   {con_ambos:>4}  {con_ambos/total:6.1%}")
    print(f"  solo serie (va a Pendientes)    {con_serie:>4}  {con_serie/total:6.1%}")
    print(f"  ni serie ni número              {sin_nada:>4}  {sin_nada/total:6.1%}")

    # ── Cohortes ─────────────────────────────────────────────────────
    grupos: dict[str, list] = collections.defaultdict(list)
    for p, r in parseados:
        if r.series:
            grupos[normalize_title(r.series)].append((p, r))

    tam = collections.Counter(len(v) for v in grupos.values())
    sueltas = sum(n for t, n in tam.items() if t == 1)
    print(f"\nCOHORTES: {len(grupos)} 'series' distintas salen de {total} archivos")
    print(f"  series que aparecen UNA sola vez : {sueltas}"
          f"  ({sueltas/len(grupos):.0%} de las series, {sueltas/total:.0%} de los archivos)")
    print("\n  Las 12 cohortes más grandes (fiabilidad alta por repetición):")
    for clave, v in sorted(grupos.items(), key=lambda kv: -len(kv[1]))[:12]:
        con_num = sum(1 for _, r in v if r.issue_number)
        print(f"    {len(v):>4} archivos  {con_num:>4} con nº   {clave[:52]}")

    # ── ComicInfo.xml: metadata REAL, sin adivinar ───────────────────
    cbz = [p for p in comics if p.suffix.lower() in {".cbz", ".cb7"}]
    cbr = [p for p in comics if p.suffix.lower() == ".cbr"]
    con_ci = ilegibles = 0
    for p in cbz:
        try:
            with zipfile.ZipFile(p) as zf:
                if any(n.lower().endswith("comicinfo.xml") for n in zf.namelist()):
                    con_ci += 1
        except Exception:
            ilegibles += 1
    print(f"\nCOMICINFO.XML (metadata real embebida, cero adivinación):")
    print(f"  CBZ/CB7 analizables : {len(cbz)}  → con ComicInfo: {con_ci}"
          f"  ({con_ci/len(cbz):.0%})" if cbz else "  sin CBZ")
    print(f"  CBR (no se abren sin unrar, hoy invisibles para capa 0): {len(cbr)}")


main()
