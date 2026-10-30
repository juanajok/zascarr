"""GET /api/operaciones — inventario de solo lectura (#123b)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.operaciones import resumen_operaciones

router = APIRouter(prefix="/operaciones", tags=["operaciones"])


@router.get("")
async def operaciones(db: AsyncSession = Depends(get_db)) -> dict:
    return await resumen_operaciones(db)
