"""Router de Series — CRUD + full-text search + missing issues."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.database import get_db
from zascarr.models import ComicTradition, Series, WishlistPolicy
from zascarr.services.asignacion import conflicto_por_operacion_viva

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

router = APIRouter(prefix="/series", tags=["series"])

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


@router.post("", status_code=201)
async def create_series(data: SeriesCreate, db: AsyncSession = Depends(get_db)):
    series = Series(**data.model_dump())
    db.add(series)
    await db.flush()
    await db.refresh(series)
    return series


@router.patch("/{series_id}")
async def update_series(series_id: UUID, data: SeriesUpdate, db: AsyncSession = Depends(get_db)):
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(series, field, value)
    await db.flush()
    return series


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: UUID, db: AsyncSession = Depends(get_db)):
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    try:
        await db.delete(series)
        # `flush` AQUÍ y no al salir de `get_db`: ese `commit` ocurre DESPUÉS de responder y
        # un fallo de integridad llegaría tarde, con el 204 ya entregado.
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if conflicto_por_operacion_viva(exc):
            raise HTTPException(
                status_code=409,
                detail="Esta serie tiene una asignación de archivos en curso; espera a que termine "
                       "(o se reconcilie) e inténtalo de nuevo.",
            ) from exc
        raise                       # cualquier OTRO error de integridad NO es este conflicto


@router.get("/{series_id}/missing")
async def get_missing_issues(series_id: UUID, db: AsyncSession = Depends(get_db)):
    """Números faltantes respecto a total_issues. Alimenta la wishlist.

    Sin total conocido devuelve lista vacía (no se inventa nada)."""
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return (await huecos_de_serie(db, series)).faltantes
