# ruff: noqa: E501
"""Los archivos de una serie agrupados por número, con lo que la ficha necesita para ofrecer «Deshacer» (BL-R1b, #254).

SOLO LECTURA y en un número FIJO de consultas (una para los archivos y otra para las asignaciones vivas), no una por archivo.
No decide nada nuevo: aplica a todos los archivos de la serie la MISMA regla de bloqueo que la vista previa de
`services/desvinculacion.py`. Desde la revisión de D9 (2026-10-23) el único bloqueo de esta lista es `en_curso`: cualquier
archivo vinculado se puede desvincular, conste o no cómo se vinculó. La confirmación vuelve a comprobarlo todo con la fila
bloqueada: esta lista solo decide si se OFRECE el botón y, si no, qué razón se enseña.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.importer_triage import natural_key
from zascarr.models import ASIGNACION_ESTADOS_VIVOS, AsignacionOperacion, File, Issue


@dataclass(frozen=True)
class ArchivoDeNumero:
    id: str
    nombre: str
    formato: str
    falta_en_disco: bool
    #: `None` = se puede ofrecer «Deshacer»; si no, el código de la vista previa (`en_curso`).
    bloqueo: str | None


@dataclass
class NumeroConArchivos:
    issue_id: str
    numero: str
    archivos: list[ArchivoDeNumero] = field(default_factory=list)


async def archivos_por_numero(db: AsyncSession, series_id: UUID) -> list[NumeroConArchivos]:
    """Los números de la serie que tienen al menos un archivo, en orden de lectura, cada uno con sus archivos por nombre."""
    filas = (await db.execute(
        select(File.id, File.file_name, File.file_format, File.is_missing,
               Issue.id.label("issue_id"), Issue.issue_number, Issue.sort_order)
        .join(Issue, File.issue_id == Issue.id).where(Issue.series_id == series_id))).all()
    if not filas:
        return []
    vivas = {str(i) for (i,) in (await db.execute(select(AsignacionOperacion.file_id).where(
        AsignacionOperacion.file_id.in_([f.id for f in filas]), AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS)))).all()}
    por_numero: dict[str, NumeroConArchivos] = {}
    orden: dict[str, tuple] = {}
    # `sort_order` casi nunca está escrito (ver `numeros_poseidos`): sin él, el orden es el NATURAL del número (2 antes que 10).
    for f in sorted(filas, key=lambda f: (f.sort_order is None, f.sort_order or 0.0, natural_key(f.issue_number or ""),
                                          natural_key(f.file_name))):
        bloqueo = "en_curso" if str(f.id) in vivas else None
        n = por_numero.setdefault(str(f.issue_id), NumeroConArchivos(str(f.issue_id), f.issue_number or "(sin número)"))
        orden.setdefault(str(f.issue_id), (f.sort_order is None, f.sort_order or 0.0, natural_key(f.issue_number or "")))
        n.archivos.append(ArchivoDeNumero(
            id=str(f.id), nombre=f.file_name, formato=f.file_format.value, falta_en_disco=bool(f.is_missing), bloqueo=bloqueo))
    return [por_numero[k] for k in sorted(por_numero, key=lambda k: orden[k])]
