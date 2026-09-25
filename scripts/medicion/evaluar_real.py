"""Evaluación oficial: pipeline REAL (capa 0 ComicInfo cuando existe,
naming.py cuando no) contra la verdad de referencia etiquetada a mano
ANTES de ejecutar nada (etiquetas.py).

Reporta CUATRO cosas, no una, porque mezclarlas fue el error de la
primera versión de este script:
  - clasifica / veraz, sobre RUTAS (como si cada fichero fuera
    independiente — infla el N si hay copias duplicadas)
  - clasifica / veraz, sobre CONTENIDO ÚNICO (SHA256; un par
    "archivo.cbr"/"archivo(1).cbr" idéntico cuenta UNA vez)
  - consistencia entre gemelos de contenido idéntico (¿el parser da el
    MISMO resultado para las dos rutas? Si no, es un bug de
    determinismo — RF-20 — no un fallo de acierto)
  - vía usada (capa 0 vs capa 1), para saber cuánto pesa cada una

Escribe además `muestra81_etiquetada.csv`, autocontenido — sin esto,
auditar la medición exige cruzar dos ficheros (el CSV vacío + este
etiquetas.py), que es precisamente lo que se señaló como problema.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from etiquetas import ETIQUETAS  # noqa: E402

from zascarr.core.cohort import detectar_ordenes_de_lectura, quitar_prefijo_de_cohorte
from zascarr.core.importer_triage import triage
from zascarr.core.matcher import normalize_title
from zascarr.utils.naming import parse_comic_filename

PESO = {"A_singleton": 6, "B_pequena": 45, "D_grande": 711}
RAIZ_BIBLIOTECA = Path("/mnt/Datos/Descargas/Tebeos")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def veredicto(serie_real: str, num_real: str, serie_p: str, num_p: str) -> str:
    serie_ok = normalize_title(serie_p) == normalize_title(serie_real)
    num_ok = num_p.lower() == num_real.lower()
    if serie_ok and num_ok and num_p:
        return "ok"
    if serie_ok and num_ok:
        return "correcto_sin_numero"
    if not serie_ok and num_p:
        return "error_serie"
    if not serie_ok:
        return "serie_mal_sin_numero"
    if not num_p:
        return "numero_perdido"
    return "error_numero"


def _ponderado(filas: list[dict]) -> tuple[float, float]:
    pond = veraz_pond = peso_total = 0.0
    for est in ("A_singleton", "B_pequena", "D_grande"):
        sub = [f for f in filas if f["estrato"] == est]
        n = len(sub)
        if not n:
            continue
        c = collections.Counter(f["veredicto"] for f in sub)
        clasif = c["ok"] / n
        veraz = (c["ok"] + c["correcto_sin_numero"]) / n
        peso = PESO[est]
        pond += clasif * peso
        veraz_pond += veraz * peso
        peso_total += peso
    return pond / peso_total, veraz_pond / peso_total


def main() -> None:
    muestra_csv = Path(__file__).parent / "muestra_bruta.csv"
    filas_in = list(csv.DictReader(open(muestra_csv))) if muestra_csv.exists() else []
    if not filas_in:
        raise SystemExit(
            "Falta muestra_bruta.csv (salida de muestreo_estratificado.py). "
            "Genera una muestra nueva antes de evaluar."
        )

    # Cohortes calculadas sobre la POBLACIÓN COMPLETA, no solo la
    # muestra — es lo que haría un ciclo real de Importer/LibraryAdopter
    # (pistas sobre la foto fija de TODOS los archivos del ciclo).
    todos_los_nombres = [p.name for p in RAIZ_BIBLIOTECA.rglob("*") if p.is_file()]
    pistas = detectar_ordenes_de_lectura(todos_los_nombres)

    via = collections.Counter()
    filas = []
    for f in filas_in:
        ruta = Path(f["ruta"])
        nombre = ruta.name
        serie_real, num_real, tipo_real, ctx = ETIQUETAS[nombre]
        tr = triage(ruta)
        if tr.strong_candidate:
            serie, num = tr.comic_info.series, str(tr.comic_info.number)
            via["capa0_comicinfo"] += 1
        else:
            pista = pistas.get(nombre)
            nombre_a_parsear = quitar_prefijo_de_cohorte(nombre, pista) if pista else nombre
            r = parse_comic_filename(nombre_a_parsear)
            serie, num = r.series, r.issue_number
            via["capa1_cohorte" if pista and nombre_a_parsear != nombre else "capa1_nombre"] += 1

        filas.append({
            "ruta": f["ruta"], "cohorte": f["cohorte"], "estrato": f["estrato"],
            "serie_real": serie_real, "numero_real": num_real, "tipo_real": tipo_real,
            "requiere_contexto": ctx,
            "parser_serie": serie, "parser_numero": num,
            "veredicto": veredicto(serie_real, num_real, serie, num),
            "sha256": sha256(ruta)[:16],
        })

    with open(Path(__file__).parent / "muestra81_etiquetada.csv", "w",
              newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    print(f"Vía usada: {dict(via)}\n")

    # ── Sobre rutas (infla N si hay gemelos) ─────────────────────────
    clasif_rutas, veraz_rutas = _ponderado(filas)
    print(f"SOBRE RUTAS (n={len(filas)}, incluye copias duplicadas):")
    print(f"  clasifica solo ... {clasif_rutas:.0%}   veraz ... {veraz_rutas:.0%}")

    # ── Contenido único + consistencia entre gemelos ─────────────────
    por_hash: dict[str, list[dict]] = collections.defaultdict(list)
    for f in filas:
        por_hash[f["sha256"]].append(f)
    pares = {h: v for h, v in por_hash.items() if len(v) > 1}
    divergentes = [(h, v) for h, v in pares.items()
                   if len({(x["parser_serie"], x["parser_numero"]) for x in v}) > 1]

    vistos: set[str] = set()
    unicos = []
    for f in filas:
        if f["sha256"] in vistos:
            continue
        vistos.add(f["sha256"])
        unicos.append(f)

    clasif_u, veraz_u = _ponderado(unicos)
    print(f"\nSOBRE CONTENIDO ÚNICO (n={len(unicos)}, dedup por SHA256 — "
          f"{len(filas) - len(unicos)} eran copias del mismo archivo):")
    print(f"  clasifica solo ... {clasif_u:.0%}   veraz ... {veraz_u:.0%}"
          f"   [CIFRA OFICIAL]")

    print(f"\nCONSISTENCIA entre gemelos ({len(pares)} pares por SHA256, "
          f"RF-20 determinismo): {len(pares) - len(divergentes)} idénticos, "
          f"{len(divergentes)} divergentes")
    for h, v in divergentes:
        for x in v:
            print(f"  !! {Path(x['ruta']).name[:55]!r} -> "
                  f"{x['parser_serie']!r} #{x['parser_numero']!r}")

    ctx = [f for f in unicos if f["requiere_contexto"]]  # bool en memoria; el CSV en disco lo guarda como texto
    fallos_ctx = [f for f in ctx if f["veredicto"] not in ("ok", "correcto_sin_numero")]
    print(f"\nTECHO del parsing por nombre: {len(ctx)} archivos (contenido único) "
          f"cuya respuesta no está en el nombre; fallan {len(fallos_ctx)}")


main()
