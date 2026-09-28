#!/usr/bin/env python3
"""B6 — comando administrativo: previsualizar y escribir `ComicInfo.xml`.

Por defecto **no escribe nada**: imprime el plan campo a campo que resulta de la
regla de procedencia (ficha `docs/design/benchmark-B6-comicinfo.md`). Para
aplicarlo hace falta `--apply` de forma explícita.

    # ver qué haría, sin tocar la colección
    python -m zascarr.cli.etiquetar

    # aplicarlo de verdad (el coleccionista lo autoriza)
    python -m zascarr.cli.etiquetar --apply

En la Pi no hay Python en el host: se invoca con `scripts/etiquetar.sh`, que
entra por `docker compose run --rm zascarr ...`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from zascarr.core.comicinfo_write import Accion, CampoPlan
from zascarr.database import async_session_factory, engine
from zascarr.services.tagger import InformeEtiquetado, TaggerService

#: Cómo se lee cada acción en el informe del coleccionista.
ETIQUETA = {
    Accion.CAMBIA: "cambiará",
    Accion.CONSERVA: "se conserva (procedencia desconocida)",
    Accion.YA_COINCIDE: "ya coincide",
    Accion.SIN_DATO: "sin dato (no se inventa)",
    Accion.BLOQUEADO: "bloqueado (locked_fields)",
}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zascarr-etiquetar",
        description="Escribe ComicInfo.xml dentro de los CBZ de la biblioteca.",
    )
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--apply", action="store_true",
                      help="escribe de verdad (por defecto solo simula)")
    modo.add_argument("--dryrun", action="store_true",
                      help="no escribe nada, ni en el CBZ ni en la BD (es el "
                           "comportamiento por defecto): tampoco guarda marcas "
                           "de revisión")
    p.add_argument("--limit", type=int, default=20,
                   help="cuántos CBZ sin revisar mirar (por defecto 20; 0 = todos)")
    p.add_argument("--file-id", action="append", dest="file_ids", metavar="UUID",
                   help="etiquetar solo estos ficheros (repetible; ignora --limit)")
    p.add_argument("--no-overwrite", action="store_true",
                   help="solo rellenar campos vacíos, nunca actualizar los existentes")
    p.add_argument("--reconciliar-todo", action="store_true",
                   help="revisarlo todo otra vez, aunque ya esté revisado, y "
                        "recalcular sha256/tamaño aunque el fichero no haya cambiado")
    p.add_argument("--json", action="store_true", help="informe legible por máquina")
    return p


def _campo_json(c: CampoPlan) -> dict:
    return {"tag": c.tag, "accion": c.accion.value, "actual": c.actual, "nuevo": c.nuevo}


def _imprimir_texto(informe: InformeEtiquetado, *, aplicar: bool) -> None:
    modo = ("APLICAR — se reescriben los CBZ" if aplicar
            else "simulación, no se escribe nada")
    print("Plan de etiquetado (ComicInfo.xml)")
    print(f"  modo: {modo}\n")
    for r in informe.resultados:
        print(f"{r.nombre}")
        if r.motivo:
            print(f"  · {r.accion}: {r.motivo}")
        for c in r.campos:
            actual = f"«{c.actual}»" if c.actual else "—"
            nuevo = f"«{c.nuevo}»" if c.nuevo else "—"
            print(f"  {c.tag:<12} {ETIQUETA[c.accion]:<38} {actual} → {nuevo}")
        print()

    if informe.escritos or informe.previstos:
        print("Cambios:")
        for r in informe.resultados:
            cambios = [c for c in r.campos if c.accion is Accion.CAMBIA]
            if cambios:
                campos = ", ".join(f"{c.tag}={c.nuevo}" for c in cambios)
                print(f"  {r.nombre}: {campos}")
        print()

    print(f"Resumen: {informe.resumen()}")
    if informe.ya_revisados:
        print(f"({informe.ya_revisados} ya revisados antes y sin cambios: no gastan cupo; "
              f"repite el comando para seguir avanzando.)")
    if not aplicar:
        print("La simulación no guarda marcas de revisión: la próxima vez volverá "
              "a mostrar los mismos pendientes.")
        if informe.previstos:
            print("Nada se ha escrito. Para aplicarlo: --apply")


def _salida_json(informe: InformeEtiquetado, *, aplicar: bool) -> None:
    print(json.dumps({
        "modo": "apply" if aplicar else "dryrun",
        "resumen": {
            "escritos": informe.escritos, "previstos": informe.previstos,
            "saltados": informe.saltados, "bloqueados": informe.bloqueados,
            "caducados": informe.caducados, "invalidos": informe.invalidos,
            "sin_espacio": informe.sin_espacio,
            "fallos_verificacion": informe.fallos_verificacion,
            "errores": informe.errores, "reconciliados": informe.reconciliados,
            "ya_revisados": informe.ya_revisados,
        },
        "resultados": [
            {
                "file_id": r.file_id, "nombre": r.nombre, "accion": r.accion,
                "motivo": r.motivo, "reconciliado": r.reconciliado,
                "campos": [_campo_json(c) for c in r.campos],
            }
            for r in informe.resultados
        ],
    }, ensure_ascii=False, indent=2))


async def _ejecutar(args: argparse.Namespace) -> int:
    aplicar = args.apply
    async with async_session_factory() as session:
        servicio = TaggerService(session)
        informe = await servicio.run(
            limit=args.limit,
            dry_run=not aplicar,
            solo_rellenar=args.no_overwrite,
            file_ids=args.file_ids,
            reconciliar_todo=args.reconciliar_todo,
        )
        if aplicar:
            # Un solo commit al final: si falla, el CBZ ya está reescrito
            # (os.replace es atómico) y la siguiente pasada reconcilia el hash
            # sin volver a escribir el XML.
            await session.commit()

    if args.json:
        _salida_json(informe, aplicar=aplicar)
    else:
        _imprimir_texto(informe, aplicar=aplicar)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    async def _main() -> int:
        try:
            return await _ejecutar(args)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
