#!/usr/bin/env python3
# ruff: noqa: E501
"""Apoyo del job «Pruebas con Postgres real» de la CI (`.github/workflows/ci.yml`).

    ci_postgres.py esperar            espera a que TEST_DATABASE_URL conteste (y falla si no está definida)
    ci_postgres.py junit FICHERO.xml  falla si el informe no demuestra que las pruebas SE EJECUTARON

Existe porque las pruebas de Postgres se SALTAN solas sin `TEST_DATABASE_URL`: un job que olvidara la
variable (o cuyo servicio no arrancara) quedaría verde sin haber probado nada. Aquí «verde» exige:
la variable definida, el servidor respondiendo, un mínimo de pruebas ejecutadas y **cero** saltadas,
con fallos o con errores. Solo stdlib + asyncpg (ya dependencia de la aplicación).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import xml.etree.ElementTree as ET

#: Suelo de pruebas que deben ejecutarse (hoy 159). Bajarlo es una decisión consciente, no un descuido.
MINIMO_DE_PRUEBAS = 150


def contar(ruta: str) -> dict[str, int]:
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.iter("testsuite"))
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for clave in total:
            total[clave] += int(s.get(clave, 0))
    return total


def comprobar_informe(ruta: str, minimo: int = MINIMO_DE_PRUEBAS) -> list[str]:
    """Motivos por los que el informe NO acredita una ejecución real (vacío = acredita)."""
    c = contar(ruta)
    motivos = []
    if c["tests"] < minimo:
        motivos.append(f"solo {c['tests']} pruebas en el informe (mínimo {minimo})")
    for clave, texto in (("skipped", "saltadas"), ("failures", "con fallos"), ("errors", "con error")):
        if c[clave]:
            motivos.append(f"{c[clave]} pruebas {texto}")
    return motivos


async def _conectar(url: str, intentos: int, pausa: float) -> str | None:
    import asyncpg

    ultimo = None
    for _ in range(intentos):
        try:
            conexion = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"), timeout=5)
            try:
                return await conexion.fetchval("SELECT version()")
            finally:
                await conexion.close()
        except Exception as exc:  # noqa: BLE001 — se reintenta y se informa del último
            ultimo = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(pausa)
    print(f"Postgres no contesta tras {intentos} intentos: {ultimo}", file=sys.stderr)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    esperar = sub.add_parser("esperar")
    esperar.add_argument("--intentos", type=int, default=30)
    esperar.add_argument("--pausa", type=float, default=2.0)
    junit = sub.add_parser("junit")
    junit.add_argument("fichero")
    junit.add_argument("--minimo", type=int, default=MINIMO_DE_PRUEBAS)
    args = ap.parse_args(argv)

    if args.orden == "esperar":
        url = os.environ.get("TEST_DATABASE_URL", "")
        if not url:
            print("TEST_DATABASE_URL no está definida: sin ella las pruebas de Postgres se saltan "
                  "y el job quedaría verde sin probar nada.", file=sys.stderr)
            return 2
        version = asyncio.run(_conectar(url, args.intentos, args.pausa))
        if version is None:
            return 3
        print(version)
        return 0

    motivos = comprobar_informe(args.fichero, args.minimo)
    c = contar(args.fichero)
    print(f"informe: {c}")
    if motivos:
        print("El job NO acredita haber ejecutado las pruebas de Postgres: " + "; ".join(motivos),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
