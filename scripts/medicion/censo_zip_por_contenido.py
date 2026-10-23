#!/usr/bin/env python3
# ruff: noqa: E501
"""Censo de ZIP POR CONTENIDO (spike #307). SOLO LECTURA: abre cada candidato como ZIP leyendo ÚNICAMENTE el directorio central (no descomprime nada,
no ejecuta herramientas, no escribe en la biblioteca) y mide lo necesario para fijar el contrato de «reconocer un ZIP por su contenido» CON DATOS:

  · GRUPOS: `cbz_control` (los .cbz que ya sabemos que son tebeos: el control contra falsos negativos) · `cbr_zip` (.cbr/.rar cuya firma es ZIP: los «ocultos»)
            · `sin_extension` · `zip` (los .zip). Solo entran los ficheros cuya firma es ZIP (4 bytes).
  · POR FICHERO: entradas, imágenes, contenedores anidados, ComicInfo, bytes descomprimidos, ratio máximo de compresión, cifrado y la clase PROVISIONAL.
  · Los umbrales de la clase provisional (mínimo de imágenes y fracción de imágenes) son PARÁMETROS: la idea es verlos contra el control y fijarlos después.

Uso:  python3 censo_zip_por_contenido.py RUTA_BIBLIOTECA [--tsv salida.tsv] [--min-imagenes 5] [--fraccion 0.8]
La salida estándar solo lleva recuentos y cifras (nunca nombres de ficheros); los nombres van al TSV, que es tuyo.
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

MAX_ENTRADAS = 1000                    # los de hoy (core/importer_triage.py)
MAX_DESCOMPRIMIDO = 500 * 1024 * 1024
IMAGENES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
CONTENEDORES = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".cbt", ".tar", ".gz", ".epub", ".pdf"}
RUIDO = {"thumbs.db", ".ds_store", "desktop.ini", "comicinfo.xml"}      # no cuentan como «contenido» para la fracción de imágenes
FIRMAS_ZIP = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")            # normal, vacío, partido


@dataclass(frozen=True)
class Medida:
    estado: str                         # "ok" | "invalido" | "demasiadas_entradas" | "demasiado_grande" | "vacio"
    entradas: int = 0                   # sin carpetas
    imagenes: int = 0
    anidados: int = 0                   # entradas con extensión de contenedor
    comicinfo: bool = False
    descomprimido: int = 0
    ratio_max: float = 0.0
    cifrado: bool = False
    contenido: int = 0                  # entradas que no son ruido ni carpetas
    mayor_entrada: int = 0              # bytes descomprimidos de la entrada más grande (lo que importa si solo se lee UNA página)
    pagina1_bytes: int = 0              # primera imagen en orden natural (la que daría la portada)
    pagina1_ratio: float = 0.0


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def grupo_de(ruta: Path) -> str | None:
    ext = ruta.suffix.lower()
    if ext == ".cbz":
        return "cbz_control"
    if ext in (".cbr", ".rar", ".cb7"):
        return "cbr_zip"
    if ext == ".zip":
        return "zip"
    if ext == "" and not ruta.name.startswith("."):
        return "sin_extension"
    return None


def es_zip(ruta: Path) -> bool:
    try:
        with open(ruta, "rb") as fh:
            return fh.read(4) in FIRMAS_ZIP
    except OSError:
        return False


def medir(ruta: Path, max_entradas: int = MAX_ENTRADAS, max_descomprimido: int = MAX_DESCOMPRIMIDO) -> Medida:
    """Lee SOLO el directorio central. Nunca descomprime. Nunca lanza."""
    try:
        zf = zipfile.ZipFile(ruta)
    except (OSError, zipfile.BadZipFile, ValueError, NotImplementedError):
        return Medida("invalido")
    with zf:
        try:
            infos = zf.infolist()
        except (OSError, ValueError, zipfile.BadZipFile):
            return Medida("invalido")
        if not infos:
            return Medida("vacio")
        ficheros = [i for i in infos if not i.is_dir()]
        total = sum(i.file_size for i in ficheros)
        # Los topes marcan el ESTADO pero las medidas se rellenan igual (solo directorio central): hace falta saber cómo son los que los superan.
        estado = "demasiadas_entradas" if len(infos) > max_entradas else ("demasiado_grande" if total > max_descomprimido else "ok")
        nombres = [Path(i.filename) for i in ficheros]
        imgs = sorted((i for i in ficheros if Path(i.filename).suffix.lower() in IMAGENES), key=lambda i: natural(i.filename))
        p1 = imgs[0] if imgs else None
        ratios = [i.file_size / i.compress_size for i in ficheros if i.compress_size > 0]
        return Medida(
            estado, entradas=len(ficheros),
            imagenes=sum(1 for n in nombres if n.suffix.lower() in IMAGENES),
            anidados=sum(1 for n in nombres if n.suffix.lower() in CONTENEDORES),
            comicinfo=any(n.name.lower() == "comicinfo.xml" for n in nombres),
            descomprimido=total, ratio_max=round(max(ratios), 1) if ratios else 0.0,
            cifrado=any(i.flag_bits & 0x1 for i in ficheros),
            contenido=sum(1 for n in nombres if n.name.lower() not in RUIDO),
            mayor_entrada=max((i.file_size for i in ficheros), default=0),
            pagina1_bytes=p1.file_size if p1 else 0,
            pagina1_ratio=round(p1.file_size / p1.compress_size, 2) if p1 and p1.compress_size else 0.0,
        )


def clasificar(m: Medida, min_imagenes: int = 5, fraccion: float = 0.8) -> str:
    """Clase PROVISIONAL (se fija con los datos): tebeo | paquete | no_tebeo | cifrado | invalido | vacio | limite."""
    if m.estado in ("demasiadas_entradas", "demasiado_grande"):
        return "limite"
    if m.estado != "ok":
        return m.estado
    if m.cifrado:
        return "cifrado"
    if m.anidados:
        return "paquete"
    if m.imagenes >= min_imagenes and m.contenido and m.imagenes / m.contenido >= fraccion:
        return "tebeo"
    return "no_tebeo"


def recorrer(raiz: Path):
    for dirpath, _d, ficheros in os.walk(raiz):
        for n in sorted(ficheros):
            ruta = Path(dirpath) / n
            g = grupo_de(ruta)
            if g and es_zip(ruta):
                try:
                    yield g, ruta.relative_to(raiz), ruta.stat().st_size, medir(ruta)
                except OSError:
                    continue


def resumen(filas: list[tuple[str, Path, int, Medida]], min_imagenes: int, fraccion: float) -> str:
    out = [f"Umbrales provisionales: mínimo {min_imagenes} imágenes y {fraccion:.0%} de imágenes sobre el contenido"]
    for g in ("cbz_control", "cbr_zip", "sin_extension", "zip"):
        fs = [f for f in filas if f[0] == g]
        if not fs:
            continue
        clases = Counter(clasificar(f[3], min_imagenes, fraccion) for f in fs)
        ok = [f[3] for f in fs if f[3].estado == "ok"]
        out.append(f"\n[{g}] {len(fs)} ficheros con firma ZIP: " + ", ".join(f"{k}={v}" for k, v in sorted(clases.items())))
        if ok:
            im = sorted(m.imagenes for m in ok)
            out.append(f"  imágenes: mín {im[0]}, p10 {im[len(im) // 10]}, mediana {int(statistics.median(im))}, máx {im[-1]}")
            out.append(f"  con ComicInfo.xml: {sum(m.comicinfo for m in ok)} de {len(ok)}; con anidados: {sum(1 for m in ok if m.anidados)}; cifrados: {sum(m.cifrado for m in ok)}")
            out.append(f"  ratio de compresión máximo (por entrada): {max(m.ratio_max for m in ok)}; descomprimido máx: {max(m.descomprimido for m in ok) >> 20} MiB; entradas máx: {max(m.entradas for m in ok)}")
            out.append(f"  entrada mayor (KiB): mediana {int(statistics.median(m.mayor_entrada for m in ok)) >> 10}, máx {max(m.mayor_entrada for m in ok) >> 10}; primera página (KiB): mediana {int(statistics.median(m.pagina1_bytes for m in ok)) >> 10}, máx {max(m.pagina1_bytes for m in ok) >> 10}; su ratio máx {max(m.pagina1_ratio for m in ok)}")
        lim = [f[3] for f in fs if f[3].estado in ("demasiadas_entradas", "demasiado_grande")]
        if lim:
            out.append(f"  SUPERAN los topes de hoy (1000 entradas / 500 MiB descomprimidos): {len(lim)} de {len(fs)} ({Counter(m.estado for m in lim).most_common()})")
            out.append(f"    cómo son: imágenes mín {min(m.imagenes for m in lim)} / máx {max(m.imagenes for m in lim)}; con ComicInfo.xml: {sum(m.comicinfo for m in lim)} de {len(lim)}; anidados: {sum(1 for m in lim if m.anidados)}; cifrados: {sum(m.cifrado for m in lim)}")
            out.append(f"    entrada mayor máx {max(m.mayor_entrada for m in lim) >> 10} KiB; primera página máx {max(m.pagina1_bytes for m in lim) >> 10} KiB, ratio máx {max(m.pagina1_ratio for m in lim)}; ratio por entrada máx {max(m.ratio_max for m in lim)}; descomprimido {min(m.descomprimido for m in lim) >> 20}–{max(m.descomprimido for m in lim) >> 20} MiB")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raiz")
    ap.add_argument("--tsv")
    ap.add_argument("--min-imagenes", type=int, default=5)
    ap.add_argument("--fraccion", type=float, default=0.8)
    a = ap.parse_args(argv)
    raiz = Path(a.raiz)
    if not raiz.is_dir():
        print(f"no existe {raiz}", file=sys.stderr)
        return 2
    filas = list(recorrer(raiz))
    if a.tsv:
        Path(a.tsv).write_text("".join(
            f"{g}\t{r}\t{t}\t{clasificar(m, a.min_imagenes, a.fraccion)}\t{m.estado}\t{m.entradas}\t{m.imagenes}\t{m.anidados}\t{int(m.comicinfo)}\t{m.descomprimido}\t{m.ratio_max}\t{int(m.cifrado)}\t{m.mayor_entrada}\t{m.pagina1_bytes}\t{m.pagina1_ratio}\n"
            for g, r, t, m in filas), encoding="utf-8")
    print(resumen(filas, a.min_imagenes, a.fraccion))
    return 0


if __name__ == "__main__":
    sys.exit(main())
