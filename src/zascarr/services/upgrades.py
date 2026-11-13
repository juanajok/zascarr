"""BL-D3 (#154): propuestas de edición mejor y su escaneo acotado.

Una propuesta es solo una OFERTA: no mueve, sustituye ni borra archivos. El
escaneo periódico mira un lote pequeño de números con archivo, respeta el perfil
de calidad de D2 y guarda la mejor candidata. El envío solo ocurre cuando el
coleccionista confirma una propuesta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue, Series, UpgradeProposal
from zascarr.services.calidad import NIVELES, buscar_mejoras
from zascarr.services.legal import is_acknowledged
from zascarr.services.prowlarr import SearchResult

logger = structlog.get_logger()

OBJETIVO_POR_PERFIL = {"mejor": 3, "equilibrado": 2, "cualquiera": 0}
COOLDOWN_HORAS = 24
MAX_PROPUESTAS = 50


def perfil_y_objetivo(settings=None) -> tuple[str, int]:
    s = settings or get_settings()
    perfil = getattr(s, "quality_profile", "equilibrado") or "equilibrado"
    if perfil not in OBJETIVO_POR_PERFIL:
        perfil = "equilibrado"
    return perfil, OBJETIVO_POR_PERFIL[perfil]


def _prowlarr_listo(settings) -> bool:
    return bool(settings.prowlarr_enabled and settings.prowlarr_url
                and settings.prowlarr_api_key)


def motivo_sin_escaneo(settings=None) -> str | None:
    """Explica por qué un escaneo no puede buscar; None si puede."""
    s = settings or get_settings()
    _, objetivo = perfil_y_objetivo(s)
    if objetivo == 0:
        return ("Con «Lo que haya» no se buscan mejoras. Elige «Equilibrado» o "
                "«Solo lo mejor» en Ajustes.")
    if not _prowlarr_listo(s):
        return "Prowlarr no está activo o le falta la URL o la clave de API."
    if int(getattr(s, "upgrade_scan_interval_minutes", 0) or 0) <= 0:
        return "El escaneo de mejoras está desactivado en Ajustes."
    if int(getattr(s, "upgrade_scan_batch", 0) or 0) <= 0:
        return "El lote de escaneo es 0; no hay números que revisar."
    return None


async def escanear_mejoras(db: AsyncSession, batch: int | None = None) -> int:
    """Busca mejoras para un lote pequeño; devuelve cuántas propuestas nuevas creó."""
    # El escaneo busca en Prowlarr por su cuenta cada cierto tiempo: es una acción de riesgo y
    # sin aviso legal aceptado no se hace (CLAUDE.md §5.2; hallazgo F-1 de SecOps sobre BL-D3).
    if not await is_acknowledged(db):
        return 0
    settings = get_settings()
    perfil, objetivo = perfil_y_objetivo(settings)
    if objetivo == 0 or not _prowlarr_listo(settings):
        return 0
    limite = batch if batch is not None else max(0, getattr(
        settings, "upgrade_scan_batch", 3))
    if limite <= 0:
        return 0
    ahora = datetime.now(UTC)
    corte = ahora - timedelta(hours=COOLDOWN_HORAS)
    issues = (await db.execute(
        select(Issue).where(
            or_(Issue.upgrade_scanned_at.is_(None), Issue.upgrade_scanned_at < corte),
            exists().where(File.issue_id == Issue.id, File.is_missing.is_(False)),
        ).order_by(Issue.upgrade_scanned_at.asc().nullsfirst(), Issue.id).limit(limite)
    )).scalars().all()
    creadas = 0
    for issue in issues:
        serie = await db.get(Series, issue.series_id)
        if serie is None:
            issue.upgrade_scanned_at = ahora
            continue
        resultado = await buscar_mejoras(db, serie, issue, min_tier=objetivo)
        if resultado.reintentable:
            # Fallo de red/cortesía: NO se sella el número; el siguiente ciclo lo reintenta.
            logger.warning("upgrades.search_failed", issue_id=str(issue.id),
                           motivo=resultado.error)
            continue
        issue.upgrade_scanned_at = ahora
        if not resultado.ok or not resultado.candidatos:
            continue
        pendiente = (await db.execute(
            select(UpgradeProposal.id).where(
                UpgradeProposal.issue_id == issue.id,
                UpgradeProposal.status == "pendiente")
        )).scalar_one_or_none()
        if pendiente is not None:
            continue
        mejor = resultado.candidatos[0]
        # #154 P0: el mismo enlace puede reaparecer tras descartarlo o descargarlo.
        # La restricción única impide reinsertarlo; no se vuelve a ofrecer.
        ya_visto = (await db.execute(
            select(UpgradeProposal.id).where(
                UpgradeProposal.issue_id == issue.id,
                UpgradeProposal.candidate_url == mejor.resultado.download_url)
        )).scalar_one_or_none()
        if ya_visto is not None:
            continue
        actual = max((a.calidad.puntuacion for a in resultado.actual), default=0)
        try:
            async with db.begin_nested():
                db.add(UpgradeProposal(
                    issue_id=issue.id,
                    current_tier=actual,
                    candidate_title=mejor.resultado.title,
                    candidate_indexer=mejor.resultado.indexer,
                    candidate_url=mejor.resultado.download_url,
                    candidate_size_bytes=mejor.resultado.size_bytes,
                    candidate_seeders=mejor.resultado.seeders,
                    candidate_tier=mejor.calidad.puntuacion,
                    status="pendiente",
                ))
                await db.flush()
            creadas += 1
        except IntegrityError:
            # Carrera con otro escaneo: la propuesta ya existe; el lote sigue.
            logger.info("upgrades.proposal_duplicate", issue_id=str(issue.id))
    await db.commit()
    return creadas


@dataclass(frozen=True)
class MejoraPendiente:
    propuesta: UpgradeProposal
    issue: Issue
    serie: Series

    @property
    def current_label(self) -> str:
        return NIVELES.get(self.propuesta.current_tier, "sin datos")

    @property
    def candidate_label(self) -> str:
        return NIVELES.get(self.propuesta.candidate_tier, "sin datos")

    @property
    def candidato(self) -> SearchResult:
        return SearchResult(
            title=self.propuesta.candidate_title,
            indexer=self.propuesta.candidate_indexer,
            download_url=self.propuesta.candidate_url,
            size_bytes=self.propuesta.candidate_size_bytes,
            seeders=self.propuesta.candidate_seeders,
            category="comics",
        )


async def listar_mejoras(db: AsyncSession) -> list[MejoraPendiente]:
    filas = (await db.execute(
        select(UpgradeProposal, Issue, Series)
        .join(Issue, Issue.id == UpgradeProposal.issue_id)
        .join(Series, Series.id == Issue.series_id)
        .where(UpgradeProposal.status == "pendiente")
        .order_by(UpgradeProposal.created_at.desc())
        .limit(MAX_PROPUESTAS)
    )).all()
    return [MejoraPendiente(p, i, s) for p, i, s in filas]


async def obtener_mejora(db: AsyncSession, propuesta_id: UUID,
                        *, solo_pendiente: bool = True) -> MejoraPendiente | None:
    consulta = (select(UpgradeProposal, Issue, Series)
                .join(Issue, Issue.id == UpgradeProposal.issue_id)
                .join(Series, Series.id == Issue.series_id)
                .where(UpgradeProposal.id == propuesta_id))
    if solo_pendiente:
        consulta = consulta.where(UpgradeProposal.status == "pendiente")
    fila = (await db.execute(consulta)).first()
    return MejoraPendiente(*fila) if fila else None


async def reclamar_mejora(db: AsyncSession, propuesta_id: UUID) -> MejoraPendiente | None:
    """Pasa pendiente → enviando de forma atómica; evita dobles descargas."""
    reclamada = await db.execute(
        update(UpgradeProposal)
        .where(UpgradeProposal.id == propuesta_id,
               UpgradeProposal.status == "pendiente")
        .values(status="enviando"))
    if reclamada.rowcount == 0:
        return None
    await db.flush()
    return await obtener_mejora(db, propuesta_id, solo_pendiente=False)


async def devolver_mejora(db: AsyncSession, propuesta_id: UUID) -> bool:
    propuesta = await db.get(UpgradeProposal, propuesta_id)
    if propuesta is None or propuesta.status != "enviando":
        return False
    propuesta.status = "pendiente"
    await db.flush()
    return True


async def descartar_mejora(db: AsyncSession, propuesta_id: UUID) -> bool:
    propuesta = await db.get(UpgradeProposal, propuesta_id)
    if propuesta is None or propuesta.status != "pendiente":
        return False
    propuesta.status = "descartada"
    await db.flush()
    return True


async def marcar_descargada(db: AsyncSession, propuesta_id: UUID) -> bool:
    propuesta = await db.get(UpgradeProposal, propuesta_id)
    if propuesta is None or propuesta.status not in ("pendiente", "enviando"):
        return False
    propuesta.status = "descargada"
    await db.flush()
    return True
