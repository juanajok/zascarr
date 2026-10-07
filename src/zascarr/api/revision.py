# ruff: noqa: E501
"""Router de revisión: `GET /api/revision/carpetas` (rebanada 1), `POST /api/revision/descubrir` (2a) y el alta de
la serie (2b: `serie/previsualizar`, `serie` y `serie/{id}/deshacer`).

`carpetas` y `descubrir` no escriben ni ofrecen acciones; `carpetas` no usa disco ni red y `descubrir` es el ÚNICO
que usa la red, y solo cuando se llama (a petición: nunca al abrir un grupo). El alta solo escribe una fila de
`series` al confirmar (y la borra al deshacer): ni números, ni archivos, ni red. Exigen sesión o Basic como el resto de `/api/*` (lo
hace `AuthMiddleware`); no llevan dependencia legal porque no son acciones de riesgo (CLAUDE.md §5.2).
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.alta_serie import (
    AltaDeSerie,
    AltaError,
    DatosManuales,
    IdentificadorCambiadoError,
    NoSePuedeDeshacerError,
    ParecidasNuevasError,
    ResultadoAlta,
    ResultadoDeshacer,
    SerieNoEncontradaError,
    SerieYaNoExisteError,
    VistaPreviaAlta,
)
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


# ── 2b: alta o reutilización de la serie ──────────────────────────────────────────────────────

class DatosManualesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(..., min_length=1, max_length=500)
    anio: int | None = Field(default=None, ge=1800, le=2100)


class PeticionPrevisualizarAlta(BaseModel):
    """Una candidata (el token de 2a) **o** los datos a mano. La tradición se ELIGE: no tiene valor por defecto."""
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(..., min_length=1, max_length=1000)
    candidata: str | None = Field(default=None, max_length=8000)
    manual: DatosManualesIn | None = None
    tradicion: ComicTradition
    decision: Literal["reutilizar", "crear_igualmente"] | None = None
    serie_id: UUID | None = None


class PeticionConfirmarAlta(BaseModel):
    """La confirmación recibe SOLO el token: nada de título, año, tradición ni identificadores sueltos."""
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1, max_length=8000)


class PeticionDeshacerAlta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operacion_id: UUID


def _secreto() -> str:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=503, detail="El servidor no tiene clave para firmar; reinícialo.")
    return secret


def _error(estado: int, e: AltaError, mensaje: str, **extra) -> HTTPException:
    return HTTPException(status_code=estado, detail={"codigo": e.codigo, "mensaje": mensaje, **extra})


@router.post("/serie/previsualizar", response_model=VistaPreviaAlta)
async def previsualizar_alta(
    peticion: PeticionPrevisualizarAlta, response: Response, db: AsyncSession = Depends(get_db),
) -> VistaPreviaAlta:
    """Qué pasaría al dar de alta o reutilizar la serie. Solo lectura: no escribe ni usa la red."""
    response.headers["Cache-Control"] = "no-store"
    servicio = AltaDeSerie(db, secret=_secreto())
    manual = DatosManuales(peticion.manual.titulo, peticion.manual.anio) if peticion.manual else None
    try:
        return await servicio.previsualizar(
            peticion.clave, tradicion=peticion.tradicion, candidata=peticion.candidata, manual=manual,
            decision=peticion.decision, serie_id=peticion.serie_id)
    except GrupoNoEncontradoError:
        raise HTTPException(status_code=404, detail="No hay registros pendientes en esa carpeta.") from None
    except AltaError as e:
        raise _error(422, e, str(e)) from None


@router.post("/serie", response_model=ResultadoAlta)
async def confirmar_alta(
    peticion: PeticionConfirmarAlta, response: Response, db: AsyncSession = Depends(get_db),
) -> ResultadoAlta:
    """Ejecuta lo que enseñó la vista previa (solo el token). Crea la serie, o reutiliza una existente sin tocarla."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return await AltaDeSerie(db, secret=_secreto()).confirmar(peticion.token)
    except ParecidasNuevasError as e:
        raise _error(409, e, "Han aparecido series parecidas desde la vista previa: repítela y decide.",
                     nuevas=[p.model_dump() for p in e.nuevas]) from None
    except (SerieYaNoExisteError, IdentificadorCambiadoError) as e:
        raise _error(409, e, str(e)) from None
    except AltaError as e:
        raise _error(422, e, str(e)) from None


@router.post("/serie/{series_id}/deshacer", response_model=ResultadoDeshacer)
async def deshacer_alta(
    series_id: UUID, peticion: PeticionDeshacerAlta, response: Response, db: AsyncSession = Depends(get_db),
) -> ResultadoDeshacer:
    """Borra una serie CREADA por esa operación mientras no tenga números, archivos ni nada en curso."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return await AltaDeSerie(db, secret=_secreto()).deshacer(series_id, peticion.operacion_id)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    except NoSePuedeDeshacerError as e:
        raise _error(409, e, _MENSAJES_DESHACER.get(e.motivo, "No se puede deshacer."), motivo=e.motivo) from None


_MENSAJES_DESHACER = {
    "no_creada_por_esta_operacion": "Esa serie no la creó esta operación: no se borra desde aquí.",
    "tiene_archivos": "La serie ya tiene archivos vinculados: no se puede deshacer.",
    "tiene_numeros": "La serie ya tiene números: no se puede deshacer.",
    "operacion_viva": "La serie tiene una asignación en curso: espera a que termine.",
    "tiene_deseados": "La serie ya tiene deseados: no se puede deshacer.",
}
