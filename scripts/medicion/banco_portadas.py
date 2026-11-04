#!/usr/bin/env python3
"""Banco de coste de la portada de serie (BL-PORT1, #300; AC-12/NFR-02…06).

Mide, **solo leyendo**, cuánto cuesta extraer la portada de CBZ reales a los
dos anchos que usa la aplicación: 240 («Por revisar») y 600 (Biblioteca,
Inicio y ficha). No escribe en la caché, no toca la base de datos y no abre
ningún archivo en modo escritura: la biblioteca se puede pasar tal cual.

Qué mide y con qué umbral (propuesta de la ficha §10.1, a ratificar por el PO):

  - p50 y p95 de la extracción en frío (por ancho). p95 ≤ 400 ms a 600 px;
    ≤ 600 ms si el original supera 12 Mpx.
  - bytes del JPEG de salida (media ≤ 60 KB/portada) y ancho resultante, para
    ver cuántos originales pequeños se quedan por debajo de 600 sin ampliar.
  - opcionalmente, delta de RSS del proceso (`--rss`): ≤ 40 MB.

Lo que este banco NO mide (queda para la medida de página, §10.2): 30 portadas
en frío con 6 peticiones concurrentes, caliente-304, `docker stats`/cgroup ni
`du` del directorio de caché. Se imprime como NOT RUN para no confundirlo con
un FAIL.

Uso (dentro del contenedor de la app, con la rama de BL-PORT1 desplegada):

  python scripts/medicion/banco_portadas.py \\
      --carpeta /media/library --muestra 30 --repeticiones 5 --rss \\
      --json /tmp/banco-portadas.json

La muestra es determinista: los N primeros `.cbz`/`.zip` por ruta ordenada.
Para los casos borde (original 400×600, 8000×12000, CBR real, ZIP declarado
CBR, serie solo con `cover_url`) basta con incluirlos en la carpeta o pasarlos
en otra ejecución con `--muestra` pequeño.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import resource
import sys
import time
from pathlib import Path

from PIL import Image

from zascarr.utils.cover import SERIES_COVER_MAX_WIDTH, extract_cover_thumbnail

#: «Por revisar» (FR-17): se mide también para comparar el sobrecoste de 600.
ANCHO_REVISION = 240

#: Umbral de píxeles de la ficha: por encima, el p95 admite 600 ms.
PIXELES_GRANDES = 12_000_000

UMBRAL_P95_MS = {ANCHO_REVISION: 400.0, SERIES_COVER_MAX_WIDTH: 400.0}
UMBRAL_P95_GRANDE_MS = 600.0
UMBRAL_MEDIA_BYTES = 60 * 1024
UMBRAL_RSS_MB = 40.0


def _percentil(valores: list[float], p: float) -> float | None:
    """Percentil por rango más cercano (suficiente para 5 repeticiones por caso)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, math.ceil(p / 100 * len(ordenados)) - 1))
    return ordenados[indice]


