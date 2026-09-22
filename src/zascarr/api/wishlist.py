"""Router de Wishlist — cola de deseos tipo Sonarr."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import Wishlist, WishlistStatus
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.wishlist import WishlistService

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


class WishlistCreate(BaseModel):
    series_id: UUID | None = None
    issue_id: UUID | None = None
    priority: int = 5
    notes: str | None = None


class WishlistUpdate(BaseModel):
    priority: int | None = None
    notes: str | None = None
    status: WishlistStatus | None = None


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


@router.post("", status_code=201, dependencies=[Depends(require_legal_acknowledgment)])
async def add_to_wishlist(data: WishlistCreate, db: AsyncSession = Depends(get_db)):
    try:
        item = await WishlistService(db).add(
            series_id=data.series_id, issue_id=data.issue_id,
            priority=data.priority, notes=data.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.refresh(item)  # trae added_at (server_default) para la respuesta
    return item


@router.patch("/{item_id}")
async def update_wishlist_item(item_id: UUID, data: WishlistUpdate, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(Wishlist).where(Wishlist.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.flush()
    return item


@router.delete("/{item_id}", status_code=204)
async def remove_from_wishlist(item_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        await WishlistService(db).remove(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/search", dependencies=[Depends(require_legal_acknowledgment)])
async def trigger_search(item_id: UUID, db: AsyncSession = Depends(get_db)):
    """Reintento/búsqueda manual inmediata: salta el cooldown."""
    try:
        return await WishlistService(db).retry(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
