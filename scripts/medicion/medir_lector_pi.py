#!/usr/bin/env python3
"""Mide el coste de servir páginas y extraer un RAR en la Pi (BL-LEC0).

No toca la biblioteca: recibe copias sintéticas por ruta. Pensado para ejecutarse
dentro del contenedor `zascarr-orquestador`, que es donde vive `unar`.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path


def _rss_mb() -> float:
    # Linux: ru_maxrss en KiB.
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _child_rss_mb() -> float:
    import resource
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0


def _p50_p95(valores: list[float]) -> tuple[float, float]:
    if not valores:
        return 0.0, 0.0
    orden = sorted(valores)
    p50 = statistics.median(orden)
    p95 = orden[min(len(orden) - 1, int(len(orden) * 0.95))]
    return p50, p95


def medir_cbz(ruta: Path, repeticiones: int) -> dict:
    with zipfile.ZipFile(ruta) as z:
        nombres = [n for n in z.namelist()
                   if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))]
    if not nombres:
        return {"error": "sin imágenes", "archivo": str(ruta)}
    tiempos: list[float] = []
    tamano_pagina = 0
    for i in range(repeticiones):
        t0 = time.perf_counter()
        with zipfile.ZipFile(ruta) as z:          # como la petición: abrir + leer una entrada
            nombre = nombres[i % len(nombres)]
            datos = z.read(nombre)
        tiempos.append((time.perf_counter() - t0) * 1000)
        tamano_pagina = len(datos)
    p50, p95 = _p50_p95(tiempos)
    return {
        "archivo": ruta.name,
        "bytes": ruta.stat().st_size,
        "paginas": len(nombres),
        "bytes_pagina": tamano_pagina,
        "primera_ms": round(tiempos[0], 1),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "rss_pico_mb": round(_rss_mb(), 1),
    }


def medir_rar(ruta: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="lec0-rar-") as tmp:
        t0 = time.perf_counter()
        antes = _child_rss_mb()
        proc = subprocess.run(
            ["unar", "-q", "-f", "-o", tmp, str(ruta)],
            capture_output=True, text=True, timeout=180, check=False)
        segundos = time.perf_counter() - t0
        despues = _child_rss_mb()
        salida = list(Path(tmp).rglob("*"))
        bytes_salida = sum(p.stat().st_size for p in salida if p.is_file())
        ficheros = [p for p in salida if p.is_file()]
        return {
            "archivo": ruta.name,
            "bytes_rar": ruta.stat().st_size,
            "rc": proc.returncode,
            "segundos": round(segundos, 2),
            "bytes_extraidos": bytes_salida,
            "ficheros": len(ficheros),
            "rss_hijo_mb": round(max(0.0, despues - antes), 1),
            "stderr": proc.stderr[-500:],
        }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cbz", type=Path, action="append", default=[])
    p.add_argument("--rar", type=Path, action="append", default=[])
    p.add_argument("--repeticiones", type=int, default=20)
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args()
    resultado = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": os.uname().nodename,
        "cbz": [medir_cbz(r, args.repeticiones) for r in args.cbz],
        "rar": [medir_rar(r) for r in args.rar],
    }
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    print(texto)
    if args.json:
        args.json.write_text(texto + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
