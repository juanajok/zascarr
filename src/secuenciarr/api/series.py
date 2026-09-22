"""Router de Series — CRUD + full-text search + missing issues."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from secuenciarr.database import get_db
from secuenciarr.models import Issue, Series

router = APIRouter(prefix="/series", tags=["series"])


@router.get("")
async def list_series(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tradition: str | None = None,
    status: str | None = None,
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Series)
    if tradition:
        query = query.where(Series.tradition == tradition)
    if status:
        query = query.where(Series.status == status)
    if search:
        query = query.where(
            func.to_tsvector("spanish", Series.title).match(search)
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    query = query.order_by(Series.sort_title, Series.start_year)
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = list((await db.execute(query)).scalars().all())
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


@router.get("/{series_id}")
async def get_series(series_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(Series).where(Series.id == series_id).options(selectinload(Series.genres))
    series = (await db.execute(q)).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return series


@router.post("", status_code=201)
async def create_series(data: dict, db: AsyncSession = Depends(get_db)):
    series = Series(**data)
    db.add(series)
    await db.flush()
    await db.refresh(series)
    return series


@router.patch("/{series_id}")
async def update_series(series_id: UUID, data: dict, db: AsyncSession = Depends(get_db)):
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    for field, value in data.items():
        setattr(series, field, value)
    await db.flush()
    return series


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: UUID, db: AsyncSession = Depends(get_db)):
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    await db.delete(series)


def compute_missing_issues(total_issues: int | None, sort_orders: set[float]) -> list[int]:
    """Números 1..total_issues sin Issue cuyo sort_order sea EXACTAMENTE
    ese entero. Compartida entre la API y la ficha de serie (web/series.py)
    para que el fix de C2 viva en un solo sitio.

    C2 (peer review): antes se truncaba sort_order con int(), así que un
    Annual/especial con sort_order=1.5 "cubría" el hueco del nº 1 aunque
    ese número no existiera de verdad — un truncado no es una presencia.
    """
    if not total_issues:
        return []
    return [i for i in range(1, total_issues + 1) if float(i) not in sort_orders]


async def _fetch_sort_orders(db: AsyncSession, series_id: UUID) -> set[float]:
    return {
        r for r in (await db.execute(
            select(Issue.sort_order).where(Issue.series_id == series_id, Issue.sort_order.is_not(None))
        )).scalars().all()
        if r is not None
    }


@router.get("/{series_id}/missing")
async def get_missing_issues(series_id: UUID, db: AsyncSession = Depends(get_db)):
    """Números faltantes respecto a total_issues. Alimenta la wishlist."""
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    if not series.total_issues:
        return []
    sort_orders = await _fetch_sort_orders(db, series_id)
    return compute_missing_issues(series.total_issues, sort_orders)
