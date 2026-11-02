"""Router de Series — CRUD + full-text search + missing issues."""
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition, Series, WishlistPolicy
from zascarr.services.alta_serie import DemasiadasParecidasError
from zascarr.services.borrado_serie import (
    BorradoDeSerie,
    SerieNoBorrableError,
    SerieNoEncontradaError,
)
from zascarr.services.edicion_serie import EdicionDeSerie, ParecidasSinVerError, SerieCambiadaError
from zascarr.services.legal import is_acknowledged
from zascarr.services.retirada_serie import ResultadoRetirada, RetiradaDeSerie, VistaPreviaRetirada

# El cálculo de huecos vive en `services/` (lo usa también el orquestador, que
# no puede depender de `api/`). Se reexportan aquí porque `web/series.py`,
# `web/dashboard.py` y sus tests ya los importaban de este módulo.
from zascarr.services.series import (  # noqa: F401
    UNIDAD_DE_GRAPA,
    Huecos,
    SeriesService,
    compute_missing_issues,
    huecos_de_serie,
    numeros_poseidos,
    numeros_poseidos_por_serie,
)
from zascarr.services.tokens_revision import (
    MAX_PARECIDAS_FIRMADAS,
    MAX_TOKEN_RETIRADA,
    verificar_token_retirada,
)
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
)
from zascarr.utils.url_portada import es_url_de_portada_permitida

router = APIRouter(prefix="/series", tags=["series"])
logger = structlog.get_logger()


def _portada_permitida(valor: str | None) -> str | None:
    """H1: la portada se descarga EN EL SERVIDOR: solo se guarda una URL que cumpla la política
    de `utils/url_portada.py`. `None` borra la portada."""
    if valor is not None and not es_url_de_portada_permitida(valor):
        raise ValueError(
            "La portada debe ser una URL http(s) de Comic Vine, AniList, Tebeosfera o GCD, "
            "sin usuario, sin dirección IP escrita y sin puerto distinto del habitual."
        )
    return valor


# ── Schemas de escritura (M1: mass assignment prohibido) ───────────────────
# Solo se permite escribir los campos de cara al coleccionista. Los campos
# internos o calculados (id, title_norm, comic_vine_id/anilist_id/
# tebeosfera_slug, metadata_*, locked_fields, enrichment_attempted_at,
# created_at/updated_at) NO están en el schema y `extra="forbid"` los rechaza
# con 422 en vez de inyectarlos en el ORM.
class SeriesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=500)
    sort_title: str | None = Field(default=None, max_length=500)
    tradition: ComicTradition = ComicTradition.AMERICAN
    start_year: int | None = Field(default=None, ge=1800, le=2100)
    end_year: int | None = Field(default=None, ge=1800, le=2100)
    total_issues: int | None = Field(default=None, ge=0)
    status: str = Field(default="ongoing", max_length=50)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=500)

    @field_validator("cover_url")
    @classmethod
    def _cover_url_permitida(cls, valor: str | None) -> str | None:
        return _portada_permitida(valor)


class SeriesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    sort_title: str | None = Field(default=None, max_length=500)
    tradition: ComicTradition | None = None
    start_year: int | None = Field(default=None, ge=1800, le=2100)
    end_year: int | None = Field(default=None, ge=1800, le=2100)
    total_issues: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=500)
    # I5: ids de las series parecidas que el cliente ya vio (no es un campo de la serie).
    vistas: list[UUID] = Field(default_factory=list, max_length=MAX_PARECIDAS_FIRMADAS)
    # D8: la política de búsqueda por serie. Va declarada aquí porque
    # `extra="forbid"` rechazaría el campo si no estuviera — y con los dos
    # valores reservados ya dentro del ENUM, un PATCH podría fijarlos sin pasar
    # por la UI. Se rechazan en el servidor (422), no solo deshabilitados en el
    # selector.
    wishlist_policy: WishlistPolicy | None = None

    @field_validator("wishlist_policy")
    @classmethod
    def _solo_politicas_aplicables(cls, valor: WishlistPolicy | None) -> WishlistPolicy:
        """`futuros` y `todos` están reservados pero todavía no significan nada
        aplicable (ver ficha D8): aceptarlos haría creer al coleccionista que se
        busca algo. Falla con motivo legible en vez de un valor que no hace
        nada.

        Un `null` explícito también se rechaza: la columna es NOT NULL, y
        dejarla a NULL reventaría al escribir; para no buscar nada está
        `ninguno`."""
        if valor is None:
            raise ValueError(
                "La política de búsqueda no puede quedar vacía: usa «ninguno» si "
                "no quieres que ZascArr busque nada de esta serie por su cuenta."
            )
        if valor in (WishlistPolicy.FUTURE, WishlistPolicy.ALL):
            raise ValueError(
                "«futuros» y «todos» todavía no se pueden aplicar: «futuros» "
                "necesita que la fuente publique los números que aún no han "
                "salido, y «todos» espera a una historia posterior. Usa "
                "«ninguno» o «faltantes»."
            )
        return valor

    @field_validator("cover_url")
    @classmethod
    def _cover_url_permitida(cls, valor: str | None) -> str | None:
        return _portada_permitida(valor)


