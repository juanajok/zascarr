"""Muestreo estratificado de la biblioteca para etiquetar parser/matcher.

Genera dos CSV:

- ``muestra_biblioteca_200.csv``: ciego. Solo identidad del archivo, estrato,
  extensión, carpeta y SHA. **No** incluye el vínculo actual ni la salida del
  parser, para que la etiqueta no se contamine con lo que se quiere medir.
- ``muestra_biblioteca_200_contexto.csv``: solo para auditar después. Incluye
  el Issue actual y el SHA; no se entrega a quien etiqueta.

El muestreo es determinista con ``--seed`` y lee la DB en una transacción
READ ONLY. No escribe en la base ni en la biblioteca.

Cuotas para n=200 (se ajustan si una capa no tiene suficientes filas):

- 20 con Issue y anual
- 9 sin Issue y anual (hoy es toda la capa)
- 60 con Issue y normal
- el resto sin Issue y normal

Se sobremuestrean los anuales a propósito: son ~1,6% de la biblioteca pero
concentran fallos de identidad. El informe del muestreo lo deja explícito.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zascarr.utils.naming import ANNUAL_PATTERN  # noqa: E402


@dataclass(frozen=True)
class Fila:
    id: str
    archivo: str
    ruta: str
    extension: str
    con_issue: bool
    anual: bool
    sha256: str | None
    serie_actual: str | None
    numero_actual: str | None
    formato_actual: str | None

    @property
    def estrato(self) -> str:
        return ("con_issue" if self.con_issue else "sin_issue") + (
            "_anual" if self.anual else "_normal")

    @property
    def clave_sha(self) -> str:
        return self.sha256 or f"id:{self.id}"


def _categoria_de_ruta(ruta: str) -> str:
    partes = Path(ruta).parts
    if "library" in partes:
        i = partes.index("library")
        if i + 1 < len(partes):
            return partes[i + 1]
    return Path(ruta).parent.name


def _asignar_cuotas(filas: list[Fila], n: int) -> dict[str, int]:
    por_estrato = Counter(f.estrato for f in filas)
    disponibles = {e: por_estrato.get(e, 0) for e in (
        "con_issue_anual", "sin_issue_anual", "con_issue_normal", "sin_issue_normal")}
    cuotas = {
        "con_issue_anual": min(20, disponibles["con_issue_anual"]),
        "sin_issue_anual": min(9, disponibles["sin_issue_anual"]),
        "con_issue_normal": min(60, disponibles["con_issue_normal"]),
    }
    resto = n - sum(cuotas.values())
    for estrato in ("sin_issue_normal", "con_issue_normal"):
        if resto <= 0:
            break
        cabe = disponibles[estrato] - cuotas.get(estrato, 0)
        cuotas[estrato] = cuotas.get(estrato, 0) + min(resto, cabe)
        resto -= min(resto, cabe)
    if resto:
        raise SystemExit(
            f"No hay suficientes filas para {n}: faltan {resto}. "
            f"Disponibles: {disponibles}")
    return cuotas


def _elegir(filas: list[Fila], cuota: int, *, rng: random.Random,
            usados: set[str]) -> list[Fila]:
    """Aleatorio sin reemplazo, prefiriendo SHA únicos; si no llega, completa
    con copias ya usadas para no romper la cuota."""
    barajadas = list(filas)
    rng.shuffle(barajadas)
    nuevos = [f for f in barajadas if f.clave_sha not in usados]
    viejos = [f for f in barajadas if f.clave_sha in usados]
    elegidos = nuevos[:cuota]
    if len(elegidos) < cuota:
        elegidos.extend(viejos[: cuota - len(elegidos)])
    for f in elegidos:
        usados.add(f.clave_sha)
    return elegidos


async def _leer(db_url: str) -> list[Fila]:
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("BEGIN TRANSACTION READ ONLY")
        rows = await conn.fetch("""
            SELECT f.id, f.file_name, f.file_path, f.sha256_hash,
                   f.issue_id, i.issue_number, i.format::text AS formato,
                   s.title AS serie_actual, s.kind::text AS serie_kind
            FROM files f
            LEFT JOIN issues i ON i.id = f.issue_id
            LEFT JOIN series s ON s.id = i.series_id
            WHERE f.is_missing = false
            ORDER BY f.id
        """)
        filas = []
        for r in rows:
            nombre = r["file_name"]
            anual = (r["serie_kind"] == "annual"
                     or bool(ANNUAL_PATTERN.search(nombre or "")))
            filas.append(Fila(
                id=str(r["id"]), archivo=nombre, ruta=r["file_path"],
                extension=Path(nombre).suffix.lower().lstrip("."),
                con_issue=r["issue_id"] is not None,
                anual=anual, sha256=r["sha256_hash"],
                serie_actual=r["serie_actual"],
                numero_actual=r["issue_number"],
                formato_actual=r["formato"]))
        return filas
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--output", default="muestra_biblioteca_200.csv")
    args = parser.parse_args()
    if not args.db_url:
        raise SystemExit("Falta --db-url o DATABASE_URL")

    filas = asyncio.run(_leer(args.db_url))
    cuotas = _asignar_cuotas(filas, args.n)
    rng = random.Random(args.seed)
    usados: set[str] = set()
    elegidos: list[Fila] = []
    for estrato, cuota in cuotas.items():
        sub = [f for f in filas if f.estrato == estrato]
        elegidos.extend(_elegir(sub, cuota, rng=rng, usados=usados))

    elegidos.sort(key=lambda f: (f.estrato, f.archivo.casefold(), f.id))
    salida = Path(args.output)
    contexto = salida.with_name(salida.stem + "_contexto.csv")
    with salida.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "id", "archivo", "ruta", "extension", "estrato", "categoria_carpeta",
            "sha256", "serie_real", "numero_real", "tipo_real",
            "requiere_contexto", "notas", "etiquetado_por", "fecha_etiqueta",
        ])
        for f in elegidos:
            w.writerow([
                f.id, f.archivo, f.ruta, f.extension, f.estrato,
                _categoria_de_ruta(f.ruta), f.sha256 or "",
                "", "", "", "", "", "", "",
            ])
    with contexto.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "archivo", "estrato", "con_issue",
                    "serie_actual", "numero_actual", "formato_actual", "sha256"])
        for f in elegidos:
            w.writerow([f.id, f.archivo, f.estrato, int(f.con_issue),
                        f.serie_actual or "", f.numero_actual or "",
                        f.formato_actual or "", f.sha256 or ""])

    print(f"Semilla: {args.seed} | filas: {len(elegidos)}/{len(filas)}")
    print("Cuotas:", cuotas)
    print("Estratos:", dict(Counter(f.estrato for f in elegidos)))
    print("Extensiones:", dict(Counter(f.extension for f in elegidos)))
    print("Con Issue:", sum(f.con_issue for f in elegidos),
          "| Sin Issue:", sum(not f.con_issue for f in elegidos))
    repetidos = len(elegidos) - len({f.clave_sha for f in elegidos})
    print(f"SHA repetidos en la muestra: {repetidos}")
    print("Ciego:", salida.resolve())
    print("Contexto:", contexto.resolve())


if __name__ == "__main__":
    main()
