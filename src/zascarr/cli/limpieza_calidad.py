#!/usr/bin/env python3
"""Lotes L2/L3/L4 del informe de calidad: vista previa y aplicación a demanda.

    python -m zascarr.cli.limpieza_calidad l3            # solo cuenta y muestra
    python -m zascarr.cli.limpieza_calidad l3 --apply    # aplica hasta 100

- `l3`: devuelve a «Por revisar» los pendientes con `match_status` distinto de
  `unsorted` (D6a).
- `l2`: retira vínculos a series borradas y los conserva en el historial (A1a).
- `l4`: retira nombres de `locked_fields` que no existen en el modelo (F5).

Por defecto no escribe. No toca identidad, número, formato ni archivos; solo el
campo del lote. El `commit` lo hace este comando al final de la tanda.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from zascarr.database import async_session_factory, engine
from zascarr.services.limpieza_calidad import LOTE, LOTES, MUESTRA, LimpiezaCalidad


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zascarr-limpieza-calidad",
        description="Lotes L2/L3/L4 de calidad: vista previa por defecto.",
    )
    p.add_argument(
        "lote", choices=LOTES,
        help="l3 (pendientes), l2 (vínculos) o l4 (locked_fields)",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="aplica una tanda (por defecto solo cuenta y muestra)",
    )
    p.add_argument(
        "--limite", type=int, default=LOTE,
        help=f"filas por tanda (por defecto {LOTE})",
    )
    p.add_argument(
        "--muestra", type=int, default=MUESTRA,
        help=f"filas de la vista previa (por defecto {MUESTRA})",
    )
    p.add_argument("--json", action="store_true", help="resultado legible por máquina")
    return p


async def _ejecutar(args: argparse.Namespace) -> tuple[dict, int]:
    async with async_session_factory() as session:
        servicio = LimpiezaCalidad(session)
        if not args.apply:
            vista = await servicio.previsualizar(args.lote, limite=args.muestra)
            return {"modo": "vista_previa", "lote": vista.lote, "pendientes": vista.pendientes,
                    "muestra": [asdict(m) for m in vista.muestra]}, 0
        r = await servicio.aplicar(args.lote, limite=args.limite)
        await session.commit()
        return {"modo": "aplicado", "lote": r.lote, "limite": r.limite,
                "pendientes_antes": r.pendientes_antes, "leidas": r.leidas,
                "cambiadas": r.cambiadas, "pendientes_despues": r.pendientes_despues}, 0


def _texto(res: dict) -> str:
    if res["modo"] == "vista_previa":
        lineas = [f"Lote {res['lote']}: {res['pendientes']} pendientes. No se ha escrito nada. "
                  "Para aplicar: --apply [--limite N]."]
        for m in res["muestra"]:
            lineas.append(f"· {m['id']}  {json.dumps(m['detalle'], ensure_ascii=False)}")
        return "\n".join(lineas)
    return (f"Lote {res['lote']}: {res['cambiadas']} filas cambiadas de {res['leidas']} leídas. "
            f"Pendientes: {res['pendientes_antes']} antes → {res['pendientes_despues']} después.")


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