@router.get("")
async def list_series(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tradition: str | None = None,
    status: str | None = None,
    search: str | None = Query(default=None),
    publisher_id: UUID | None = None,
    character_id: UUID | None = None,
    story_arc_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await SeriesService(db).list_series(
        page=page, page_size=page_size, tradition=tradition, status=status,
        search=search, publisher_id=publisher_id, character_id=character_id,
        story_arc_id=story_arc_id,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


@router.get("/{series_id}")
async def get_series(series_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(Series).where(Series.id == series_id).options(selectinload(Series.genres))
    series = (await db.execute(q)).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return series


@router.post("", status_code=201, deprecated=True)
async def create_series(data: SeriesCreate, db: AsyncSession = Depends(get_db)):
    """**Obsoleto (I3 de #114, fase 1 de su retirada).** Sin cambios de comportamiento, pero
    **no ofrece las garantías G1–G8** del alta por token (`POST /api/revision/serie/previsualizar`
    y `/serie`): no hay vista previa ni confirmación, la tradición es `american` si no se indica,
    no detecta series con el mismo título, no usa candados, no deja procedencia (`metadata_source`
    queda vacío y el enriquecedor puede completar la fila) ni comprobante, y no se puede deshacer.
    Sustituto: `POST /api/revision/serie/sin-carpeta/previsualizar` (título y año a mano, tradición
    elegida) y `POST /api/revision/serie` con su token; después, `PATCH /api/series/{id}` para la
    descripción, la portada, el estado o el total de números. Esta ruta se retirará en una versión
    posterior."""
    series = Series(**data.model_dump())
    db.add(series)
    await db.flush()
    await db.refresh(series)
    return series


@router.patch("/{series_id}")
async def update_series(series_id: UUID, data: SeriesUpdate, db: AsyncSession = Depends(get_db)):
    """Edita una serie. Si cambia el título, la tradición o el año, aplica la misma detección de
    series parecidas que el alta (I5 de #114): `409 serie_parecida` con la lista, salvo que
    `vistas` incluya sus identificadores."""
    cambios = data.model_dump(exclude_unset=True)
    vistas = {str(v) for v in cambios.pop("vistas", [])}
    # Puerta legal (C6, SecOps A-1): activar una política distinta de `ninguno` exige el aviso
    # aceptado, igual que en la UI; desactivar nunca. Mismo 403 y mismo `HX-Redirect` que
    # `require_legal_acknowledgment`. El 404 va antes.
    politica = cambios.get("wishlist_policy")
    activa = politica is not None and politica != WishlistPolicy.NONE
    if activa and not await is_acknowledged(db):
        existe = (await db.execute(
            select(Series.id).where(Series.id == series_id))).scalar_one_or_none()
        if existe is None:
            raise HTTPException(status_code=404, detail="Serie no encontrada")
        raise HTTPException(status_code=403, detail="legal_acknowledgment_required",
                            headers={"HX-Redirect": "/ui/legal"})
    try:
        return await EdicionDeSerie(db).actualizar(series_id, cambios, vistas)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    except ParecidasSinVerError as exc:
        detalle = {"codigo": "serie_parecida", "mensaje": str(exc),
                   "parecidas": [p.model_dump() for p in exc.parecidas]}
        raise HTTPException(status_code=409, detail=detalle) from exc
    except DemasiadasParecidasError as exc:
        detalle = {"codigo": exc.codigo, "mensaje": str(exc)}
        raise HTTPException(status_code=422, detail=detalle) from exc
    except SerieCambiadaError as exc:
        detalle = {"codigo": "serie_cambiada",
                   "mensaje": "La serie ha cambiado mientras se comprobaba: repite la petición."}
        raise HTTPException(status_code=409, detail=detalle) from exc


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: UUID, db: AsyncSession = Depends(get_db)):
    """Borra una serie **sin dependientes** (ADR 0010 P-3, I4 de #114). No toca el disco.

    `409` si hay una asignación en curso (`detail` en texto, como siempre), o si tiene archivos
    vinculados, números o deseados (`detail` = `{"codigo", "mensaje"}`); en ningún caso cambia
    nada."""
    try:
        await BorradoDeSerie(db).borrar(series_id)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    except SerieNoBorrableError as exc:
        if exc.motivo == "operacion_viva":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        detalle = {"codigo": exc.motivo, "mensaje": str(exc)}
        raise HTTPException(status_code=409, detail=detalle) from exc


# ── BL-SER1 (#303): retirar una serie de la biblioteca SIN borrar sus archivos ───────────────────

class PeticionRetirarSerie(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1, max_length=MAX_TOKEN_RETIRADA)


def _secreto() -> str:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(
            status_code=503, headers={"Cache-Control": "no-store"},
            detail="El servidor no tiene clave para firmar; reinícialo.")
    return secret


_NO_STORE = {"Cache-Control": "no-store"}


def _error_retirada(estado: int, codigo: str, mensaje: str,
                    *, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status_code=estado, detail={"codigo": codigo, "mensaje": mensaje},
                         headers={**_NO_STORE, **(headers or {})})


@router.post("/{series_id}/retirada/previsualizar", response_model=VistaPreviaRetirada)
async def previsualizar_retirada(
    series_id: UUID, response: Response, db: AsyncSession = Depends(get_db),
) -> VistaPreviaRetirada:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await RetiradaDeSerie(db, secret=_secreto()).previsualizar(series_id)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, headers=_NO_STORE,
                            detail="Serie no encontrada") from None


async def ejecutar_retirada(db: AsyncSession, token: str) -> ResultadoRetirada:
    try:
        return await RetiradaDeSerie(db, secret=_secreto()).confirmar(token)
    except TokenInvalidoError as e:
        raise _error_retirada(422, e.codigo, str(e)) from None
    except TokenCaducadoError as e:
        raise HTTPException(
            status_code=410, headers=_NO_STORE,
            detail={
                "codigo": e.codigo,
                "mensaje": str(e),
                "puede_haberse_aplicado": e.puede_haberse_aplicado,
            }) from None
    except ConflictoDeBloqueoError as e:
        raise HTTPException(status_code=503, headers={**_NO_STORE, "Retry-After": "1"},
                            detail={"codigo": e.codigo, "mensaje": str(e)}) from None
    except ResultadoInciertoError as e:
        raise HTTPException(
            status_code=503, headers={**_NO_STORE, "Retry-After": "1"},
            detail={
                "codigo": e.codigo,
                "mensaje": ("No se pudo confirmar si se retiró. Repite la confirmación con el "
                            "mismo token para ver el resultado."),
            }) from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("retirada.error_inesperado")
        raise _error_retirada(
            500, "error_inesperado",
            "No se pudo completar y no se ha cambiado nada. Inténtalo de nuevo.") from None


@router.post("/{series_id}/retirada", response_model=ResultadoRetirada)
async def retirar_serie(
    series_id: UUID,
    peticion: PeticionRetirarSerie,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ResultadoRetirada:
    response.headers["Cache-Control"] = "no-store"
    firmado = verificar_token_retirada(peticion.token, _secreto(), ignorar_caducidad=True)
    if firmado is None or firmado.series_id != str(series_id):
        raise _error_retirada(
            422, "token_invalido",
            "Esa vista previa no es de esta serie: ábrela de nuevo desde la serie.")
    return await ejecutar_retirada(db, peticion.token)


@router.get("/{series_id}/missing")
async def get_missing_issues(series_id: UUID, db: AsyncSession = Depends(get_db)):
    """Números faltantes respecto a total_issues. Alimenta la wishlist.

    Sin total conocido devuelve lista vacía (no se inventa nada)."""
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return (await huecos_de_serie(db, series)).faltantes
