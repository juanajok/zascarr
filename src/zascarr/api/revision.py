# ruff: noqa: E501
"""Router de revisión: `GET /api/revision/carpetas` (rebanada 1), `POST /api/revision/descubrir` (2a) y el alta de
la serie (2b: `serie/previsualizar`, `serie` y `serie/{id}/deshacer`).

`carpetas` y `descubrir` no escriben ni ofrecen acciones; `carpetas` no usa disco ni red y `descubrir` es el ÚNICO
que usa la red, y solo cuando se llama (a petición: nunca al abrir un grupo). El alta solo escribe una fila de
`series` al confirmar (y la borra al deshacer): ni números, ni archivos, ni red. La vista previa de la vinculación
(2c) solo lee (`SELECT` y `stat`); la confirmación (2d) vincula en su sitio, sin mover ningún fichero. Exigen sesión o Basic como el resto de `/api/*` (lo
hace `AuthMiddleware`); no llevan dependencia legal porque no son acciones de riesgo (CLAUDE.md §5.2).
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.alta_serie import (
    AltaDeSerie,
    AltaDeshechaError,
    AltaError,
    AltaSerieAusenteError,
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
from zascarr.services.tokens_revision import MAX_CLAVE_GRUPO, MAX_TOKEN_VINCULACION
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    RespuestaEjecucion,
    ResultadoInciertoError,
    TokenCaducadoError,
    VinculacionDeArchivos,
)
from zascarr.services.vinculacion import SerieYaNoExisteError as SerieDeVinculacionYaNoExisteError
from zascarr.services.vinculacion import TokenInvalidoError as TokenDeVinculacionInvalidoError
from zascarr.services.vinculacion_previa import (
    ArchivoAjenoError,
    CursorNoValidoError,
    NumeroNoValidoError,
    RespuestaVinculacion,
    SerieElegidaNoExisteError,
    VistaPreviaDeVinculacion,
)

logger = structlog.get_logger()

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
    except (SerieYaNoExisteError, IdentificadorCambiadoError, AltaDeshechaError, AltaSerieAusenteError) as e:
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


# ── 2c: vista previa de la vinculación ────────────────────────────────────────────────────────

class PeticionPrevisualizarVinculacion(BaseModel):
    """El grupo, la serie elegida y las modificaciones EXPLÍCITAS de la persona. Nada viene marcado por defecto."""
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(..., min_length=1, max_length=MAX_CLAVE_GRUPO)
    series_id: UUID
    #: id de archivo → número editado (vacío: quitarlo). Lo que no esté aquí usa el número del nombre.
    numeros: dict[UUID, str] = Field(default_factory=dict, max_length=1000)
    #: ids de archivo que la persona ha marcado. Vacío al principio.
    marcados: list[UUID] = Field(default_factory=list, max_length=1000)
    #: Posición de la página (el `siguiente` de la respuesta anterior). Sin cursor: la primera página.
    cursor: str | None = Field(default=None, max_length=2000)


@router.post("/vinculacion/previsualizar", response_model=RespuestaVinculacion)
async def previsualizar_vinculacion(
    peticion: PeticionPrevisualizarVinculacion, response: Response, db: AsyncSession = Depends(get_db),
) -> RespuestaVinculacion:
    """Qué pasaría si estos archivos se vincularan a esta serie, SIN hacerlo. Solo `SELECT` y `stat` (metadatos): no
    escribe, no lee contenido, no calcula hashes, no usa la red y no calcula destinos (vincular conserva nombre y
    ruta). Emite el token `vincular` solo si hay al menos un archivo marcado y ejecutable. Evalúa como mucho 100 archivos por
    petición; `cursor` / `pagina.siguiente` recorren el resto del grupo."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return await VistaPreviaDeVinculacion(db, secret=_secreto()).previsualizar(
            peticion.clave, peticion.series_id,
            numeros={str(k): v for k, v in peticion.numeros.items()},
            marcados={str(m) for m in peticion.marcados}, cursor=peticion.cursor)
    except GrupoNoEncontradoError:
        raise HTTPException(status_code=404, detail={
            "codigo": "grupo_no_encontrado", "mensaje": "No hay registros pendientes en esa carpeta."}) from None
    except SerieElegidaNoExisteError:
        raise HTTPException(status_code=404, detail={
            "codigo": "serie_no_encontrada", "mensaje": "La serie elegida no existe."}) from None
    except ArchivoAjenoError as e:
        raise HTTPException(status_code=422, detail={
            "codigo": "archivo_ajeno_al_grupo",
            "mensaje": f"{e.cuantos} archivo(s) indicado(s) no pertenecen a este grupo."}) from None
    except NumeroNoValidoError as e:
        raise HTTPException(status_code=422, detail={"codigo": "numero_no_valido", "mensaje": str(e)}) from None
    except CursorNoValidoError as e:
        raise HTTPException(status_code=422, detail={"codigo": "cursor_no_valido", "mensaje": str(e)}) from None


# ── 2d: vincular en su sitio ──────────────────────────────────────────────────────────────────

class PeticionVincular(BaseModel):
    """La confirmación recibe SOLO el token: ni números, ni selección, ni serie. Su tamaño máximo es el del mayor
    token que la vista previa puede emitir (100 archivos, conflictos y clave incluidos): se calcula, no se elige."""
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1, max_length=MAX_TOKEN_VINCULACION)


@router.post("/vinculacion", response_model=RespuestaEjecucion, response_model_by_alias=True)
async def vincular(
    peticion: PeticionVincular, response: Response, db: AsyncSession = Depends(get_db),
) -> RespuestaEjecucion:
    """Ejecuta lo que enseñó y firmó la vista previa, en UNA transacción y SIN mover ningún fichero. Repetir el
    mismo token devuelve el mismo informe. Nunca anuncia éxito si algún archivo no quedó vinculado."""
    response.headers["Cache-Control"] = "no-store"
    secret = _secreto()
    try:
        return await VinculacionDeArchivos(db, secret=secret).confirmar(peticion.token)
    except TokenDeVinculacionInvalidoError as e:
        raise _error_vinculacion(422, e.codigo, str(e)) from None
    except TokenCaducadoError as e:
        raise _error_vinculacion(410, e.codigo, str(e)) from None
    except SerieDeVinculacionYaNoExisteError as e:
        raise _error_vinculacion(409, e.codigo, str(e)) from None
    except ConflictoDeBloqueoError as e:
        raise HTTPException(status_code=503, headers={"Retry-After": "1"},
                            detail={"codigo": e.codigo, "mensaje": str(e)}) from None
    except ResultadoInciertoError as e:
        # Falló DESPUÉS de pedir el commit: no se afirma que no haya cambios. Repetir el token lo aclara.
        raise HTTPException(
            status_code=503, headers={"Retry-After": "1"},
            detail={"codigo": e.codigo, "mensaje": "No se pudo confirmar si se aplicó. Repite la confirmación con el "
                    "mismo token: si ya se aplicó, verás el mismo informe; si no, se aplicará."}) from None
    except HTTPException:
        raise
    except Exception as e:
        # Sin rutas ni nombres en el registro: solo el tipo del error. Nada se ha cambiado (rollback completo).
        logger.error("vinculacion.error_inesperado", tipo=type(e).__name__)
        raise _error_vinculacion(
            500, "error_inesperado", "No se pudo completar y no se ha cambiado nada. Inténtalo de nuevo.") from None


def _error_vinculacion(estado: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=estado, detail={"codigo": codigo, "mensaje": mensaje})
