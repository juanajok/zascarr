"""Estado de la cortesía (§6.2): `GET /api/estado/cortesia`.

Solo lectura: devuelve el snapshot de §6.1 con `Cache-Control: no-store`. No es una ruta exenta de
autenticación (el middleware la protege como el resto de `/api/`) y en arranque degradado responde
503 como cualquier `/api/`. Nunca publica URL, query, claves ni hosts fuera de la allowlist.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from zascarr.config import get_settings
from zascarr.services.cortesia_estado import snapshot_publico

router = APIRouter(tags=["estado"])


@router.get("/estado/cortesia")
async def estado_cortesia() -> JSONResponse:
    return JSONResponse(
        content=snapshot_publico(get_settings()),
        headers={"Cache-Control": "no-store"},
    )
