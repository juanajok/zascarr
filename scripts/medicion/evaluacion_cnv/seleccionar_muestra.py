#!/usr/bin/env python3
"""Selecciona y COPIA una muestra reproducible de CBR registrados (BL-CNV0).

Regla fija, sin elección a mano: 4 sólidos (mayor <=300 MB y cuantiles), 4 RAR5,
2 ZIP disfrazados, hasta 2 dañados y 1 anidado/multivolumen si el censo los encuentra,
y el resto típicos RAR4/RAR5 de 1-150 MB en orden de sha256(ruta). Copia solo; no toca
el original. Escribe `muestras.tsv` con id, ruta relativa, sha256 y motivo.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

BASE = Path("/home/pi/eval-cnv")
ROOT = Path("/media/WDElements/Tebeos")
LIMITE = 300 * 1024 * 1024


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _leer_cabeceras() -> dict[str, dict]:
    d: dict[str, dict] = {}
    for linea in (BASE / "censo-cabeceras.tsv").read_text(encoding="utf-8").splitlines():
        f = linea.split("\t")
        if len(f) < 5:
            continue
        rel, size, fmt, sol, cif = f[:5]
        try:
            n = int(size)
        except ValueError:
            n = -1
        d[rel] = {"size": n, "fmt": fmt, "solido": sol == "True", "cifrado": cif}
    return d


def _leer_lsar() -> dict[str, dict]:
    d: dict[str, dict] = {}
    p = BASE / "salida/censo-lsar.tsv"
    if not p.exists():
        return d
    for linea in p.read_text(encoding="utf-8").splitlines():
        f = linea.split("\t")
        if len(f) < 6:
            continue
        rel, ls, ent, ani, vol, mot = f[:6]
        d[rel] = {"lsar": ls, "entradas": int(ent) if ent.isdigit() else 0,
                  "anidado": ani == "1", "volumen": vol == "1", "motivo": mot}
    return d


def _orden(rel: str) -> str:
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()


def main() -> int:
    cab = _leer_cabeceras()
    ls = _leer_lsar()
    elegidos: list[tuple[str, str, str]] = []  # rel, tipo, motivo
    vistos: set[str] = set()

    def add(rel: str, tipo: str, motivo: str) -> None:
        if rel in vistos or rel not in cab or cab[rel]["size"] < 0:
            return
        vistos.add(rel)
        elegidos.append((rel, tipo, motivo))

    solidos = sorted((r for r in cab if cab[r]["solido"] and cab[r]["size"] <= LIMITE),
                     key=lambda r: (cab[r]["size"], r))
    if solidos:
        for idx, motivo in [(-1, "sólido mayor <=300 MB"), (len(solidos)//2, "sólido mediano"),
                            (len(solidos)//4, "sólido cuartil"), (0, "sólido pequeño")]:
            if -len(solidos) <= idx < len(solidos):
                add(solidos[idx], "rar", motivo)

    rar5 = sorted((r for r in cab if cab[r]["fmt"] == "RAR5" and cab[r]["size"] <= LIMITE),
                  key=lambda r: (cab[r]["size"], r))
    for idx, motivo in [(-1, "RAR5 mayor"), (len(rar5)//2, "RAR5 mediano"),
                        (len(rar5)//4, "RAR5 cuartil"), (0, "RAR5 pequeño")]:
        if rar5 and -len(rar5) <= idx < len(rar5):
            add(rar5[idx], "rar", motivo)

    zipf = sorted((r for r in cab if cab[r]["fmt"] == "ZIP"), key=_orden)
    for r in zipf[:2]:
        add(r, "zip", "ZIP disfrazado")

    danados = sorted((r for r in ls if ls[r]["lsar"] != "ok"), key=_orden)
    for r in danados[:2]:
        add(r, "rar", "lsar no lista (" + (ls[r]["motivo"] or ls[r]["lsar"]) + ")")
    for campo, motivo in [("anidado", "archivo anidado"), ("volumen", "volumen múltiple")]:
        for r in sorted((r for r in ls if ls[r][campo]), key=_orden)[:1]:
            add(r, "rar", motivo)

    tipicos = sorted((r for r in cab if cab[r]["fmt"] in ("RAR4", "RAR5")
                      and 1 << 20 <= cab[r]["size"] <= 150 << 20), key=_orden)
    for r in tipicos:
        if len(elegidos) >= 26:
            break
        add(r, "rar", "típico determinista")

    dest = BASE / "muestras"
    dest.mkdir(parents=True, exist_ok=True)
    for p in dest.glob("m*"):
        if p.is_file():
            p.unlink()
    salida = []
    for i, (rel, tipo, motivo) in enumerate(elegidos, 1):
        sid = f"m{i:02d}"
        origen = ROOT / rel
        destino = dest / sid
        h1 = _sha(origen)
        shutil.copyfile(origen, destino)
        h2 = _sha(destino)
        if h1 != h2:
            raise SystemExit(f"hash distinto en {sid}")
        destino.chmod(0o444)
        salida.append("\t".join((sid, rel, h1, str(cab[rel]["size"]), tipo, motivo)))
    (BASE / "salida/muestras.tsv").write_text("\n".join(salida) + "\n", encoding="utf-8")
    print(f"muestras={len(salida)}")
    from collections import Counter
    print("tipos=" + repr(Counter(t for _, t, _ in elegidos)))
    print("motivos=" + repr(Counter(m for _, _, m in elegidos)))
    print("bytes=" + str(sum(cab[r]["size"] for r, _, _ in elegidos)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
