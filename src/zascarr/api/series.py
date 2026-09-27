"""Router de Series — CRUD + full-text search + missing issues."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.database import get_db
from zascarr.models import ComicTradition, File, Issue, IssueFormat, Series
from zascarr.services.series import SeriesService

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
    await db.delete(series)


@dataclass(frozen=True)
class Huecos:
    """Huecos de una serie y si el cálculo merece confianza.

    `computable=False` significa "no hay con qué calcularlo", NO "no falta
    nada": la UI debe decirlo en vez de enseñar una lista inventada.
    """
    faltantes: list[int]
    computable: bool
    motivo: str | None = None


def compute_missing_issues(total_issues: int | None, numeros_poseidos: set[int]) -> list[int]:
    """Números 1..total_issues que la serie NO posee. Función pura.

    C2 (peer review): un Annual/especial no "cubre" el hueco de la grapa con
    el mismo número — eso lo garantiza `_numero_de_grapa`, que exige
    `format=SINGLE_ISSUE` y un número entero, en vez de comparar floats.
    """
    if not total_issues:
        return []
    return [i for i in range(1, total_issues + 1) if i not in numeros_poseidos]


def _numero_de_grapa(issue_number: str | None, formato) -> int | None:
    """Número entero si la fila ES una grapa numerada; `None` si no lo es.

    Solo una grapa (`SINGLE_ISSUE`) con número entero ocupa el hueco de la
    grapa de ese número. Un ómnibus/tomo #12 **no** es la grapa #12, y un
    `Annual 1` o un `1.5` tampoco tapan el hueco del nº 1 (regla de C2).
    """
    if formato != IssueFormat.SINGLE_ISSUE:
        return None
    if not issue_number or not issue_number.strip().isdigit():
        return None
    return int(issue_number.strip())


async def numeros_poseidos_por_serie(db: AsyncSession) -> dict[UUID, set[int]]:
    """Números de grapa poseídos, para TODAS las series, en una sola consulta.

    Versión agregada de `numeros_poseidos` para el dashboard (no N+1).
    """
    filas = (await db.execute(
        select(Issue.series_id, Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
    )).all()
    por_serie: dict[UUID, set[int]] = {}
    for series_id, numero, formato, disponible in filas:
        if not disponible:
            continue
        n = _numero_de_grapa(numero, formato)
        if n is not None:
            por_serie.setdefault(series_id, set()).add(n)
    return por_serie


async def numeros_poseidos(db: AsyncSession, series_id: UUID) -> set[int]:
    """Números de grapa que la serie POSEE de verdad, mirando el DISCO.

    Por qué no `Issue.sort_order` (2026-09-27): **ningún código de `main`
    escribe ese campo** — la única derivación que existió (`_derive_sort_order`)
    se quedó en una rama abandonada. Medido con `scripts/medicion/censo_huecos.py`
    sobre una muestra: 0/18 issues con `sort_order` y **52 huecos inventados**
    en 5 series, porque `compute_missing_issues(N, ∅)` devuelve `[1..N]`.

    Ahora la posesión sale de lo que hay en disco — un `File` con
    `is_missing=false`, el mismo criterio que ya usan los demás consumidores
    de "¿lo tengo?" (B7) — y del formato: solo una grapa cubre una grapa.
    """
    filas = (await db.execute(
        select(Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
        .where(Issue.series_id == series_id)
    )).all()
    poseidos: set[int] = set()
    for numero, formato, disponible in filas:
        if not disponible:
            continue
        n = _numero_de_grapa(numero, formato)
        if n is not None:
            poseidos.add(n)
    return poseidos


async def huecos_de_serie(db: AsyncSession, series: Series,
                          poseidos: set[int] | None = None) -> Huecos:
    """Huecos de una serie, diciendo si el cálculo es fiable.

    Sin `total_issues` no hay nada que restar: no se inventan huecos, se dice
    que no se puede calcular (el total lo trae el enricher del catálogo).

    `poseidos` permite reutilizar una consulta ya hecha (la ficha de serie
    necesita el conjunto igualmente, para pintar los números presentes).
    """
    if not series.total_issues:
        return Huecos([], False, "la serie no tiene un total de números conocido")
    if poseidos is None:
        poseidos = await numeros_poseidos(db, series.id)
    return Huecos(compute_missing_issues(series.total_issues, poseidos), True, None)


@router.get("/{series_id}/missing")
async def get_missing_issues(series_id: UUID, db: AsyncSession = Depends(get_db)):
    """Números faltantes respecto a total_issues. Alimenta la wishlist.

    Sin total conocido devuelve lista vacía (no se inventa nada)."""
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return (await huecos_de_serie(db, series)).faltantes
