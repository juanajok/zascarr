# ruff: noqa: E501
"""Router de revisión (rebanada 1): `GET /api/revision/carpetas`, solo lectura.

Sin escrituras, sin disco, sin red y sin acciones. Exige sesión o Basic como el resto de `/api/*` (lo hace
`AuthMiddleware`); no lleva dependencia legal porque no es una acción de riesgo (CLAUDE.md §5.2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.revision_carpetas import (
    LIMITE_MAXIMO,
    LIMITE_POR_DEFECTO,
    RespuestaCarpetas,
    RevisionCarpetas,
)

router = APIRouter(prefix="/revision", tags=["revision"])


@router.get("/carpetas", response_model=RespuestaCarpetas)
async def carpetas_pendientes(
    response: Response,
    limite: int = Query(default=LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    desplazamiento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RespuestaCarpetas:
    """Lo pendiente agrupado por su carpeta contextual, con la serie sugerida y las señales que la contradicen."""
    # Los datos cambian con cada registro o asignación: nada de cachés intermedias.
    response.headers["Cache-Control"] = "no-store"
    return await RevisionCarpetas(db).carpetas(limite=limite, desplazamiento=desplazamiento)
