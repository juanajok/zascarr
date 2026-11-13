"""Vincular un archivo EN SU SITIO, sin moverlo ni renombrarlo (#720).

Es la acción segura para archivos que ya están en la biblioteca y cuyo Issue
ya existe. No crea publicaciones, no copia, no mueve y no toca el disco: solo
enlaza la fila de `files` con el `Issue` que la persona eligió. Organizar sigue
siendo el único camino que mueve y renombra.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import EDITION_KIND_A_FORMAT, File, Issue, IssueFormat
from zascarr.utils.naming import parse_comic_filename


@dataclass(frozen=True)
class ResultadoVinculo:
    estado: str
    texto: str = ""


async def vincular_en_sitio(
    db: AsyncSession, file_id: UUID, series_id: UUID, issue_number: str,
) -> ResultadoVinculo:
    numero = (issue_number or "").strip()
    if not numero:
        return ResultadoVinculo("datos_no_validos", "Escribe el número de la publicación.")
    file = await db.get(File, file_id, with_for_update=True)
    if file is None:
        return ResultadoVinculo("no_encontrado", "El archivo ya no existe.")
    if file.issue_id is not None:
        return ResultadoVinculo("ya_vinculado", "Ese archivo ya está vinculado.")
    biblioteca = Path(str(get_settings().library_path)).resolve()
    ruta = Path(file.file_path).resolve()
    try:
        dentro = ruta.is_relative_to(biblioteca) and "_Unsorted" not in ruta.parts
    except (OSError, ValueError):
        dentro = False
    if not dentro:
        return ResultadoVinculo(
            "fuera_de_biblioteca",
            "Este archivo aún no está en su sitio: usa Organizar para moverlo y renombrarlo.")

    formato = EDITION_KIND_A_FORMAT.get(
        parse_comic_filename(file.file_name).edition_kind, IssueFormat.SINGLE_ISSUE)
    filas = list((await db.execute(
        sa.select(Issue.id, Issue.format)
        .where(Issue.series_id == series_id,
               func.lower(Issue.issue_number) == func.lower(numero))
        .with_for_update())).all())
    if not filas:
        return ResultadoVinculo(
            "issue_no_existe",
            "Esa publicación todavía no existe en la serie. "
            "Usa Organizar para crearla y mover el archivo.")
    if len(filas) > 1:
        return ResultadoVinculo(
            "numero_ambiguo",
            "Esa serie tiene más de un número así (volúmenes distintos): no elijo uno por ti.")
    issue_id, formato_issue = filas[0]
    if (formato_issue or IssueFormat.SINGLE_ISSUE) != formato:
        return ResultadoVinculo(
            "colision_edicion",
            "Ese número existe como otra edición (por ejemplo una grapa y un recopilatorio).")
    ocupado = (await db.execute(
        sa.select(sa.func.count()).select_from(File).where(File.issue_id == issue_id))).scalar_one()
    if ocupado:
        return ResultadoVinculo(
            "issue_ocupado", "Esa publicación ya tiene otro archivo vinculado.")
    ahora = datetime.now(UTC).isoformat()
    meta = dict(file.metadata_ or {})
    meta["vinculo"] = {
        "version": 1, "tipo": "en_sitio", "fecha": ahora,
        "serie_id": str(series_id), "numero": numero, "formato": formato.value,
    }
    if file.issue_id is not None:
        return ResultadoVinculo("ya_vinculado", "Ese archivo ya está vinculado.")
    file.issue_id = issue_id
    file.metadata_source = "manual"
    file.metadata_ = meta
    await db.flush()
    return ResultadoVinculo("vinculado", "")
