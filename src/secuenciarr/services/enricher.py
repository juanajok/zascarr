"""
Enricher — completa metadatos de series e issues consultando fuentes externas.

Fuentes activas: Comic Vine (grapa americana/British) y AniList (manga/
manhwa/manhua). GCD y Tebeosfera quedan fuera a propósito: no tienen API
pública estable y su scraping es un proyecto en sí mismo. El enum
MetadataSource ya las contempla para cuando existan clientes propios.

Enrutado por Series.tradition: cada serie se enriquece con UNA sola fuente,
la que le corresponde (nunca se prueban las dos por si acaso — evitaría el
mismo error que el peer review señaló en el matcher: adivinar en vez de
aceptar solo lo inequívoco). Tradiciones sin fuente todavía (BD, tebeo,
fumetti...) no se tocan: ni Comic Vine ni AniList las indexan bien, y es
mejor no enriquecer que enriquecer con la fuente equivocada.

AniList enriquece SOLO a nivel de serie (título, sinopsis, portada, nº de
capítulos): no tiene un concepto de "issue" equivalente al de Comic Vine
—su staff/autoría es de la serie completa, no por capítulo— así que
Issue.metadata_source nunca se pone a 'anilist' en esta versión.

Reglas de convivencia con datos ya existentes (peer review, fix C3):
  - NUNCA se toca una fila con metadata_source == 'manual': es corrección
    humana y el enricher no pisa criterio humano.
  - NUNCA se sobrescribe un campo ya relleno; solo se completan huecos
    (None / cadena vacía). Si comicinfo_xml ya puso una sinopsis, se respeta.
  - Solo se marca metadata_source con la fuente que aportó el dato (no se
    reetiqueta lo que ya vino de comicinfo_xml).
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.core.matcher import normalize_title
from secuenciarr.models import (
    ComicTradition, Creator, CreatorRole, Issue, IssueCreator, MetadataSource, Series,
)
from secuenciarr.services.anilist import AniListClient, AniListResult
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

# Tradiciones que AniList cubre. El resto de no-americanas (BD, tebeo,
# fumetti) van a Comic Vine igualmente NO: se dejan sin tocar (ver docstring).
_ANILIST_TRADITIONS = {ComicTradition.MANGA, ComicTradition.MANHWA, ComicTradition.MANHUA}
_COMIC_VINE_TRADITIONS = {ComicTradition.AMERICAN, ComicTradition.BRITISH}

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


@dataclass
class SeriesMatch:
    """Resultado de match a nivel de serie, normalizado entre fuentes."""
    source_id: int
    description: str | None = None
    cover_url: str | None = None
    count_of_issues: int | None = None


class EnrichmentService:
    """Enriquecimiento incremental: cada llamada procesa un lote pequeño.

    Pensado para correr como job periódico (ver main.py), no como proceso
    batch de una sola vez: las APIs externas limitan a ~1 req/s y una
    biblioteca de miles de series tardaría horas en una sola pasada.
    Procesar en lotes pequeños y frecuentes converge igual sin bloquear
    nada más.
    """

    def __init__(self, db: AsyncSession, cv_client: ComicVineClient | None = None,
                 anilist_client: AniListClient | None = None):
        self.db = db
        self._injected_cv = cv_client            # para tests
        self._injected_anilist = anilist_client  # para tests

    async def enrich_pending(self, limit: int = 20) -> EnrichmentReport:
        report = EnrichmentReport()
        async with AsyncExitStack() as stack:
            cv_client = self._injected_cv or await stack.enter_async_context(ComicVineClient())
            anilist_client = self._injected_anilist or await stack.enter_async_context(AniListClient())
            await self._enrich_series_batch(cv_client, anilist_client, limit, report)
            await self._enrich_issues_batch(cv_client, limit, report)
        return report

    # ── Series ───────────────────────────────────────────────────────────

    async def _enrich_series_batch(self, cv_client: ComicVineClient, anilist_client: AniListClient,
                                    limit: int, report: EnrichmentReport) -> None:
        pending = (await self.db.execute(
            select(Series)
            .where(Series.comic_vine_id.is_(None))
            .where(Series.anilist_id.is_(None))
            .where(Series.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .limit(limit)
        )).scalars().all()

        for series in pending:
            source = self._source_for(series.tradition)
            if source is None:
                continue  # tradición sin fuente todavía (BD, tebeo, fumetti...)

            id_field, source_value, source_label = source
            try:
                if source_value == MetadataSource.ANILIST.value:
                    match = await self._find_anilist_match(anilist_client, series)
                else:
                    match = await self._find_cv_series_match(cv_client, series)
            except Exception:
                logger.exception("enricher.series_lookup_failed", series=series.title, source=source_label)
                report.errors.append(f"serie '{series.title}': error consultando {source_label}")
                continue

            if match is None:
                report.series_no_match.append(series.title)
                continue

            self._apply_series_match(series, match, id_field, source_value)
            await self.db.flush()
            report.series_enriched.append(series.title)
            logger.info("enricher.series_enriched", series=series.title,
                       source=source_label, source_id=match.source_id)

    @staticmethod
    def _source_for(tradition: ComicTradition) -> tuple[str, str, str] | None:
        """(campo de id, valor de metadata_source, etiqueta legible) o None
        si esa tradición no tiene fuente de enriquecimiento todavía."""
        if tradition in _ANILIST_TRADITIONS:
            return "anilist_id", MetadataSource.ANILIST.value, "AniList"
        if tradition in _COMIC_VINE_TRADITIONS:
            return "comic_vine_id", MetadataSource.COMIC_VINE.value, "Comic Vine"
        return None

    @staticmethod
    def _apply_series_match(series: Series, match: SeriesMatch, id_field: str, source_value: str) -> None:
        setattr(series, id_field, match.source_id)
        if not series.description:
            series.description = match.description
        if not series.cover_url:
            series.cover_url = match.cover_url
        if not series.total_issues and match.count_of_issues:
            series.total_issues = match.count_of_issues
        if series.metadata_source is None:
            series.metadata_source = source_value

    async def _find_cv_series_match(self, client: ComicVineClient, series: Series) -> SeriesMatch | None:
        """Solo acepta coincidencia de título normalizado exacto.

        El ranking de relevancia de /search/ de Comic Vine es una caja negra;
        aceptar el primer resultado sin más repetiría el error que el propio
        peer review señaló en el matcher (ambigüedad resuelta adivinando).
        Sin coincidencia exacta, se prefiere no enriquecer a enriquecer mal.
        """
        candidates = await client.search_series(series.title, limit=10)
        norm = normalize_title(series.title)
        matches = [c for c in candidates if normalize_title(c.name) == norm]
        chosen = self._pick_by_year(matches, series.start_year, lambda c: c.start_year)
        if chosen is None:
            return None
        return SeriesMatch(source_id=chosen.cv_id, description=chosen.description,
                           cover_url=chosen.image_url, count_of_issues=chosen.count_of_issues)

    async def _find_anilist_match(self, client: AniListClient, series: Series) -> SeriesMatch | None:
        """Mismo criterio conservador que Comic Vine: solo título exacto
        (romaji O inglés) tras normalizar. AniList no tiene "sort_title"
        separado, así que no hay desambiguación extra más allá del año."""
        candidates = await client.search_manga(series.title, limit=10)
        norm = normalize_title(series.title)
        matches = [
            c for c in candidates
            if norm in (normalize_title(c.title_romaji or ""), normalize_title(c.title_english or ""))
        ]
        chosen = self._pick_by_year(matches, series.start_year, lambda c: c.start_year)
        if chosen is None:
            return None
        return SeriesMatch(source_id=chosen.anilist_id, description=chosen.description,
                           cover_url=chosen.cover_url, count_of_issues=chosen.chapters)

    @staticmethod
    def _pick_by_year(matches: list, target_year: int | None, year_of):
        """Común a ambas fuentes: sin match exacto de título, nada; con uno
        solo, ese; con varios, el año de nuestra Series desempata (±1)."""
        if not matches:
            return None
        if len(matches) == 1 or not target_year:
            return matches[0]
        by_year = [c for c in matches if year_of(c) and abs(year_of(c) - target_year) <= _YEAR_TOLERANCE]
        return by_year[0] if by_year else matches[0]

    # ── Issues (solo Comic Vine: ver docstring del módulo) ────────────────

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
