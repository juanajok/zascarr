"""Igual que evaluar.py pero con el PIPELINE REAL: capa 0 (ComicInfo del
CBZ) cuando existe, y naming.py cuando no. Es lo que ZascArr extrae de
verdad, no solo lo que saca del nombre."""
from __future__ import annotations
import collections, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from etiquetas import ETIQUETAS

from zascarr.core.importer_triage import triage
from zascarr.core.matcher import normalize_title
from zascarr.utils.naming import parse_comic_filename

PESO = {"A_singleton": 6, "B_pequena": 45, "D_grande": 711}

def main() -> None:
    filas = list(csv.DictReader(open("muestra81.csv")))
    por_estrato = collections.defaultdict(collections.Counter)
    via = collections.Counter()
    for f in filas:
        ruta = Path(f["ruta"]); nombre = ruta.name
        serie_real, num_real, _tipo, _ctx = ETIQUETAS[nombre]
        tr = triage(ruta)
        if tr.strong_candidate:          # capa 0: metadata real embebida
            serie, num = tr.comic_info.series, str(tr.comic_info.number)
            via["capa0_comicinfo"] += 1
        else:                            # capa 1: solo el nombre
            r = parse_comic_filename(nombre)
            serie, num = r.series, r.issue_number
            via["capa1_nombre"] += 1

        serie_ok = normalize_title(serie) == normalize_title(serie_real)
        num_ok = num.lower() == num_real.lower()
        if serie_ok and num_ok and num:   v = "ok"
        elif serie_ok and num_ok:         v = "correcto_sin_numero"
        elif not serie_ok and num:        v = "error_serie"
        elif not serie_ok:                v = "serie_mal_sin_numero"
        elif not num:                     v = "numero_perdido"
        else:                             v = "error_numero"
        por_estrato[f["estrato"]][v] += 1

    print(f"Vía usada: {dict(via)}\n")
    print(f"{'estrato':<14}{'n':>4}{'ok':>5}{'clasif':>8}{'veraz':>8}")
    pond = veraz_pond = peso_total = 0.0
    glob = collections.Counter()
    for est in ("A_singleton", "B_pequena", "D_grande"):
        c = por_estrato[est]; n = sum(c.values())
        if not n: continue
        glob.update(c)
        clasif = c["ok"]/n
        veraz = (c["ok"]+c["correcto_sin_numero"])/n
        pond += clasif*PESO[est]; veraz_pond += veraz*PESO[est]; peso_total += PESO[est]
        print(f"{est:<14}{n:>4}{c['ok']:>5}{clasif:>7.0%}{veraz:>8.0%}")
    n = sum(glob.values())
    err = glob["error_serie"]+glob["error_numero"]+glob["serie_mal_sin_numero"]
    print(f"\nPOBLACIONAL (pipeline real, capa 0 + capa 1):")
    print(f"  CLASIFICA SOLO .......... {pond/peso_total:.0%}")
    print(f"  ES VERAZ ................ {veraz_pond/peso_total:.0%}")
    print(f"  errores ................. {err}/{n} = {err/n:.0%}")
    print(f"  número perdido .......... {glob['numero_perdido']}/{n}")
main()
