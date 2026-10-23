#!/usr/bin/env python3
# ruff: noqa: E501
"""Censo de CABECERAS RAR (spike #308, segunda tanda). SOLO LECTURA: abre cada fichero, lee los primeros 4 KiB y los interpreta con la stdlib.
No ejecuta ninguna herramienta, no copia, no escribe nada en la biblioteca (la salida va a la salida estándar o a un TSV que indicas).

Qué dice de cada fichero (sin descomprimir nada):  formato (RAR4 o anterior / RAR5 / ZIP / otro) · ¿SÓLIDO? (bandera del archivo) ·
¿cifrado? (cabeceras cifradas, o el primer fichero del archivo cifrado). Una bandera ausente no prueba lo contrario: «desconocido» es una respuesta válida.

Uso:  python3 censo_cabeceras_rar.py RUTA_BIBLIOTECA [--tsv salida.tsv] [--elegir N]
  --elegir N : imprime las muestras propuestas por REGLA fija (2 sólidos, hasta 2 cifrados, N .cbr típicos, 1 de cada k en orden alfabético).
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

LEER = 4096
RAR4 = b"Rar!\x1a\x07\x00"
RAR5 = b"Rar!\x1a\x07\x01\x00"
EXTENSIONES = {".cbr", ".rar", ""}                  # lo que interesa: .cbr, .rar y los ficheros sin extensión (en el censo había 12)


@dataclass(frozen=True)
class Cabecera:
    firma: str                    # "RAR4", "RAR5", "ZIP", "7z", "otro"
    solido: bool | None           # None = no se pudo saber
    cifrado: str                  # "no", "cabeceras", "archivos", "desconocido"


def _vint(b: bytes, pos: int) -> tuple[int, int] | None:
    """Entero de longitud variable de RAR5 (7 bits por byte, el bit alto marca continuación). Devuelve (valor, nueva posición) o None."""
    v, desplaza = 0, 0
    while pos < len(b) and desplaza <= 63:
        c = b[pos]
        pos += 1
        v |= (c & 0x7F) << desplaza
        if not c & 0x80:
            return v, pos
        desplaza += 7
    return None


def _rar4(b: bytes) -> Cabecera:
    p = len(RAR4)
    if len(b) < p + 7:
        return Cabecera("RAR4", None, "desconocido")
    _crc, tipo, flags, tam = struct.unpack_from("<HBHH", b, p)
    if tipo != 0x73:                                   # el primer bloque debe ser el principal
        return Cabecera("RAR4", None, "desconocido")
    solido = bool(flags & 0x0008)
    if flags & 0x0080:                                 # MHD_PASSWORD: las cabeceras de los bloques van cifradas
        return Cabecera("RAR4", solido, "cabeceras")
    p += tam
    for _ in range(32):                                # recorre bloques hasta el primer fichero (tipo 0x74)
        if p + 7 > len(b) or tam < 7:
            return Cabecera("RAR4", solido, "desconocido")
        _crc, tipo, flags, tam = struct.unpack_from("<HBHH", b, p)
        if tipo == 0x74:
            return Cabecera("RAR4", solido, "archivos" if flags & 0x0004 else "no")
        if tipo in (0x7B,):                            # fin de archivo sin ficheros
            return Cabecera("RAR4", solido, "no")
        extra = struct.unpack_from("<I", b, p + 7)[0] if (flags & 0x8000 and p + 11 <= len(b)) else 0
        p += tam + extra
    return Cabecera("RAR4", solido, "desconocido")


def _rar5(b: bytes) -> Cabecera:
    p = len(RAR5)
    solido: bool | None = None
    for _ in range(16):
        if p + 4 > len(b):
            break
        p += 4                                         # CRC32 de la cabecera
        r = _vint(b, p)
        if not r:
            break
        tam, p = r
        ini = p
        fin = ini + tam
        r1 = _vint(b, p)
        if not r1:
            break
        tipo, p = r1
        r2 = _vint(b, p)
        if not r2:
            break
        flags, p = r2
        extra = 0
        if flags & 0x01:
            r3 = _vint(b, p)
            if not r3:
                break
            extra, p = r3
        datos = 0
        if flags & 0x02:
            r4 = _vint(b, p)
            if not r4:
                break
            datos, p = r4
        if tipo == 4:                                  # cabecera de cifrado del archivo: todo lo que sigue va cifrado
            return Cabecera("RAR5", solido, "cabeceras")
        if tipo == 1:                                  # cabecera principal: banderas del archivo
            r5 = _vint(b, p)
            if r5:
                solido = bool(r5[0] & 0x04)
        elif tipo == 2:                                # primer fichero: ¿registro de cifrado en el área extra?
            cif = _rar5_cifrado(b, ini, fin, extra)
            return Cabecera("RAR5", solido, cif)
        if fin > len(b):
            break
        p = fin + datos
    return Cabecera("RAR5", solido, "desconocido")


def _rar5_cifrado(b: bytes, ini: int, fin: int, extra: int) -> str:
    """Busca el registro 0x01 (cifrado de fichero) en el área extra del final de la cabecera del fichero."""
    if extra <= 0:
        return "no"
    if fin > len(b):
        return "desconocido"
    p = fin - extra
    while p < fin:
        r = _vint(b, p)
        if not r:
            return "desconocido"
        tam, q = r
        r2 = _vint(b, q)
        if not r2:
            return "desconocido"
        if r2[0] == 0x01:
            return "archivos"
        p = q + tam
    return "no"


def clasificar(b: bytes) -> Cabecera:
    """Interpreta los primeros bytes de un fichero. Nunca lanza: ante bytes raros devuelve «otro»/«desconocido»."""
    try:
        if b.startswith(RAR5):
            return _rar5(b)
        if b.startswith(RAR4):
            return _rar4(b)
    except (struct.error, IndexError):
        return Cabecera("RAR5" if b.startswith(RAR5) else "RAR4", None, "desconocido")
    if b[:2] == b"PK":
        return Cabecera("ZIP", None, "desconocido")
    if b[:6] == b"7z\xbc\xaf\x27\x1c":
        return Cabecera("7z", None, "desconocido")
    return Cabecera("otro", None, "desconocido")


def recorrer(raiz: Path):
    for dirpath, _dirs, ficheros in os.walk(raiz):
        for n in sorted(ficheros):
            ruta = Path(dirpath) / n
            if ruta.suffix.lower() not in EXTENSIONES:
                continue
            try:
                with open(ruta, "rb") as fh:
                    b = fh.read(LEER)
                yield str(ruta.relative_to(raiz)), ruta.stat().st_size, clasificar(b)
            except OSError as e:
                print(f"! no se pudo leer {ruta.name}: {e.strerror}", file=sys.stderr)


def elegir(filas: list[tuple[str, int, Cabecera]], n_tipicos: int, cada: int = 30, tope_solido: int = 300 << 20) -> list[tuple[str, str]]:
    """Regla fija, sin elección a mano. Devuelve (ruta, motivo)."""
    sel: list[tuple[str, str]] = []
    solidos = sorted((f for f in filas if f[2].solido and f[1] <= tope_solido), key=lambda f: (f[1], f[0]))
    if solidos:
        sel.append((solidos[-1][0], f"sólido, el mayor hasta {tope_solido >> 20} MB ({solidos[-1][1] >> 20} MB)"))
        mediano = solidos[len(solidos) // 2]
        if mediano[0] != solidos[-1][0]:
            sel.append((mediano[0], f"sólido, tamaño mediano ({mediano[1] >> 20} MB)"))
    cifrados = sorted((f for f in filas if f[2].cifrado in ("cabeceras", "archivos")), key=lambda f: (f[1], f[0]))
    for f in cifrados[:2]:
        sel.append((f[0], f"cifrado ({f[2].cifrado}), de los más pequeños ({f[1] >> 20} MB)"))
    ya = {r for r, _ in sel}
    tip = sorted((f for f in filas if f[0].lower().endswith(".cbr") and f[2].firma in ("RAR4", "RAR5") and (1 << 20) <= f[1] <= (150 << 20) and f[0] not in ya), key=lambda f: f[0])
    for f in tip[::cada][:n_tipicos]:
        sel.append((f[0], f"típico (1 de cada {cada} en orden alfabético)"))
    return sel


def resumen(filas: list[tuple[str, int, Cabecera]]) -> str:
    c = Counter((f[2].firma, "sólido" if f[2].solido else ("no sólido" if f[2].solido is False else "sólido ?")) for f in filas)
    cif = Counter(f[2].cifrado for f in filas if f[2].firma.startswith("RAR"))
    out = [f"{len(filas)} ficheros (.cbr, .rar o sin extensión)"]
    out += [f"  {k[0]:<6} {k[1]:<10} {v:>5}" for k, v in sorted(c.items())]
    out += ["Cifrado (solo RAR): " + ", ".join(f"{k}={v}" for k, v in sorted(cif.items()))]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raiz")
    ap.add_argument("--tsv")
    ap.add_argument("--elegir", type=int, metavar="N")
    a = ap.parse_args(argv)
    raiz = Path(a.raiz)
    if not raiz.is_dir():
        print(f"no existe {raiz}", file=sys.stderr)
        return 2
    filas = list(recorrer(raiz))
    if a.tsv:
        Path(a.tsv).write_text("".join(f"{r}\t{t}\t{c.firma}\t{c.solido}\t{c.cifrado}\n" for r, t, c in filas), encoding="utf-8")
    print(resumen(filas), file=sys.stderr)
    if a.elegir is not None:
        for ruta, motivo in elegir(filas, a.elegir):
            print(f"# {motivo}\n{ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
