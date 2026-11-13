"""Reconcilia una guía de lectura con tu colección (SCR3, entrega 2).

Uso manual, con la fuente encendida (Ajustes o variable de entorno de ESTE proceso):

    READING_ORDERS_ENABLED=true python scripts/reconciliar-lecturas.py \\
        --url "https://comicbookreadingorders.com/dc/events/...-reading-order/"
    CONTINUITY_GUIDE_ENABLED=true python scripts/reconciliar-lecturas.py \\
        --fuente continuity_guide --url "https://www.continuityguide.net/planetx"

Crea o actualiza el arco (`story_arcs`) y su orden de lectura
(`story_arc_issues.reading_order`) a partir de las referencias FÁCTICAS de la guía
(serie/número/orden): nunca se guarda ni se muestra la prosa del autor. Sin pantalla
nueva: la guía aparece en «Sagas en orden» (`/ui/arcos`) al terminar.

No toca archivos ni la biblioteca: solo escribe arcos y enlaces de lectura.
"""
from __future__ import annotations

import argparse
import asyncio

from zascarr.database import async_session_factory
from zascarr.services.reading_orders import (
    ContinuityGuideExtractor,
    ReadingOrdersExtractor,
)
from zascarr.services.reconciliacion_lecturas import leer_y_reconciliar
from zascarr.utils.cache_http import CacheHttp

FUENTES = {
    "reading_orders": ReadingOrdersExtractor,
    "continuity_guide": ContinuityGuideExtractor,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcilia una guía de lectura con la colección local de ZascArr.")
    parser.add_argument("--fuente", choices=sorted(FUENTES), default="reading_orders",
                        help="Sitio de la guía (por defecto: reading_orders).")
    parser.add_argument("--url", required=True, help="URL de la guía que se quiere reconciliar.")
    args = parser.parse_args()
    asyncio.run(_reconciliar(args.fuente, args.url))


async def _reconciliar(fuente: str, url: str) -> None:
    extractor = FUENTES[fuente](CacheHttp(async_session_factory))
    try:
        async with async_session_factory() as db:
            resultado = await leer_y_reconciliar(db, extractor, url)
            await db.commit()
    finally:
        await extractor.__aexit__()
    if resultado is None:
        print("La guía no se pudo leer (fuente apagada, robots o HTML irreconocible). "
              "Nada que reconciliar.")
        return
    motivos = ", ".join(f"{motivo}: {n}" for motivo, n in resultado.motivos) or "ninguno"
    estado = "creada" if resultado.creado else "actualizada"
    print(f"Guía «{resultado.titulo}» {estado} en /ui/arcos.")
    print(f"Referencias enlazadas: {resultado.enlazados} · omitidas: "
          f"{resultado.omitidos} ({motivos}).")


if __name__ == "__main__":
    main()
