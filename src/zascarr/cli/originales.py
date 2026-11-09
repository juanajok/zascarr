"""CLI de mantenimiento de la conversión (#478): reconciliar el diario y vaciar la cuarentena."""
from __future__ import annotations

import argparse
import asyncio

from zascarr.config import get_settings
from zascarr.database import async_session_factory
from zascarr.services.conversion import ConversionDeArchivo


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zascarr-originales",
        description="Reconcilia conversiones interrumpidas y vacía originales apartados.")
    p.add_argument("accion", choices=("reconciliar", "vaciar"))
    p.add_argument("--lote", type=int, default=50, help="originales a borrar por tanda (vaciar)")
    return p


async def _ejecutar(args) -> int:
    async with async_session_factory() as session:
        servicio = ConversionDeArchivo(session, secret=get_settings().secret_key)
        if args.accion == "reconciliar":
            print(f"Conversiones reconciliadas: {await servicio.reconciliar_diario()}")
        else:
            print(f"Originales borrados: {servicio.vaciar_originales(args.lote)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_ejecutar(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
