"""Router de Wishlist — cola de deseos tipo Sonarr."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.database import get_db
from secuenciarr.models import Wishlist, WishlistStatus

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.get("")
async def list_wishlist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: WishlistStatus | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Wishlist)
    if status:
        query = query.where(Wishlist.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    query = query.order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = list((await db.execute(query)).scalars().all())
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


@router.post("", status_code=201)
async def add_to_wishlist(data: dict, db: AsyncSession = Depends(get_db)):
    if not data.get("series_id") and not data.get("issue_id"):
        raise HTTPException(status_code=422, detail="Indica series_id o issue_id.")
    item = Wishlist(**data)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


@router.patch("/{item_id}")
async def update_wishlist_item(item_id: UUID, data: dict, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(Wishlist).where(Wishlist.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    for field, value in data.items():
        setattr(item, field, value)
    await db.flush()
    return item


@router.delete("/{item_id}", status_code=204)
async def remove_from_wishlist(item_id: UUID, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(Wishlist).where(Wishlist.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    await db.delete(item)


@router.post("/{item_id}/search")
async def trigger_search(item_id: UUID, db: AsyncSession = Depends(get_db)):
    """Lanza búsqueda manual inmediata."""
    item = (await db.execute(select(Wishlist).where(Wishlist.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    item.status = WishlistStatus.SEARCHING
    item.last_searched_at = datetime.now(timezone.utc)
    await db.flush()
    return item
