#!/usr/bin/env python3
"""L1/F4a (#1186) — limpiar el HTML de las sinopsis ya guardadas, a demanda.

Por defecto **no escribe nada**: cuenta las sinopsis con HTML y enseña una
muestra de antes/después. Para ejecutar un lote hace falta `--apply`:

    # vista previa (solo lectura)
    python -m zascarr.cli.limpiar_sinopsis

    # un lote de hasta 100 filas
    python -m zascarr.cli.limpiar_sinopsis --apply --limite 100

Garantías: no toca `locked_fields` con `synopsis` ni `metadata_source='manual'`;
guarda el texto original en `issues.metadata["sinopsis_original"]` (si ya está,
no lo pisa) y no cambia identidad, número, formato ni archivos. La limpieza es
idempotente: una segunda pasada no reescribe lo que ya es texto plano.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from zascarr.database import async_session_factory, engine
from zascarr.services.limpiar_sinopsis import LOTE, MUESTRA, LimpiadorSinopsis


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zascarr-limpiar-sinopsis",
        description="Limpia el HTML de las sinopsis guardadas (vista previa por defecto).",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="ejecuta un lote de verdad (por defecto solo cuenta y muestra)",
    )
    p.add_argument(
        "--limite", type=int, default=LOTE,
        help=f"filas por lote al aplicar (por defecto {LOTE})",
    )
    p.add_argument(
        "--muestra", type=int, default=MUESTRA,
        help=f"filas de la vista previa (por defecto {MUESTRA})",
    )
    p.add_argument("--json", action="store_true", help="resultado legible por máquina")
    return p


async def _ejecutar(args: argparse.Namespace) -> tuple[dict, int]:
    async with async_session_factory() as session:
        servicio = LimpiadorSinopsis(session)
        if not args.apply:
            vista = await servicio.previsualizar(limite=args.muestra)
            return {
                "modo": "vista_previa",
                "pendientes": vista.pendientes,
                "protegidas": vista.protegidas,
                "manuales": vista.manuales,
                "muestra": [asdict(m) for m in vista.muestra],
            }, 0
        resultado = await servicio.aplicar(limite=args.limite)
        await session.commit()
        return {
            "modo": "aplicado",
            "limite": resultado.limite,
            "pendientes_antes": resultado.pendientes_antes,
            "leidas": resultado.leidas,
            "limpiadas": resultado.limpiadas,
            "sin_cambio": resultado.sin_cambio,
            "cambiadas": resultado.cambiadas,
            "pendientes_despues": resultado.pendientes_despues,
        }, 0


def _corto(texto: str, largo: int = 160) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _texto(res: dict) -> str:
    if res["modo"] == "vista_previa":
        lineas = [
            f"Sinopsis con HTML pendientes: {res['pendientes']}. "
            f"Protegidas: {res['protegidas']}; manuales: {res['manuales']}. "
            "No se ha escrito nada. Para limpiar un lote: --apply [--limite N].",
        ]
        for m in res["muestra"]:
            lineas.append(f"· {m['issue_id']}  {_corto(m['antes'])}  →  {_corto(m['despues'])}")
        return "\n".join(lineas)
    return (
        f"Lote de hasta {res['limite']}: leídas {res['leidas']}, "
        f"limpiadas {res['limpiadas']}, sin cambio {res['sin_cambio']}, "
        f"cambiadas por otro proceso {res['cambiadas']}. "
        f"Pendientes: {res['pendientes_antes']} antes → {res['pendientes_despues']} después."
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limite < 1 or args.muestra < 0:
        print("--limite debe ser al menos 1 y --muestra no puede ser negativo", file=sys.stderr)
        return 2

    async def _main() -> int:
        try:
            res, codigo = await _ejecutar(args)
        finally:
            await engine.dispose()
        print(json.dumps(res, ensure_ascii=False) if args.json else _texto(res))
        return codigo

    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
