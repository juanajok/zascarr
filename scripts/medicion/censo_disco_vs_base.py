# ruff: noqa: E501
"""Censo de SOLO LECTURA: ¿qué ficheros hay en el disco que ZascArr no tiene registrados, y por qué? (spike #297)

Compara dos listados que se sacan SIN tocar nada:
  - el inventario del disco (`find . -type f -printf '%P\\t%s\\t%T@\\n'`, el mismo de los planes de despliegue);
  - lo que hay en la tabla `files` (consulta `select`, ver abajo).

No abre la base de datos ni el disco: lee dos ficheros de texto. No escribe nada salvo, si se pide, la lista detallada.
Qué responde, por orden:
  1. cuántos ficheros del disco están registrados (misma ruta), cuántos no, y cuántas filas de la base no tienen fichero;
  2. de los que NO están registrados, por qué es PROBABLE: formato que ZascArr no lee (`.rar`, `.tar`…), descarga a medias
     (`.part`…), sin extensión, **misma ruta con otra codificación o mayúsculas** (un `é` en dos formas Unicode, por ejemplo)
     o un tebeo normal sin registrar; y de estos últimos cuántos tienen el MISMO TAMAÑO que uno registrado (candidatos a copia;
     por tamaño, sin hash: es una pista, no una prueba);
  3. en qué carpetas se concentran.
No decide nada ni propone adoptar: eso es del PO (la ficha del spike lo recoge).

Uso (en la Pi, como `pi`; los dos comandos solo leen):
  cd /media/WDElements/Tebeos && sudo find . -type f -printf '%P\\t%s\\t%T@\\n' | LC_ALL=C sort > /tmp/disco.tsv
  docker exec zascarr-db psql -U comics_admin -d zascarr -At -F "$(printf '\\t')" -c \\
    "select file_path, coalesce(file_size_bytes,-1), is_missing, issue_id is not null from files order by file_path" > /tmp/base.tsv
  python3 scripts/medicion/censo_disco_vs_base.py --disco /tmp/disco.tsv --base /tmp/base.tsv [--lista /tmp/sin-registrar.tsv]
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# Los mismos formatos que `services/importer.py::COMIC_EXTS` (copiados para que el script funcione sin instalar ZascArr).
COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}
DESCARGA_A_MEDIAS = {".part", ".crdownload", ".tmp", ".!qb", ".aria2", ".download"}
PREFIJO_POR_DEFECTO = "/media/library/"


@dataclass(frozen=True)
class FilaBase:
    ruta: str          # relativa a la biblioteca (sin el prefijo del contenedor)
    tamano: int
    is_missing: bool
    con_numero: bool


@dataclass
class Censo:
    en_disco: int = 0
    en_base: int = 0
    comunes: int = 0
    solo_disco: dict[str, str] = field(default_factory=dict)      # ruta → categoría
    solo_base: dict[str, bool] = field(default_factory=dict)      # ruta → ¿ya marcado is_missing?
    mismo_tamano: set[str] = field(default_factory=set)           # rutas de solo_disco con el tamaño de un archivo registrado

    def por_categoria(self) -> Counter:
        return Counter(self.solo_disco.values())


def _norm(ruta: str) -> str:
    return unicodedata.normalize("NFC", ruta).casefold()


def leer_inventario(lineas) -> dict[str, int]:
    """`ruta<TAB>tamaño<TAB>mtime` → {ruta: tamaño}. Las líneas mal formadas se cuentan aparte (ver `main`)."""
    inv: dict[str, int] = {}
    for linea in lineas:
        partes = linea.rstrip("\n").split("\t")
        if len(partes) < 2 or not partes[0]:
            continue
        try:
            inv[partes[0]] = int(partes[1])
        except ValueError:
            continue
    return inv


def leer_base(lineas, prefijo: str = PREFIJO_POR_DEFECTO) -> list[FilaBase]:
    """`file_path<TAB>tamaño<TAB>is_missing<TAB>con_numero` (psql -At: `t`/`f`) → filas con la ruta relativa a la biblioteca."""
    filas: list[FilaBase] = []
    for linea in lineas:
        partes = linea.rstrip("\n").split("\t")
        if len(partes) < 4 or not partes[0]:
            continue
        ruta = partes[0]
        rel = ruta[len(prefijo):] if ruta.startswith(prefijo) else ruta
        try:
            tam = int(partes[1])
        except ValueError:
            tam = -1
        filas.append(FilaBase(rel, tam, partes[2].strip().lower() in ("t", "true", "1"), partes[3].strip().lower() in ("t", "true", "1")))
    return filas


def categoria(ruta: str, hay_otra_forma: bool) -> str:
    ext = PurePosixPath(ruta).suffix.lower()
    if hay_otra_forma:
        return "misma_ruta_otra_forma"             # mayúsculas o Unicode distinto: mismo fichero para una persona
    if ext in COMIC_EXTS:
        return "tebeo_sin_registrar"
    if ext in DESCARGA_A_MEDIAS:
        return "descarga_a_medias"
    if not ext:
        return "sin_extension"
    return "formato_no_soportado"


def comparar(disco: dict[str, int], base: list[FilaBase]) -> Censo:
    c = Censo(en_disco=len(disco), en_base=len(base))
    rutas_base = {f.ruta: f for f in base}
    normas_base = {_norm(f.ruta) for f in base}
    tamanos_base = {f.tamano for f in base if f.tamano >= 0}
    for ruta, tam in disco.items():
        if ruta in rutas_base:
            c.comunes += 1
            continue
        cat = categoria(ruta, _norm(ruta) in normas_base)
        c.solo_disco[ruta] = cat
        if cat == "tebeo_sin_registrar" and tam in tamanos_base:
            c.mismo_tamano.add(ruta)
    for f in base:
        if f.ruta not in disco:
            c.solo_base[f.ruta] = f.is_missing
    return c


def carpeta(ruta: str, niveles: int = 2) -> str:
    partes = PurePosixPath(ruta).parts[:-1]
    return "/".join(partes[:niveles]) if partes else "(raíz)"


def resumen(c: Censo, top: int = 15) -> str:
    out = [f"DISCO: {c.en_disco} ficheros · BASE: {c.en_base} filas · registrados y presentes (misma ruta): {c.comunes}", ""]
    sd = c.por_categoria()
    out.append(f"EN EL DISCO SIN FILA EN LA BASE: {len(c.solo_disco)}")
    textos = {
        "tebeo_sin_registrar": "tebeos (.cbz/.cbr/.cb7/.pdf/.epub) sin registrar",
        "misma_ruta_otra_forma": "misma ruta con otra forma (mayúsculas o Unicode distinto)",
        "formato_no_soportado": "formato que ZascArr no lee (.rar, .tar…)",
        "descarga_a_medias": "descarga a medias (.part…)",
        "sin_extension": "sin extensión",
    }
    for k in ("tebeo_sin_registrar", "misma_ruta_otra_forma", "formato_no_soportado", "descarga_a_medias", "sin_extension"):
        out.append(f"  {sd.get(k, 0):>5}  {textos[k]}")
    out.append(f"  de los tebeos sin registrar, {len(c.mismo_tamano)} tienen el MISMO TAMAÑO que uno registrado (pista de copia; sin hash, no es prueba)")
    exts = Counter(PurePosixPath(r).suffix.lower() or "(sin)" for r, k in c.solo_disco.items() if k != "tebeo_sin_registrar")
    if exts:
        out.append("  extensiones de los que no son tebeos: " + ", ".join(f"{e}={n}" for e, n in exts.most_common(8)))
    out.append("")
    marcados = sum(1 for v in c.solo_base.values() if v)
    out.append(f"EN LA BASE SIN FICHERO EN EL DISCO: {len(c.solo_base)} (ya marcados is_missing: {marcados}; SIN marcar: {len(c.solo_base) - marcados})")
    out.append("")
    por_carp = Counter(carpeta(r) for r, k in c.solo_disco.items() if k in ("tebeo_sin_registrar", "misma_ruta_otra_forma"))
    out.append(f"CARPETAS (2 niveles) con más tebeos sin registrar (top {top}):")
    for carp, n in por_carp.most_common(top):
        out.append(f"  {n:>5}  {carp}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--disco", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--prefijo", default=PREFIJO_POR_DEFECTO, help="prefijo de la biblioteca DENTRO del contenedor (por defecto /media/library/)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--lista", help="escribe aquí `ruta<TAB>categoría<TAB>mismo_tamaño` de los ficheros sin registrar (no se imprime)")
    a = ap.parse_args(argv)
    with open(a.disco, encoding="utf-8", errors="replace") as f:
        disco = leer_inventario(f)
    with open(a.base, encoding="utf-8", errors="replace") as f:
        base = leer_base(f, a.prefijo if a.prefijo.endswith("/") else a.prefijo + "/")
    if not disco or not base:
        print("✗ Uno de los dos listados está vacío o no tiene el formato esperado: no se compara nada.", file=sys.stderr)
        return 2
    sin_prefijo = sum(1 for fila in base if "/" not in fila.ruta and not disco.get(fila.ruta))
    c = comparar(disco, base)
    print(resumen(c, a.top))
    if sin_prefijo > len(base) // 2:
        print("\n! Más de la mitad de la base no cuelga del prefijo: ¿es correcto --prefijo?", file=sys.stderr)
    if a.lista:
        with open(a.lista, "w", encoding="utf-8") as f:
            for ruta, cat in sorted(c.solo_disco.items()):
                f.write(f"{ruta}\t{cat}\t{'si' if ruta in c.mismo_tamano else 'no'}\n")
        print(f"\nLista detallada: {a.lista}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
