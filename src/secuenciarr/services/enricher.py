"""
Enricher — completa metadatos de series e issues consultando Comic Vine.

Alcance de esta primera versión: SOLO Comic Vine (cubre grapa americana y
British). GCD, AniList y Tebeosfera quedan fuera a propósito: no tienen API
pública estable y su scraping es un proyecto en sí mismo. El enum
MetadataSource ya las contempla para cuando existan clientes propios — este
módulo no necesita cambiar para que se añadan, solo se suman más "batches".

Reglas de convivencia con datos ya existentes (peer review, fix C3):
  - NUNCA se toca una fila con metadata_source == 'manual': es corrección
    humana y el enricher no pisa criterio humano.
  - NUNCA se sobrescribe un campo ya relleno; solo se completan huecos
    (None / cadena vacía). Si comicinfo_xml ya puso una sinopsis, se respeta.
  - Solo se marca metadata_source='comic_vine' cuando el enricher es quien
    ha aportado el dato (no se reetiqueta lo que ya vino de comicinfo_xml).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.core.matcher import normalize_title
from secuenciarr.models import Creator, CreatorRole, Issue, IssueCreator, MetadataSource, Series
from secuenciarr.services.comic_vine import ComicVineClient, CVCredit, CVResult

logger = structlog.get_logger()

# Roles de Comic Vine que sabemos mapear a CreatorRole. El resto de roles en
# texto libre que devuelve la API ("plotter", "cover" ambiguo, etc.) se
# ignoran en vez de adivinar un enum incorrecto.
_CV_ROLE_MAP: dict[str, CreatorRole] = {
    "writer": CreatorRole.WRITER,
    "penciler": CreatorRole.PENCILER,
    "penciller": CreatorRole.PENCILER,
    "inker": CreatorRole.INKER,
    "colorist": CreatorRole.COLORIST,
    "letterer": CreatorRole.LETTERER,
    "cover": CreatorRole.COVER_ARTIST,
    "editor": CreatorRole.EDITOR,
    "translator": CreatorRole.TRANSLATOR,
}

# Desambiguación por año como en matcher.py: ±1 absorbe discrepancias de
# "año de la serie" vs "año del primer número" entre fuentes.
_YEAR_TOLERANCE = 1


@dataclass
class EnrichmentReport:
    series_enriched: list[str] = field(default_factory=list)
    series_no_match: list[str] = field(default_factory=list)
    issues_enriched: list[str] = field(default_factory=list)
    issues_no_match: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_enriched(self) -> int:
        return len(self.series_enriched) + len(self.issues_enriched)


class EnrichmentService:
    """Enriquecimiento incremental: cada llamada procesa un lote pequeño.

    Pensado para correr como job periódico (ver main.py), no como proceso
    batch de una sola vez: Comic Vine limita a ~1 req/s y una biblioteca de
    miles de series tardaría horas en una sola pasada. Procesar en lotes
    pequeños y frecuentes converge igual sin bloquear nada más.
    """

    def __init__(self, db: AsyncSession, cv_client: ComicVineClient | None = None):
        self.db = db
        self._injected_client = cv_client  # para tests: evita el context manager real

    async def enrich_pending(self, limit: int = 20) -> EnrichmentReport:
        report = EnrichmentReport()
        if self._injected_client is not None:
            await self._run(self._injected_client, limit, report)
        else:
            async with ComicVineClient() as client:
                await self._run(client, limit, report)
        return report

    async def _run(self, client: ComicVineClient, limit: int, report: EnrichmentReport) -> None:
        await self._enrich_series_batch(client, limit, report)
        await self._enrich_issues_batch(client, limit, report)

    # ── Series ───────────────────────────────────────────────────────────

    async def _enrich_series_batch(self, client: ComicVineClient, limit: int,
                                    report: EnrichmentReport) -> None:
        pending = (await self.db.execute(
            select(Series)
            .where(Series.comic_vine_id.is_(None))
            .where(Series.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .limit(limit)
        )).scalars().all()

        for series in pending:
            try:
                match = await self._find_series_match(client, series)
            except Exception:
                logger.exception("enricher.series_lookup_failed", series=series.title)
                report.errors.append(f"serie '{series.title}': error consultando Comic Vine")
                continue

            if match is None:
                report.series_no_match.append(series.title)
                continue

            series.comic_vine_id = match.cv_id
            if not series.description:
                series.description = match.description
            if not series.cover_url:
                series.cover_url = match.image_url
            if not series.total_issues and match.count_of_issues:
                series.total_issues = match.count_of_issues
            if series.metadata_source is None:
                series.metadata_source = MetadataSource.COMIC_VINE.value
            await self.db.flush()
            report.series_enriched.append(series.title)
            logger.info("enricher.series_enriched", series=series.title, cv_id=match.cv_id)

    async def _find_series_match(self, client: ComicVineClient, series: Series) -> CVResult | None:
        """Solo acepta coincidencia de título normalizado exacto.

        El ranking de relevancia de /search/ de Comic Vine es una caja negra;
        aceptar el primer resultado sin más repetiría el error que el propio
        peer review señaló en el matcher (ambigüedad resuelta adivinando).
        Sin coincidencia exacta, se prefiere no enriquecer a enriquecer mal.
        """
        candidates = await client.search_series(series.title, limit=10)
        norm = normalize_title(series.title)
        matches = [c for c in candidates if normalize_title(c.name) == norm]
        if not matches:
            return None
        if len(matches) == 1 or not series.start_year:
            return matches[0]
        by_year = [c for c in matches
                   if c.start_year and abs(c.start_year - series.start_year) <= _YEAR_TOLERANCE]
        return by_year[0] if by_year else matches[0]

    # ── Issues ───────────────────────────────────────────────────────────

    async def _enrich_issues_batch(self, client: ComicVineClient, limit: int,
                                    report: EnrichmentReport) -> None:
        rows = (await self.db.execute(
            select(Issue, Series)
            .join(Series, Issue.series_id == Series.id)
            .where(Series.comic_vine_id.is_not(None))
            .where(Issue.comic_vine_id.is_(None))
            .where(Issue.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .where(Issue.issue_number.is_not(None))
            .limit(limit)
        )).all()

        for issue, series in rows:
            label = f"{series.title} #{issue.issue_number}"
            try:
                match = await client.find_issue(series.comic_vine_id, issue.issue_number)
            except Exception:
                logger.exception("enricher.issue_lookup_failed", issue=label)
                report.errors.append(f"issue {label}: error consultando Comic Vine")
                continue

            if match is None:
                report.issues_no_match.append(label)
                continue

            issue.comic_vine_id = match.cv_id
            if not issue.synopsis:
                issue.synopsis = match.description
            if not issue.cover_url:
                issue.cover_url = match.image_url
            if issue.metadata_source is None:
                issue.metadata_source = MetadataSource.COMIC_VINE.value
            await self._apply_credits(issue, match.credits)
            await self.db.flush()
            report.issues_enriched.append(label)
            logger.info("enricher.issue_enriched", issue=label, cv_id=match.cv_id)

    async def _apply_credits(self, issue: Issue, credits: list[CVCredit]) -> None:
        """Añade créditos SOLO si el issue no tiene ninguno todavía.

        Se consulta issue_creators directamente en vez de `issue.credits`:
        tocar una relación lazy sobre un objeto de AsyncSession sin haberla
        cargado explícitamente dispara IO síncrono oculto (MissingGreenlet).
        """
        existing = (await self.db.execute(
            select(IssueCreator).where(IssueCreator.issue_id == issue.id)
        )).scalars().first()
        if existing:
            return

        seen: set[tuple[str, CreatorRole]] = set()
        for credit in credits:
            role = None
            for role_text in credit.roles:
                role = _CV_ROLE_MAP.get(role_text)
                if role is None:
                    continue
                creator = await self._get_or_create_creator(credit)
                key = (creator.id, role)
                if key in seen:
                    continue
                seen.add(key)
                self.db.add(IssueCreator(issue_id=issue.id, creator_id=creator.id, role=role))

    async def _get_or_create_creator(self, credit: CVCredit) -> Creator:
        if credit.cv_id:
            existing = (await self.db.execute(
                select(Creator).where(Creator.comic_vine_id == credit.cv_id)
            )).scalar_one_or_none()
            if existing:
                return existing

        existing = (await self.db.execute(
            select(Creator).where(Creator.name == credit.name)
        )).scalar_one_or_none()
        if existing:
            if credit.cv_id and not existing.comic_vine_id:
                existing.comic_vine_id = credit.cv_id
            return existing

        creator = Creator(
            name=credit.name,
            comic_vine_id=credit.cv_id,
            metadata_source=MetadataSource.COMIC_VINE.value,
        )
        self.db.add(creator)
        await self.db.flush()
        return creator
