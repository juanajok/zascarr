"""
Resumen de la biblioteca (V4): las cifras del Inicio, en un único sitio.

Hasta V3 estas consultas vivían dentro del router `web/dashboard.py` (V4a las extrajo SIN cambiar
ninguna cifra). V4b corrige lo que esas cifras afirmaban de más:

- «Completitud» dividía los números que HAY (de cualquier serie) entre la suma del catálogo de
  TODAS las fuentes: mezclaba unidades (grapas de Comic Vine, capítulos de AniList, «números» de
  Tebeosfera) y series sin catálogo. Ahora solo cuentan las series cuyo recuento está acreditado
  como de grapas (`UNIDAD_DE_GRAPA`), y si no hay ninguna NO hay cifra (`completitud is None`),
  no «0 %».
- «Números pendientes» = 0 podía significar «colección completa» o «no sé calcularlo». Ahora se
  acompaña de cuántas series se pudieron calcular y cuántas no.

Nota de modelo: `File` NO tiene `series_id`; la relación es File → Issue → Series.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, Series
from zascarr.services.series import (
    UNIDAD_DE_GRAPA,
    compute_missing_issues,
    numeros_poseidos_por_serie,
)

# Cuántas series muestra «Últimas actualizaciones».
ULTIMAS_SERIES = 10


@dataclass(frozen=True)
class Completitud:
    """Cobertura SOLO de las series con recuento de grapas acreditado."""
    tienes: int
    de: int
    series: int

    @property
    def porcentaje(self) -> int:
        return round(self.tienes / self.de * 100)


@dataclass(frozen=True)
class ResumenBiblioteca:
    total_series: int
    series_con_archivos: int
    # Ficheros registrados y disponibles (no marcados como desaparecidos): lo que ZascArr tiene
    # anotado, NO una lectura del disco.
    archivos_registrados: int
    # Series cuyo catálogo permite contar huecos (recuento de grapas) y las que no.
    series_con_recuento: int
    huecos_pendientes: int
    completitud: Completitud | None
    ultimas_series: tuple[Series, ...]

    @property
    def series_sin_recuento(self) -> int:
        return self.total_series - self.series_con_recuento


async def resumen_biblioteca(db: AsyncSession) -> ResumenBiblioteca:
    """Las cifras del Inicio. Solo lee; no hace `commit`."""
    total_series = (await db.execute(select(func.count(Series.id)))).scalar() or 0

    # B7 (revisión de PR, 2026-09-26): un File con is_missing=True ya no
    # cuenta como "lo tienes" — sin este filtro, borrar un tebeo a mano
    # del disco no bajaba ni el contador de completitud ni "series con
    # archivos", contradiciendo lo que B7 promete en el badge de la fila.
    series_con_archivos = (await db.execute(
        select(func.count(func.distinct(Issue.series_id)))
        .join(File, File.issue_id == Issue.id)
        .where(File.is_missing.is_(False))
    )).scalar() or 0

    archivos_registrados = (await db.execute(
        select(func.count()).select_from(File).where(File.is_missing.is_(False))
    )).scalar() or 0

    # Huecos pendientes: UNA consulta para todas las series (no una query por
    # serie), luego se agrega en Python reusando la misma función pura
    # (compute_missing_issues) que usa la ficha de serie. La posesión sale del
    # DISCO (archivo disponible) y del formato, NO de `sort_order` — que ningún
    # código de main escribe y hacía que el contador sumara el catálogo entero.
    # Solo entran las series cuyo `total_issues` está acreditado como recuento
    # de grapas (ver `UNIDAD_DE_GRAPA`): sumar capítulos de AniList o "números"
    # de Tebeosfera con grapas sería mezclar unidades.
    series_totales = (await db.execute(
        select(Series.id, Series.total_issues, Series.metadata_source)
        .where(Series.total_issues.isnot(None))
    )).all()

    poseidos_por_serie = await numeros_poseidos_por_serie(db)

    huecos_pendientes = 0
    series_con_recuento = 0
    numeros_con_recuento = 0
    for series_id, total, fuente in series_totales:
        if fuente not in UNIDAD_DE_GRAPA or not total:
            continue
        series_con_recuento += 1
        numeros_con_recuento += total
        huecos_pendientes += len(
            compute_missing_issues(total, poseidos_por_serie.get(series_id, set()))
        )

    completitud = None
    if numeros_con_recuento:
        completitud = Completitud(
            tienes=numeros_con_recuento - huecos_pendientes,
            de=numeros_con_recuento,
            series=series_con_recuento,
        )

    # Últimas series actualizadas: subconsulta con max(imported_at) por serie.
    last_import = (
        select(Issue.series_id.label("series_id"), func.max(File.imported_at).label("ultimo"))
        .join(File, File.issue_id == Issue.id)
        .where(File.is_missing.is_(False))
        .group_by(Issue.series_id)
        .subquery()
    )
    ultimas_series = (await db.execute(
        select(Series)
        .join(last_import, last_import.c.series_id == Series.id)
        .order_by(last_import.c.ultimo.desc())
        .limit(ULTIMAS_SERIES)
    )).scalars().all()

    return ResumenBiblioteca(
        total_series=total_series,
        series_con_archivos=series_con_archivos,
        archivos_registrados=archivos_registrados,
        series_con_recuento=series_con_recuento,
        huecos_pendientes=huecos_pendientes,
        completitud=completitud,
        ultimas_series=tuple(ultimas_series),
    )
