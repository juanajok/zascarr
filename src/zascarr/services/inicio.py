"""
Inicio (V4): reúne el estado observado y se lo da a la función pura de primeros pasos.

Cada dato tiene UNA fuente y aquí se dice cuál (la regla de la ficha V4: sin contradicciones entre
pantallas):

- archivos registrados / series / huecos / completitud → `services/resumen.py`
- archivos sin clasificar → `ReviewService.count_pending` (sin el tope de 50 de la lista)
- series seguidas → `WishlistService.count_active` (las mismas que lista Deseados)
- adopción → `LibraryAdopter.estado` (marcador explícito de B11, no inferido de que haya filas)
- informe de duplicados → último `ImportRun` con `details.kind == "audit"`
- aviso legal → `services/legal.is_acknowledged`
- fuente de búsqueda → `orchestrator.hay_fuente_de_busqueda` (la misma definición que usa D9)

Solo lee.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ImportRun
from zascarr.services.legal import is_acknowledged
from zascarr.services.library_adopter import LibraryAdopter
from zascarr.services.orchestrator import hay_fuente_de_busqueda
from zascarr.services.primeros_pasos import (
    EstadoInicio,
    InformeDisco,
    PrimerosPasos,
    calcular_primeros_pasos,
)
from zascarr.services.resumen import ResumenBiblioteca, resumen_biblioteca
from zascarr.services.review import ReviewService
from zascarr.services.wishlist import WishlistService


@dataclass(frozen=True)
class VistaInicio:
    resumen: ResumenBiblioteca
    pasos: PrimerosPasos
    informe: InformeDisco | None
    archivos_sin_clasificar: int


async def ultimo_informe(db: AsyncSession) -> InformeDisco | None:
    """Solo las cifras del último informe de duplicados, sin cargar las listas del JSON."""
    fila = (await db.execute(
        select(
            ImportRun.started_at,
            ImportRun.files_scanned,
            ImportRun.details["files_hashed"].astext,
        )
        .where(ImportRun.details["kind"].astext == "audit")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).first()
    if fila is None:
        return None
    fecha, leidos, comparados = fila
    return InformeDisco(
        fecha=fecha,
        archivos_leidos=leidos or 0,
        archivos_comparados=int(comparados or 0),
    )


async def cargar_inicio(db: AsyncSession) -> VistaInicio:
    resumen = await resumen_biblioteca(db)
    sin_clasificar = await ReviewService(db).count_pending()
    seguidas = await WishlistService(db).count_active()
    adopcion = await LibraryAdopter(db).estado()
    informe = await ultimo_informe(db)
    legal = await is_acknowledged(db)
    pasos = calcular_primeros_pasos(EstadoInicio(
        adopcion=adopcion,
        archivos_registrados=resumen.archivos_registrados,
        archivos_sin_clasificar=sin_clasificar,
        series_seguidas=seguidas,
        informe=informe,
        aviso_legal_aceptado=legal,
        hay_fuente_de_busqueda=hay_fuente_de_busqueda(get_settings()),
    ))
    return VistaInicio(resumen=resumen, pasos=pasos, informe=informe,
                       archivos_sin_clasificar=sin_clasificar)
