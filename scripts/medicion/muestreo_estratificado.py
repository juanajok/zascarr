#!/usr/bin/env python3
"""
Muestreo estratificado de la biblioteca para medir el acierto real del parser.

Uso:
    python3 muestreo_estratificado.py /media/WDElements/Tebeos --n 60 --seed 42

Salida:
    - Tabla de estratos por consola (población y muestra por estrato)
    - muestra_bruta.csv con las rutas seleccionadas y columnas vacías
      para que la persona etiquete la verdad de referencia ANTES de mirar
      qué dice el parser (evita sesgo de confirmación).
"""

import argparse
import csv
import random
import unicodedata
from pathlib import Path
from collections import defaultdict

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}
OTROS_CONTENEDORES = {".rar", ".zip"}


def norm(texto: str) -> str:
    """Normaliza el nombre de carpeta para agrupar cohortes:
    minúsculas, sin tildes, sin año entre paréntesis, sin puntuación."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = t.lower().strip()
    for ch in "()[]{}.,-_":
        t = t.replace(ch, " ")
    return " ".join(t.split())


def estrato(n: int) -> str:
    if n == 1:
        return "A_singleton"      # series con 1 solo archivo: máximo riesgo
    if n <= 10:
        return "B_pequena"        # 2-10
    if n <= 50:
        return "C_media"          # 11-50
    return "D_grande"             # >50 (Flash, Death Note, JSA...)


# Reparto de la muestra por estrato (sobremuestreo deliberado del long tail)
CUOTA = {
    "A_singleton": 0.35,   # 35% de la muestra
    "B_pequena":   0.30,
    "C_media":     0.20,
    "D_grande":    0.15,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz", help="Raíz de la biblioteca")
    ap.add_argument("--n", type=int, default=60, help="Tamaño de muestra")
    ap.add_argument("--seed", type=int, default=42, help="Semilla (reproducible)")
    ap.add_argument("--out", default="muestra_bruta.csv")
    args = ap.parse_args()

    raiz = Path(args.raiz)
    if not raiz.is_dir():
        raise SystemExit(f"No existe: {raiz}")

    cohortes: dict[str, list[Path]] = defaultdict(list)
    otros = 0
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in OTROS_CONTENEDORES:
            otros += 1
            continue
        if ext not in COMIC_EXTS:
            continue
        cohortes[norm(p.parent.name)].append(p)

    rnd = random.Random(args.seed)
    estratos: dict[str, list[Path]] = defaultdict(list)
    for nombre, files in cohortes.items():
        estratos[estrato(len(files))].extend(files)

    total = sum(len(v) for v in estratos.values())
    print(f"Población: {total} cómics en {len(cohortes)} cohortes"
          f" (+{otros} contenedores .rar/.zip aparte)\n")
    print(f"{'Estrato':<14}{'Cohortes':>9}{'Archivos':>9}{'% pobl.':>9}{'Cuota':>7}{'Muestra':>9}")

    muestra: list[tuple[Path, str, str]] = []
    for nombre_estrato in ("A_singleton", "B_pequena", "C_media", "D_grande"):
        archivos = estratos.get(nombre_estrato, [])
        if not archivos:
            continue
        n_cohortes = sum(
            1 for files in cohortes.values() if estrato(len(files)) == nombre_estrato
        )
        objetivo = max(1, round(args.n * CUOTA[nombre_estrato]))
        objetivo = min(objetivo, len(archivos))
        sel = rnd.sample(sorted(archivos), objetivo)
        for p in sel:
            cohorte = norm(p.parent.name)
            muestra.append((p, cohorte, nombre_estrato))
        print(f"{nombre_estrato:<14}{n_cohortes:>9}{len(archivos):>9}"
              f"{100*len(archivos)/total:>8.1f}%{CUOTA[nombre_estrato]:>6.0%}"
              f"{objetivo:>9}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ruta", "cohorte", "estrato",
            "serie_real", "numero_real", "tipo_real",  # grapa | tomo | pack | especial | obra_unica
            "parser_serie", "parser_numero", "veredicto",  # ok | error_serie | error_numero | pendiente
        ])
        for p, cohorte, est in muestra:
            w.writerow([str(p), cohorte, est, "", "", "", "", "", ""])

    print(f"\nMuestra escrita en {args.out} ({len(muestra)} filas)")
    print("\nRecordatorio de métricas:")
    print("- Acierto poblacional = suma por estrato de (acierto_estrato × peso_poblacional)")
    print("- Acierto por cohorte = media de aciertos por cohorte (sin ponderar por tamaño)")
    print("- Reporta AMBOS; el segundo vigila el long tail, el primero la experiencia real.")


if __name__ == "__main__":
    main()
