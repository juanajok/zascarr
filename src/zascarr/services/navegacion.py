"""
Contadores del menú (V3): dos `COUNT` baratos y nada más.

El menú NO consulta la base de datos al renderizarse (`base.html` no tiene contexto de BD): los
números llegan después, por un fragmento HTMX (`web/navegacion.py`), de modo que una BD lenta o
caída nunca retrasa ni rompe una página. Cada contador usa el MISMO filtro que la lista a la que
enlaza (`ReviewService._condiciones_pendientes`, `WishlistService.count_active`).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.services.review import ReviewService
from zascarr.services.wishlist import WishlistService


@dataclass(frozen=True)
class Contadores:
    pendientes: int
    deseados: int


async def contadores(db: AsyncSession) -> Contadores:
    return Contadores(
        pendientes=await ReviewService(db).count_pending(),
        deseados=await WishlistService(db).count_active(),
    )