def _rss_mb() -> float:
    """RSS máximo del proceso en MB (Linux devuelve `ru_maxrss` en KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _cbz(carpeta: Path, muestra: int) -> list[Path]:
    candidatos = sorted(
        p for p in carpeta.rglob("*")
        if p.is_file() and p.suffix.lower() in {".cbz", ".zip"}
    )
    return candidatos[:muestra]


def _medir_archivo(path: Path, ancho: int, repeticiones: int) -> dict | None:
    """Extrae `repeticiones` veces a `ancho`. None si el archivo no da portada."""
    tiempos: list[float] = []
    datos: bytes | None = None
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        resultado = extract_cover_thumbnail(path, ancho=ancho)
        tiempos.append((time.perf_counter() - inicio) * 1000)
        if resultado is None:
            return None
        datos = resultado[0]
    with Image.open(io.BytesIO(datos)) as img:
        ancho_salida, alto_salida = img.width, img.height
    return {
        "archivo": str(path),
        "tiempos_ms": tiempos,
        "mediana_ms": _percentil(tiempos, 50),
        "p95_ms": _percentil(tiempos, 95),
        "bytes": len(datos),
        "ancho_salida": ancho_salida,
        "alto_salida": alto_salida,
        "pixeles_original": ancho_salida * alto_salida,
    }


def _resumen(casos: list[dict], ancho: int) -> dict:
    tiempos = [t for caso in casos for t in caso["tiempos_ms"]]
    bytes_ = [caso["bytes"] for caso in casos]
    anchos = [caso["ancho_salida"] for caso in casos]
    grandes = [caso for caso in casos if caso["pixeles_original"] > PIXELES_GRANDES]
    p95 = _percentil(tiempos, 95)
    media_bytes = sum(bytes_) / len(bytes_) if bytes_ else 0

    def _dentro_del_umbral(caso: dict) -> bool:
        limite = UMBRAL_P95_GRANDE_MS if caso["pixeles_original"] > PIXELES_GRANDES else (
            UMBRAL_P95_MS[ancho]
        )
        return caso["p95_ms"] is not None and caso["p95_ms"] <= limite

    lentos = [caso for caso in casos if not _dentro_del_umbral(caso)]
    return {
        "ancho": ancho,
        "n_archivos": len(casos),
        "n_archivos_grandes": len(grandes),
        "p50_ms": round(_percentil(tiempos, 50) or 0, 1),
        "p95_ms": round(p95 or 0, 1),
        "p95_limite_ms": UMBRAL_P95_MS[ancho],
        "p95_pasa": p95 is not None and not lentos,
        "n_lentos": len(lentos),
        "media_bytes": round(media_bytes),
        "media_pasa": media_bytes <= UMBRAL_MEDIA_BYTES,
        "ancho_salida_min": min(anchos) if anchos else None,
        "ancho_salida_max": max(anchos) if anchos else None,
        "por_debajo_de_600": sum(1 for a in anchos if a < SERIES_COVER_MAX_WIDTH),
    }


def _imprimir(informe: dict) -> None:
    print("")
    print("BANCO DE PORTADAS — BL-PORT1 (#300), AC-12")
    print(f"Carpeta: {informe['carpeta']}")
    print(f"Archivos medidos: {informe['n_medidos']} de {informe['n_candidatos']} "
          f"(muestra {informe['muestra']}, {informe['repeticiones']} repeticiones)")
    print(f"Fallos sin portada (CBR real, corrupto…): {informe['n_fallos']}")
    if informe["n_fallos"]:
        print("  " + ", ".join(Path(f).name for f in informe["fallos"][:5]))
    print("")
    print(f"{'Ancho':>6} {'p50':>9} {'p95':>9} {'límite':>9} {'PASS/FAIL':>10} "
          f"{'KB medio':>9} {'ΔRSS':>8}")
    for fila in informe["resumen"]:
        limite = f"{fila['p95_limite_ms']:.0f} ms" + ("*" if fila["n_archivos_grandes"] else "")
        rss = f"{informe['rss_delta_mb']:.1f} MB" if informe["rss_delta_mb"] is not None else "—"
        veredicto = "PASS" if fila["p95_pasa"] and fila["media_pasa"] else "FAIL"
        print(f"{fila['ancho']:>6} {fila['p50_ms']:>7.1f} ms {fila['p95_ms']:>7.1f} ms "
              f"{limite:>9} {veredicto:>10} {fila['media_bytes'] / 1024:>8.1f} {rss:>8}")
    if any(fila["n_archivos_grandes"] for fila in informe["resumen"]):
        print("* hay originales > 12 Mpx: su p95 propio admite 600 ms")
    print("")
    for fila in informe["resumen"]:
        linea = (f"  a {fila['ancho']} px: salida {fila['ancho_salida_min']}–"
                 f"{fila['ancho_salida_max']} px de ancho; media {fila['media_bytes']} B")
        if fila["ancho"] >= SERIES_COVER_MAX_WIDTH:
            linea += (f"; {fila['por_debajo_de_600']} de {fila['n_archivos']} quedan por debajo "
                      f"de 600 (originales pequeños, no se amplían)")
        print(linea)
    if informe["rss_delta_mb"] is not None:
        rss_ok = informe["rss_delta_mb"] <= UMBRAL_RSS_MB
        print(f"  RSS máximo del proceso: {informe['rss_inicial_mb']:.1f} → "
              f"{informe['rss_final_mb']:.1f} MB (Δ {informe['rss_delta_mb']:.1f} MB, "
              f"{'PASS' if rss_ok else 'FAIL'} con límite {UMBRAL_RSS_MB:.0f} MB)")
    print("")
    print("NOT RUN en este banco (medida de página, ficha §10.2): 30 portadas en frío con 6")
    print("peticiones concurrentes; caliente 304; docker stats/cgroup; du de la caché.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Coste de extraer la portada de serie a 240 y a 600 px (solo lectura)."
    )
    parser.add_argument("--carpeta", required=True, type=Path,
                        help="carpeta con CBZ reales (se recorre en busca de .cbz/.zip)")
    parser.add_argument("--muestra", type=int, default=30,
                        help="n.º de archivos a medir (los primeros por ruta ordenada)")
    parser.add_argument("--repeticiones", type=int, default=5,
                        help="repeticiones por archivo y ancho")
    parser.add_argument("--rss", action="store_true",
                        help="anotar el delta de RSS del proceso (ru_maxrss)")
    parser.add_argument("--json", type=Path, default=None,
                        help="escribir el informe completo en JSON en esta ruta")
    args = parser.parse_args(argv)

    if not args.carpeta.is_dir():
        print(f"No existe la carpeta: {args.carpeta}", file=sys.stderr)
        return 2
    if args.muestra < 1 or args.repeticiones < 1:
        print("La muestra y las repeticiones deben ser >= 1", file=sys.stderr)
        return 2

    archivos = _cbz(args.carpeta, args.muestra)
    if not archivos:
        print(f"No hay ningún .cbz/.zip en {args.carpeta}", file=sys.stderr)
        return 2

    rss_inicial = _rss_mb() if args.rss else None
    casos: dict[int, list[dict]] = {ANCHO_REVISION: [], SERIES_COVER_MAX_WIDTH: []}
    fallos: list[str] = []
    for path in archivos:
        for ancho in casos:
            caso = _medir_archivo(path, ancho, args.repeticiones)
            if caso is None:
                fallos.append(str(path))
                break
            casos[ancho].append(caso)

    resumen = [_resumen(lista, ancho) for ancho, lista in casos.items()]
    rss_final = _rss_mb() if args.rss else None
    informe = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "carpeta": str(args.carpeta),
        "muestra": args.muestra,
        "repeticiones": args.repeticiones,
        "n_candidatos": len(archivos),
        "n_medidos": len(casos[SERIES_COVER_MAX_WIDTH]),
        "n_fallos": len(set(fallos)),
        "fallos": sorted(set(fallos)),
        "umbrales": {
            "p95_ms": UMBRAL_P95_MS,
            "p95_ms_original_grande": UMBRAL_P95_GRANDE_MS,
            "media_bytes": UMBRAL_MEDIA_BYTES,
            "rss_delta_mb": UMBRAL_RSS_MB,
        },
        "rss_inicial_mb": round(rss_inicial, 1) if rss_inicial is not None else None,
        "rss_final_mb": round(rss_final, 1) if rss_final is not None else None,
        "rss_delta_mb": round(rss_final - rss_inicial, 1) if rss_inicial is not None else None,
        "resumen": resumen,
        "casos": casos,
    }
    _imprimir(informe)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Informe JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
