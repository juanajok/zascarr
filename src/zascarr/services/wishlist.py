"""
WishlistService — alta/baja/búsqueda/reintento de la lista de deseos (D1).

Fuente única de verdad para tanto la API JSON (`api/wishlist.py`) como la
UI HTMX (`web/wishlist.py`) — evita que la lógica de "qué campos son
válidos al crear/actualizar" viva duplicada en dos routers, y de paso
cierra M1 (mass assignment): antes `api/wishlist.py` hacía
`Wishlist(**data)` con el body crudo de la petición.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Series, Wishlist, WishlistStatus


class WishlistService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_series(self, query: str, limit: int = 20) -> list[Series]:
        """Búsqueda manual para elegir qué añadir — mismo criterio simple
        (ilike parcial) que ReviewService.search_series (B2); no se
        comparte código entre ambas por ser 4 líneas sin relación real
        entre features."""
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(Series)
            .where(Series.title.ilike(f"%{query}%"))
            .order_by(Series.title)
            .limit(limit)
        )).scalars().all())

    async def add(self, series_id: UUID | None = None, issue_id: UUID | None = None,
                   priority: int = 5, notes: str | None = None) -> Wishlist:
        if not series_id and not issue_id:
            raise ValueError("Indica series_id o issue_id.")
        item = Wishlist(series_id=series_id, issue_id=issue_id, priority=priority, notes=notes)
        self.db.add(item)
        await self.db.flush()
        return item

    async def remove(self, item_id: UUID) -> None:
        item = await self.db.get(Wishlist, item_id)
        if not item:
            raise ValueError("Item no encontrado")
        await self.db.delete(item)

    async def retry(self, item_id: UUID) -> Wishlist:
        """Reintento manual desde la UI: salta el cooldown de
        process_wishlist limpiando last_searched_at."""
        item = await self.db.get(Wishlist, item_id)
        if not item:
            raise ValueError("Item no encontrado")
        item.status = WishlistStatus.WANTED
        item.last_searched_at = None
        await self.db.flush()
        return item
