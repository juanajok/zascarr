# ruff: noqa: E501
"""Router de revisión: `GET /api/revision/carpetas` (rebanada 1) y `POST /api/revision/descubrir` (2a).

Ninguno escribe ni ofrece acciones. `carpetas` no usa disco ni red. `descubrir` es el ÚNICO que usa la red, y
solo cuando se llama (a petición: nunca al abrir un grupo). Exigen sesión o Basic como el resto de `/api/*` (lo
hace `AuthMiddleware`); no llevan dependencia legal porque no son acciones de riesgo (CLAUDE.md §5.2).
"""
from __future__ import annotations

import asyncio
import math
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.descubrimiento_grupo import (
    ConsultaVaciaError,
    DescubrimientoDeGrupo,
    GrupoNoEncontradoError,
    RespuestaDescubrir,
)
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


# ── 2a: descubrimiento desde un grupo ─────────────────────────────────────────────────────────

#: Separación mínima entre dos búsquedas (desde que termina una hasta que empieza la siguiente). El límite de
#: cortesía de cada fuente vive en la INSTANCIA del cliente y cada búsqueda crea clientes nuevos, así que dos
#: búsquedas seguidas llegarían al sitio sin espera entre ellas. Una sola ejecución por proceso (`--workers 1`).
MIN_INTERVALO_S = 3.0
_BUSQUEDA_EN_CURSO = asyncio.Lock()
_fin_de_la_ultima = 0.0


class PeticionDescubrir(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(..., min_length=1, max_length=1000)
    consulta: str | None = Field(default=None, max_length=200)


def reiniciar_ritmo_para_pruebas() -> None:
    global _fin_de_la_ultima
    _fin_de_la_ultima = 0.0


def _demasiado_pronto(detalle: str, espera: float) -> HTTPException:
    return HTTPException(status_code=429, detail=detalle,
                         headers={"Retry-After": str(max(1, math.ceil(espera)))})


@router.post("/descubrir", response_model=RespuestaDescubrir)
async def descubrir(
    peticion: PeticionDescubrir, response: Response, db: AsyncSession = Depends(get_db),
) -> RespuestaDescubrir:
    """Busca en las fuentes DESDE un grupo de la superficie de revisión. No escribe nada, no elige ni recomienda
    ninguna candidata y no crea series: cada candidata lleva un token firmado para los pasos siguientes."""
    response.headers["Cache-Control"] = "no-store"
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=503, detail="El servidor no tiene clave para firmar; reinícialo.")
    global _fin_de_la_ultima
    if _BUSQUEDA_EN_CURSO.locked():
        raise _demasiado_pronto("Ya hay una búsqueda en curso: espera a que termine.", MIN_INTERVALO_S)
    espera = _fin_de_la_ultima + MIN_INTERVALO_S - time.monotonic()
    if _fin_de_la_ultima and espera > 0:
        raise _demasiado_pronto("Espera unos segundos antes de buscar de nuevo: las fuentes piden calma.", espera)
    async with _BUSQUEDA_EN_CURSO:
        try:
            respuesta = await DescubrimientoDeGrupo(db, secret=secret).descubrir(
                peticion.clave, peticion.consulta)
        except GrupoNoEncontradoError:
            # Sin red de por medio: no consume el espaciado entre búsquedas.
            raise HTTPException(status_code=404, detail="No hay registros pendientes en esa carpeta.") from None
        except ConsultaVaciaError:
            raise HTTPException(status_code=422, detail="Escribe qué buscar: no hay una consulta posible.") from None
        except BaseException:
            _fin_de_la_ultima = time.monotonic()
            raise
        _fin_de_la_ultima = time.monotonic()
        return respuesta
