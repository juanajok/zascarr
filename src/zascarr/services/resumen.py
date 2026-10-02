"""
Resumen de la biblioteca (V4): las cifras del Inicio, en un único sitio.

Hasta V3 estas cinco consultas vivían dentro del router `web/dashboard.py`: ninguna otra pantalla
podía reutilizarlas y la plantilla del Inicio recibía números sueltos. Se extraen aquí SIN cambiar
ninguna cifra (ni el orden de las consultas, que fijan los tests) para que `PrimerosPasos` (V4) y el
resto de pantallas lean de la misma fuente en vez de recalcular.

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
class ResumenBiblioteca:
    total_series: int
    series_con_archivos: int
    # Suma de `Series.total_issues` (el catálogo conocido); 0 si ninguna serie lo tiene.
    total_issues: int
    # Números distintos con al menos un archivo disponible.
    issues_importados: int
    huecos_pendientes: int
    ultimas_series: tuple[Series, ...]

    @property
    def porcentaje_completitud(self) -> int:
        """Redondeado; 0 cuando no hay catálogo (V4b lo distingue de un 0 % real)."""
        if not self.total_issues:
            return 0
        return round(self.issues_importados / self.total_issues * 100)


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

    total_issues = (await db.execute(
        select(func.sum(Series.total_issues)).where(Series.total_issues.isnot(None))
    )).scalar() or 0

    issues_importados = (await db.execute(
        select(func.count(func.distinct(File.issue_id)))
        .where(File.issue_id.isnot(None))
        .where(File.is_missing.is_(False))
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
    for series_id, total, fuente in series_totales:
        if fuente not in UNIDAD_DE_GRAPA:
            continue
        huecos_pendientes += len(
            compute_missing_issues(total, poseidos_por_serie.get(series_id, set()))
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
        total_issues=total_issues,
        issues_importados=issues_importados,
        huecos_pendientes=huecos_pendientes,
        ultimas_series=tuple(ultimas_series),
    )
