"""BL-PARSE3 (F2): la carpeta sugiere la serie de un pendiente en «Por revisar».

Si al menos `MINIMO_HERMANOS` archivos de la misma carpeta ya tienen número y están **todos** en
la misma serie, esa serie se ofrece como sugerencia de un clic. Nunca enlaza sola: la tarjeta usa
el mismo formulario de B12 y el coleccionista confirma.

Medido el 2026-11-26 (`docs/design/especificacion-BL-PARSE3.md` §6): 99,89 % de acierto sobre 2.713
archivos ya vinculados. Cuentan todos los vínculos, no solo los manuales (estos se concentran en
carpetas de eventos y dan peor resultado), y la unanimidad deja fuera las carpetas mezcladas.

Se calcula al pintar la pantalla, con una consulta por página: no guarda nada, así que asignar tres
archivos de una carpeta hace que el cuarto salga sugerido en la siguiente visita.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, Series
from zascarr.utils.naming import es_titulo_de_anual, parse_comic_filename

#: Hermanos con número, todos en la misma serie, necesarios para sugerir (R1).
MINIMO_HERMANOS = 3

#: R2b: un «número» 19xx/20xx es un año (`… Century 1910`), no el de la grapa.
_NUMERO_CON_FORMA_DE_ANIO = re.compile(r"(?:19|20)\d{2}")


@dataclass(frozen=True)
class SugerenciaCarpeta:
    """La serie que proponen los hermanos de carpeta y cuántos son."""
    series_id: UUID
    title: str
    start_year: int | None
    hermanos: int


def carpeta_de(ruta: str) -> str:
    """La carpeta de un archivo: su ruta completa sin el nombre (no solo el último tramo)."""
    return str(PurePosixPath(ruta).parent)


async def sugerencias_por_carpeta(
    db: AsyncSession, archivos: Sequence[File],
) -> dict[UUID, SugerenciaCarpeta]:
    """Sugerencia por la carpeta de cada pendiente de `archivos` que la tenga (R1, R2).

    Una sola consulta para todas sus carpetas (R4). Los hermanos son archivos con número y no
    ausentes; los pendientes no tienen número, así que nunca cuentan, tampoco el propio archivo."""
    carpetas = {carpeta_de(f.file_path) for f in archivos if f.file_path}
    if not carpetas:
        return {}
    carpeta = func.regexp_replace(File.file_path, "/[^/]*$", "")
    filas = (await db.execute(
        select(carpeta.label("carpeta"), Series.id.label("series_id"), Series.title,
               Series.start_year, func.count(File.id).label("hermanos"))
        .join(Issue, File.issue_id == Issue.id)
        .join(Series, Issue.series_id == Series.id)
        .where(File.is_missing.is_(False), carpeta.in_(carpetas))
        .group_by(carpeta, Series.id, Series.title, Series.start_year)
    )).all()

    por_carpeta: dict[str, list] = defaultdict(list)
    for fila in filas:
        por_carpeta[fila.carpeta].append(fila)
    unanimes = {
        c: series[0] for c, series in por_carpeta.items()
        if len(series) == 1 and series[0].hermanos >= MINIMO_HERMANOS}

    sugerencias: dict[UUID, SugerenciaCarpeta] = {}
    for f in archivos:
        fila = unanimes.get(carpeta_de(f.file_path)) if f.file_path else None
        if fila is None:
            continue
        parsed = parse_comic_filename(f.file_name)
        # R2: un anual solo con una serie anual, y al revés (la misma regla que el matcher).
        if parsed.is_annual != es_titulo_de_anual(fila.title):
            continue
        # R2b: lo que queda pendiente en una carpeta homogénea suele ser lo que no encaja
        # (especiales, promocionales, otras obras): sin número, especial o con un año por número.
        if (not parsed.issue_number or parsed.is_special
                or _NUMERO_CON_FORMA_DE_ANIO.fullmatch(parsed.issue_number)):
            continue
        sugerencias[f.id] = SugerenciaCarpeta(
            series_id=UUID(str(fila.series_id)), title=fila.title,
            start_year=fila.start_year, hermanos=fila.hermanos)
    return sugerencias
