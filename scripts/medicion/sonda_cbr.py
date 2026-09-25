"""Sonda RF-1: ¿cuántos CBR llevan ComicInfo.xml dentro, y cuánto cuesta
sacarlo? Decide si "leer metadata real" es el mayor salto de calidad o
una dependencia para nada.

Mide lo que pidió el coleccionista:
  - % con ComicInfo (y en qué ruta dentro del archivo: raíz, subcarpeta)
  - tiempo p50/p95 de LISTAR (solo cabeceras) y de EXTRAER (el coste real,
    que en un RAR sólido puede obligar a descomprimir lo anterior)
  - % no legibles, por motivo
"""
from __future__ import annotations

import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path("/mnt/Datos/Descargas/Tebeos")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def corre(cmd: list[str], timeout: int = 120) -> tuple[int, bytes, float]:
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return -1, b"", time.monotonic() - t0


def main() -> None:
    cbrs = sorted(p for p in RAIZ.rglob("*.cbr"))
    random.Random(42).shuffle(cbrs)
    muestra = cbrs[:N]
    print(f"CBR en la biblioteca: {len(cbrs)} — sonda sobre {len(muestra)}\n")

    con_ci = sin_ci = ilegibles = 0
    t_listar: list[float] = []
    t_extraer: list[float] = []
    rutas_ci: dict[str, int] = {}
    fallos: list[tuple[str, str]] = []

    for p in muestra:
        rc, out, dt = corre(["7z", "l", "-ba", "-slt", str(p)])
        t_listar.append(dt)
        if rc != 0:
            ilegibles += 1
            fallos.append((p.name[:50], f"7z l rc={rc}"))
            continue

        entradas = [l[7:] for l in out.decode("utf-8", "replace").splitlines()
                    if l.startswith("Path = ")]
        ci = [e for e in entradas if e.lower().endswith("comicinfo.xml")]
        if not ci:
            sin_ci += 1
            continue

        con_ci += 1
        clave = "raíz" if "/" not in ci[0] and "\\" not in ci[0] else "subcarpeta"
        rutas_ci[clave] = rutas_ci.get(clave, 0) + 1

        rc2, out2, dt2 = corre(["7z", "e", "-so", str(p), ci[0]])
        t_extraer.append(dt2)
        if rc2 != 0 or b"<" not in out2:
            fallos.append((p.name[:50], "extracción falló"))

    n = len(muestra)
    print(f"CON ComicInfo.xml : {con_ci:>3}/{n}  ({con_ci/n:.0%})")
    print(f"SIN ComicInfo.xml : {sin_ci:>3}/{n}")
    print(f"ilegibles con 7z  : {ilegibles:>3}/{n}")
    if rutas_ci:
        print(f"  ubicación dentro del archivo: {rutas_ci}")

    def pct(v: list[float], q: float) -> float:
        return statistics.quantiles(v, n=100)[int(q) - 1] if len(v) > 2 else max(v or [0])

    if t_listar:
        print(f"\nTIEMPO listar (solo cabeceras):  p50 {statistics.median(t_listar):.3f}s"
              f"   p95 {pct(t_listar, 95):.3f}s   máx {max(t_listar):.3f}s")
    if t_extraer:
        print(f"TIEMPO extraer ComicInfo.xml:    p50 {statistics.median(t_extraer):.3f}s"
              f"   p95 {pct(t_extraer, 95):.3f}s   máx {max(t_extraer):.3f}s")
        print(f"  (ojo: este equipo no es la Pi — en la Pi habrá que remedirlo)")
    if fallos:
        print(f"\nFallos ({len(fallos)}):")
        for nombre, motivo in fallos[:8]:
            print(f"  {motivo:<18} {nombre}")


main()
