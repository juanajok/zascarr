#!/usr/bin/env python3
"""#307 (D5) — comando administrativo: guardar el formato REAL (por contenido) de los `.cbr`/`.cb7` ya registrados.

Es una operación **a demanda**: no la lanza ningún ciclo automático (decisión del PO, 2026-10-23). Por defecto **no escribe nada**: dice cuántas filas
están pendientes. Para ejecutar un lote hace falta `--apply`, de forma explícita:

    # cuántas filas faltan, sin leer ningún fichero
    python -m zascarr.cli.rellenar_formato

    # un lote (por defecto 100 filas, elegidas al azar entre las pendientes)
    python -m zascarr.cli.rellenar_formato --apply --limite 100

Solo LEE los ficheros (≤ 512 bytes y, si son ZIP, su directorio central) y solo ESCRIBE en `files.metadata`: nunca toca el fichero, no pisa ninguna
clave existente ni pierde otros metadatos. Un fichero ilegible (disco desmontado) queda pendiente y se reintenta en otra ejecución. Código de salida:
0 = terminó el lote; 1 = el lote terminó pero hubo ficheros ilegibles (para que un cron no lo dé por completo).

En la Pi no hay Python en el host: se invoca con `scripts/rellenar-formato.sh`. No lo ejecutes sobre la biblioteca real sin haberlo decidido: mide antes su coste en el USB.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from zascarr.database import async_session_factory, engine
from zascarr.services.importer import LOTE_FORMATO_CONTENIDO, Importer


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zascarr-rellenar-formato", description="Guarda el formato real (por contenido) de los .cbr/.cb7 ya registrados.")
    p.add_argument("--apply", action="store_true", help="ejecuta un lote de verdad (por defecto solo cuenta las filas pendientes)")
    p.add_argument("--limite", type=int, default=LOTE_FORMATO_CONTENIDO, help=f"filas por ejecución (por defecto {LOTE_FORMATO_CONTENIDO})")
    p.add_argument("--json", action="store_true", help="resultado legible por máquina")
    return p


async def _ejecutar(args: argparse.Namespace) -> tuple[dict, int]:
    async with async_session_factory() as session:
        importador = Importer(session)
        if not args.apply:
            pendientes = await importador.contar_pendientes_formato()
            return {"modo": "solo_cuenta", "pendientes": pendientes}, 0
        r = await importador.rellenar_formato_contenido(limite=args.limite)
        await session.commit()
        return {"modo": "aplicado", "limite": r.limite, "pendientes_antes": r.pendientes_antes, "leidas": r.leidas, "rellenadas": r.rellenadas,
                "ilegibles": r.ilegibles, "pendientes_despues": r.pendientes_despues}, (1 if r.ilegibles else 0)


def _texto(res: dict) -> str:
    if res["modo"] == "solo_cuenta":
        return (f"Filas .cbr/.cb7 sin formato real guardado: {res['pendientes']}. No se ha leído ni escrito nada. "
                "Para rellenar un lote: --apply [--limite N].")
    return (f"Lote de hasta {res['limite']} filas: leídas {res['leidas']}, rellenadas {res['rellenadas']}, ilegibles {res['ilegibles']} (siguen pendientes). "
            f"Pendientes: {res['pendientes_antes']} antes → {res['pendientes_despues']} después.")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limite < 1:
        print("--limite debe ser al menos 1", file=sys.stderr)
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
