"""Cola diferida de `ComicInfo.xml` (CCM-5, #1004).

Marca los números consolidados y los sincroniza con el plan de B6 fuera de la
petición. La cola es deliberadamente pequeña: un worker, un fichero cada vez y
una pausa configurable para no saturar el disco de la Pi.

No amplía B6 con `Web`/`GTIN`/`Count`: esos tags no están en el mapa actual y
quedan aplazados. El filtro de `Summary` sigue en `tagger.py`: externo nunca,
manual sí.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, FileFormat, Issue
from zascarr.services.tagger import ESCRITO, SALTADO, TaggerService

logger = structlog.get_logger()

CLAVE_PENDIENTE = "comicinfo_sync_pendiente"
PAUSA_IO_S = 2.0
MAX_LOTE = 20


@dataclass
class InformeCola:
    mirados: int = 0
    escritos: int = 0
    sin_cambios: int = 0
    aplazados: int = 0
    errores: int = 0


def _pendiente(issue: Issue) -> bool:
    meta = issue.metadata_ if isinstance(issue.metadata_, dict) else {}
    return meta.get(CLAVE_PENDIENTE) is True


def _marcar(issue: Issue, valor: bool) -> None:
    meta = dict(issue.metadata_ or {})
    if valor:
        meta[CLAVE_PENDIENTE] = True
    else:
        meta.pop(CLAVE_PENDIENTE, None)
    issue.metadata_ = meta


class SincronizadorComicInfo:
    def __init__(self, db: AsyncSession, *, pausa_s: float = PAUSA_IO_S,
                 tagger_factory=None):
        self._db = db
        self._pausa_s = pausa_s
        self._tagger_factory = tagger_factory or TaggerService

    async def _issues(self, limite: int) -> list[Issue]:
        filas = (await self._db.execute(
            select(Issue).where(Issue.metadata_.has_key(CLAVE_PENDIENTE))
            .order_by(Issue.id).limit(max(1, limite))
        )).scalars().all()
        return [i for i in filas if _pendiente(i)]

    async def _archivos(self, issue_id) -> list[File]:
        return (await self._db.execute(
            select(File).where(
                File.issue_id == issue_id,
                File.file_format == FileFormat.CBZ,
                File.is_missing.is_(False),
            ).order_by(File.id)
        )).scalars().all()

    async def procesar_issue(self, issue: Issue, *, informe: InformeCola) -> None:
        archivos = await self._archivos(issue.id)
        informe.mirados += 1
        if not archivos:
            _marcar(issue, False)
            await self._db.flush()
            return
        tagger = self._tagger_factory(self._db)
        aplazado = False
        for archivo in archivos:
            resultado = await tagger.ejecutar(archivo, dry_run=False)
            if resultado.accion == ESCRITO:
                informe.escritos += 1
            elif resultado.accion == SALTADO:
                if resultado.advertencia or "ausente" in (resultado.motivo or ""):
                    informe.aplazados += 1
                    aplazado = True
                else:
                    informe.sin_cambios += 1
            else:
                informe.errores += 1
        if not aplazado:
            _marcar(issue, False)
        await self._db.flush()

    async def procesar_lote(self, limite: int = MAX_LOTE) -> InformeCola:
        informe = InformeCola()
        issues = await self._issues(limite)
        for pos, issue in enumerate(issues):
            if pos:
                await asyncio.sleep(self._pausa_s)
            try:
                await self.procesar_issue(issue, informe=informe)
                await self._db.commit()
            except Exception:  # noqa: BLE001 — un número no corta la cola
                await self._db.rollback()
                informe.errores += 1
                logger.exception("ccm.cola_comicinfo_error", issue_id=str(issue.id))
        return informe
