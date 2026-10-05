#!/usr/bin/env python3
# ruff: noqa: E501
"""B14 — mide, SOLO LEYENDO, cuánto aporta el nombre de la carpeta frente al del archivo.

Recorre una biblioteca (sin escribir nada, sin BD), parsea cada nombre con el parser de producción y lo compara
con los nombres de las carpetas que lo contienen. No decide ninguna serie: clasifica la RELACIÓN entre las dos
señales para que una persona revise las discrepancias. La salida lleva rutas reales: queda en el directorio
que se indique y NO debe publicarse (ver la política de privacidad de las mediciones en el ADR 0006).

Uso:  python scripts/medicion/medir_carpetas.py /ruta/biblioteca  -o salida.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from zascarr.core.matcher import normalize_title
from zascarr.utils.naming import parse_comic_filename

EXTENSIONES = {".cbz", ".cbr", ".cb7"}
_CORCHETES = re.compile(r"\[[^\]]*\]")
_PARENTESIS = re.compile(r"\(([^)]*)\)")
_ANIO = re.compile(r"^(?:19|20)\d{2}(?:\s*-\s*(?:\d{2}|\d{4}))?$")


def limpiar_carpeta(nombre: str) -> tuple[str, int | None, list[str]]:
    """(título, año, etiquetas) de un nombre de carpeta: quita corchetes y paréntesis, que llevan año y
    etiquetas de release («(COMPLETO)(CRG)»), y los separa."""
    anio: int | None = None
    etiquetas: list[str] = [m.group(0) for m in _CORCHETES.finditer(nombre)]
    for m in _PARENTESIS.finditer(nombre):
        dentro = m.group(1).strip()
        if _ANIO.match(dentro):
            anio = anio or int(dentro[:4])
        else:
            etiquetas.append(m.group(0))
    titulo = _PARENTESIS.sub(" ", _CORCHETES.sub(" ", nombre))
    return re.sub(r"\s+", " ", titulo).strip(" -_."), anio, etiquetas


def relacion(titulo_archivo: str, titulo_carpeta: str) -> str:
    a, c = normalize_title(titulo_archivo), normalize_title(titulo_carpeta)
    if not a:
        return "sin_titulo_en_el_nombre"
    if not c:
        return "carpeta_vacia"
    if a == c:
        return "igual"
    if c in a:
        return "carpeta_dentro_del_nombre"
    if a in c:
        return "nombre_dentro_de_la_carpeta"
    return "distinto"


def medir(raiz: Path) -> list[dict]:
    filas = []
    for ruta in sorted(raiz.rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
            continue
        rel = ruta.relative_to(raiz)
        carpetas = list(rel.parts[:-1])
        p = parse_comic_filename(ruta.name)
        # El primer nivel es la tradición («Comics», «BD»…): contenedor, nunca serie.
        candidatas = carpetas[1:] or []
        mejor = candidatas[-1] if candidatas else None
        limpia, anio_c, etiquetas = limpiar_carpeta(mejor) if mejor else ("", None, [])
        filas.append({
            "ruta": str(rel), "niveles": len(carpetas),
            "archivo_serie": p.series, "archivo_numero": p.issue_number, "archivo_anio": p.year,
            "carpeta": mejor, "carpeta_limpia": limpia, "carpeta_anio": anio_c, "carpeta_etiquetas": etiquetas,
            "relacion": relacion(p.series, limpia) if mejor else "sin_carpeta_de_serie",
        })
    return filas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz", type=Path)
    ap.add_argument("-o", "--salida", type=Path, required=True)
    args = ap.parse_args()
    filas = medir(args.raiz)
    args.salida.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    cuenta = Counter(f["relacion"] for f in filas)
    print(f"{len(filas)} archivos")
    for k, v in cuenta.most_common():
        print(f"  {k:32} {v:5}  {100 * v / len(filas):5.1f} %")


if __name__ == "__main__":
    main()
