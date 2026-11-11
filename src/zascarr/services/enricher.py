# ruff: noqa: E501
"""
Enricher — completa metadatos de series e issues consultando fuentes externas.

Fuentes activas: Comic Vine (grapa americana/British), AniList (manga/
manhwa/manhua) y Tebeosfera (tebeo/franco_belgian — grapa/álbum en
español, confirmado con búsquedas reales, no solo supuesto). GCD queda
fuera a propósito: no tiene API pública ni una referencia de scraping ya
identificada. El enum MetadataSource ya la contempla para cuando exista
un cliente propio.

Enrutado por Series.tradition: cada serie se enriquece con UNA sola fuente,
la que le corresponde (nunca se prueban varias por si acaso — evitaría el
mismo error que el peer review señaló en el matcher: adivinar en vez de
aceptar solo lo inequívoco). Tradiciones sin fuente todavía (fumetti...)
no se tocan: ninguna fuente activa las indexa con confianza, y es mejor
no enriquecer que enriquecer con la fuente equivocada.

AniList y Tebeosfera enriquecen SOLO a nivel de serie (título, sinopsis,
portada, nº de números/capítulos): ninguna de las dos tiene aquí un
concepto de "issue" equivalente al de Comic Vine — así que
Issue.metadata_source nunca se pone a 'anilist' ni 'tebeosfera' en esta
versión; _enrich_issues_batch sigue siendo solo Comic Vine.

Reglas de convivencia con datos ya existentes (peer review, fix C3):
  - NUNCA se toca una fila con metadata_source == 'manual': es corrección
    humana y el enricher no pisa criterio humano.
  - NUNCA se sobrescribe un campo ya relleno; solo se completan huecos
    (None / cadena vacía). Si comicinfo_xml ya puso una sinopsis, se respeta.
  - Solo se marca metadata_source con la fuente que aportó el dato (no se
    reetiqueta lo que ya vino de comicinfo_xml).
  - NUNCA se empareja por título una serie que ya tiene una identidad externa
    elegida (comic_vine_id, anilist_id, tebeosfera_slug o gcd_id): la igualdad de
    título no prueba que sea la misma edición. Asociarle otra fuente es una
    acción explícita y confirmada, que no existe todavía.

AC-22 (#565, decisión PO de 2026-11-11 pese a D-7): los clientes piden los
campos que su API documenta en la MISMA petición: AniList solo `genres` en su
GraphQL (sus personajes no se usan) y Comic Vine
`character_credits`/`story_arc_credits` en la búsqueda de número (Comic Vine
**no** expone `genres` en volumen/issue: no se pide). El enricher rellena
`Series.genres` e `Issue.characters` solo si están vacíos y no bloqueados; no
sustituye datos existentes ni toca `metadata_source` de filas manuales. Tebeosfera
no declara género y no se inventa; GCD no tiene cliente aquí. Los
`story_arc_credits` se piden y se documentan, pero NO se persisten: `StoryArc`
no tiene una relación inequívoca serie↔arco en el modelo actual y AC-22 no pide
crear una relación nueva.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import (
    Character,
    ComicTradition,
    Creator,
    CreatorRole,
    Genre,
    Issue,
    IssueCreator,
    MetadataSource,
    Series,
    issue_characters,
    series_genres,
)
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient, CVCredit
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada

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

# Tradiciones que cubre cada fuente. El resto (fumetti...) se deja sin
# tocar: ver docstring del módulo.
_ANILIST_TRADITIONS = {ComicTradition.MANGA, ComicTradition.MANHWA, ComicTradition.MANHUA}
_TEBEOSFERA_TRADITIONS = {ComicTradition.TEBEO, ComicTradition.FRANCO_BELGIAN}
_COMIC_VINE_TRADITIONS = {ComicTradition.AMERICAN, ComicTradition.BRITISH}

# Desambiguación por año como en matcher.py: ±1 absorbe discrepancias de
# "año de la serie" vs "año del primer número" entre fuentes.
_YEAR_TOLERANCE = 1

# H2 (peer review v2): antes, una serie/issue sin match entraba en el batch
# en CADA ciclo para siempre, quemando rate limit de APIs externas en
# búsquedas condenadas. enrichment_attempted_at marca "lo intentamos" (con o
# sin match) y esto es cuánto se espera antes de reintentar — no en el
# siguiente ciclo (cada pocos minutos), sino a plazo largo: una fuente puede
# indexar una serie recién publicada con retraso.
ENRICHMENT_RETRY_AFTER = timedelta(days=30)


def _nombres_de_detalle(valores: object) -> list[str]:
    """Nombres de `character_credits`/`story_arc_credits` de la respuesta de CV."""
    salida: list[str] = []
    for item in valores or []:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("name") or "").strip()
        if nombre:
            salida.append(nombre)
    return salida


def _nombres_limpios(valores: list[str], *, maximo: int) -> list[str]:
    """Nombres no vacíos, recortados al tope y sin duplicados por caja."""
    salida: list[str] = []
    vistos: set[str] = set()
    for valor in valores:
        nombre = str(valor or "").strip()
        if not nombre:
            continue
        nombre = nombre[:maximo]
        clave = nombre.casefold()
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(nombre)
    return salida


def puede_enlazarse_con_comic_vine(series: Series, comic_vine_activo: bool) -> bool:
    """¿Puede el enriquecedor enlazar esta serie con Comic Vine? Es LA condición de `_enrich_series_batch` (sin
    identidad externa elegida, `metadata_source` distinto de `manual`, tradición con Comic Vine como fuente y la fuente
    activa) para que la ficha no repita una copia. No incluye el plazo de reintento (30 días): es «puede llegar a ser»."""
    return bool(
        comic_vine_activo
        and series.comic_vine_id is None
        and series.anilist_id is None
        and series.tebeosfera_slug is None
        and series.gcd_id is None
        and series.metadata_source != MetadataSource.MANUAL.value
        and series.tradition in _COMIC_VINE_TRADITIONS
    )


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
    """Resultado de match a nivel de serie, normalizado entre fuentes.

    source_id es int para Comic Vine/AniList pero str para Tebeosfera
    (slug de texto, no ID numérico) — de ahí el tipo unión.
    """
    source_id: int | str
    description: str | None = None
    cover_url: str | None = None
    count_of_issues: int | None = None
    #: Géneros declarados por la fuente en la MISMA búsqueda (vacío si no los declara).
    genres: list[str] = field(default_factory=list)


class EnrichmentService:
    """Enriquecimiento incremental: cada llamada procesa un lote pequeño.

    Pensado para correr como job periódico (ver main.py), no como proceso
    batch de una sola vez: las APIs externas limitan a ~1 req/s y una
    biblioteca de miles de series tardaría horas en una sola pasada.
    Procesar en lotes pequeños y frecuentes converge igual sin bloquear
    nada más.
    """

    def __init__(self, db: AsyncSession, cv_client: ComicVineClient | None = None,
                 anilist_client: AniListClient | None = None,
                 tebeosfera_client: TebeosferaClient | None = None):
        self.db = db
        self._injected_cv = cv_client                  # para tests
        self._injected_anilist = anilist_client        # para tests
        self._injected_tebeosfera = tebeosfera_client  # para tests

    async def enrich_pending(self, limit: int = 20) -> EnrichmentReport:
        report = EnrichmentReport()
        settings = get_settings()
        async with AsyncExitStack() as stack:
            cv_client = self._injected_cv if settings.comicvine_enabled else None
            if cv_client is None and settings.comicvine_enabled:
                cv_client = await stack.enter_async_context(ComicVineClient())
            anilist_client = self._injected_anilist if settings.anilist_enabled else None
            if anilist_client is None and settings.anilist_enabled:
                anilist_client = await stack.enter_async_context(AniListClient())
            tebeosfera_client = self._injected_tebeosfera if settings.tebeosfera_enabled else None
            if tebeosfera_client is None and settings.tebeosfera_enabled:
                tebeosfera_client = await stack.enter_async_context(TebeosferaClient())
            await self._enrich_series_batch(
                cv_client, anilist_client, tebeosfera_client, limit, report
            )
            await self._enrich_issues_batch(cv_client, limit, report)
            await self._backfill_generos_anilist(anilist_client, limit, report)
            await self._backfill_personajes_cv(cv_client, limit, report)
        return report

    # ── Backfill de identidad estructurada (#565 task-171) ───────────────

    async def _backfill_generos_anilist(self, client: AniListClient | None, limit: int,
                                        report: EnrichmentReport) -> None:
        """Rellena géneros de series ya identificadas con AniList que siguen vacías.

        Acotado por `limit`, idempotente y solo para filas no manuales. La marca
        en `metadata_` evita repetir la petición cada ciclo si la fuente no
        declara géneros; no hay migración.
        """
        if client is None:
            return
        sin_generos = ~exists().where(series_genres.c.series_id == Series.id)
        filas = (await self.db.execute(
            select(Series)
            .where(Series.anilist_id.is_not(None))
            .where(Series.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .where(~Series.locked_fields.contains(["genres"]))
            .where(sin_generos)
            .where(~Series.metadata_.has_key("etq3_generos_intentado"))
            .limit(limit)
        )).scalars().all()
        for series in filas:
            if "genres" in (series.locked_fields or []):
                continue
            try:
                detalle = await client.get_manga(int(series.anilist_id))
            except Exception:
                logger.exception("enricher.generos_backfill_failed", series=series.title)
                report.errors.append(f"serie {series.title}: error pidiendo géneros")
                continue
            series.metadata_ = {**(series.metadata_ or {}), "etq3_generos_intentado": True}
            if detalle is not None:
                await self._aplicar_generos(series, detalle.genres)
            await self.db.flush()

    async def _backfill_personajes_cv(self, client: ComicVineClient | None, limit: int,
                                      report: EnrichmentReport) -> None:
        """Rellena personajes de números ya identificados con Comic Vine y vacíos."""
        if client is None:
            return
        sin_personajes = ~exists().where(issue_characters.c.issue_id == Issue.id)
        filas = (await self.db.execute(
            select(Issue)
            .where(Issue.comic_vine_id.is_not(None))
            .where(Issue.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .where(~Issue.locked_fields.contains(["characters"]))
            .where(sin_personajes)
            .where(~Issue.metadata_.has_key("etq3_personajes_intentado"))
            .limit(limit)
        )).scalars().all()
        for issue in filas:
            if "characters" in (issue.locked_fields or []):
                continue
            label = f"{issue.issue_number} (cv {issue.comic_vine_id})"
            try:
                detalle = await client.get_issue_detail(int(issue.comic_vine_id))
            except Exception:
                logger.exception("enricher.personajes_backfill_failed", issue=label)
                report.errors.append(f"issue {label}: error pidiendo personajes")
                continue
            issue.metadata_ = {**(issue.metadata_ or {}), "etq3_personajes_intentado": True}
            await self._aplicar_personajes(issue, _nombres_de_detalle(detalle.get("character_credits")))
            await self.db.flush()

    # ── Series ───────────────────────────────────────────────────────────

    async def _enrich_series_batch(self, cv_client: ComicVineClient, anilist_client: AniListClient,
                                    tebeosfera_client: TebeosferaClient, limit: int,
                                    report: EnrichmentReport) -> None:
        # B8: excluir ANTES del LIMIT las tradiciones cuya fuente está
        # desactivada (cliente None). Si no, p. ej. 20 mangas con AniList
        # apagada acapararían el lote y dejarían sin turno a un tebeo activo.
        desactivadas: list[ComicTradition] = []
        if cv_client is None:
            desactivadas.extend(_COMIC_VINE_TRADITIONS)
        if anilist_client is None:
            desactivadas.extend(_ANILIST_TRADITIONS)
        if tebeosfera_client is None:
            desactivadas.extend(_TEBEOSFERA_TRADITIONS)

        stmt = (
            select(Series)
            .where(Series.comic_vine_id.is_(None))
            .where(Series.anilist_id.is_(None))
            .where(Series.tebeosfera_slug.is_(None))
            # Con identidad GCD elegida ya está identificada: que otra fuente coincida por
            # TÍTULO no prueba que sea la misma edición. Asociarle otra fuente es una acción
            # explícita y confirmada, no un emparejamiento automático.
            .where(Series.gcd_id.is_(None))
            .where(Series.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .where(or_(
                Series.enrichment_attempted_at.is_(None),
                Series.enrichment_attempted_at < datetime.now(UTC) - ENRICHMENT_RETRY_AFTER,
            ))
        )
        if desactivadas:
            stmt = stmt.where(Series.tradition.not_in(desactivadas))
        pending = (await self.db.execute(stmt.limit(limit))).scalars().all()

        for series in pending:
            source = self._source_for(series.tradition)
            if source is None:
                # Tradición sin fuente (fumetti/other): no hay API que
                # consultar, pero se marca el intento para que la caché
                # negativa (H2) no la re-seleccione en cada ciclo y acapare
                # el lote en detrimento de series sí enriquecibles (ADR-0002).
                series.enrichment_attempted_at = datetime.now(UTC)
                continue

            id_field, source_value, source_label = source
            cliente = (
                anilist_client if source_value == MetadataSource.ANILIST.value
                else tebeosfera_client if source_value == MetadataSource.TEBEOSFERA.value
                else cv_client
            )
            if cliente is None:
                # B8: fuente desactivada → cero tráfico y no se marca el
                # intento (no consume el plazo de reintento de 30 días).
                continue
            try:
                if source_value == MetadataSource.ANILIST.value:
                    match = await self._find_anilist_match(cliente, series)
                elif source_value == MetadataSource.TEBEOSFERA.value:
                    match = await self._find_tebeosfera_match(cliente, series)
                else:
                    match = await self._find_cv_series_match(cliente, series)
            except (CortesiaEnEspera, FuenteApagada) as exc:
                # AC-16: una fuente sin turno (espera o apagada) no es un fallo ni consume los
                # 30 días de la caché negativa: se omite esa fuente en este ciclo.
                logger.info("enricher.source_sin_turno", source=source_label,
                            motivo=getattr(exc, "motivo", "apagada"))
                continue
            except Exception:
                # No se marca enrichment_attempted_at: un fallo de red es
                # transitorio y debe poder reintentarse en el próximo ciclo,
                # no dentro de 30 días como un "no encontrado" genuino.
                logger.exception(
                    "enricher.series_lookup_failed", series=series.title, source=source_label
                )
                report.errors.append(f"serie '{series.title}': error consultando {source_label}")
                continue

            # H2: se marca el intento tanto si hay match como si no.
            if match is None:
                series.enrichment_attempted_at = datetime.now(UTC)
                report.series_no_match.append(series.title)
                continue

            # H9 (#129 B): reclamar la identidad con un UPDATE condicional. Si otra
            # operación (p. ej. una asociación confirmada) ya la escribió, rowcount=0 y
            # NO se tocan ni el id ni los metadatos de esa serie. En ese caso tampoco se
            # marca `enrichment_attempted_at`: esa serie ya no es nuestra.
            if id_field in (series.locked_fields or []):
                self._apply_series_match(series, match, id_field, source_value)
                series.enrichment_attempted_at = datetime.now(UTC)
            else:
                reclamada = await self.db.execute(
                    update(Series).where(Series.id == series.id,
                                         getattr(Series, id_field).is_(None))
                    .values({id_field: match.source_id})
                    .execution_options(synchronize_session="fetch"))
                if reclamada.rowcount != 1:
                    logger.info("enricher.identity_claimed", series=series.title,
                                source=source_label)
                    continue
                series.enrichment_attempted_at = datetime.now(UTC)
                self._apply_series_match(series, match, id_field, source_value)
            await self._aplicar_generos(series, match.genres)
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
        if tradition in _TEBEOSFERA_TRADITIONS:
            return "tebeosfera_slug", MetadataSource.TEBEOSFERA.value, "Tebeosfera"
        if tradition in _COMIC_VINE_TRADITIONS:
            return "comic_vine_id", MetadataSource.COMIC_VINE.value, "Comic Vine"
        return None

    @staticmethod
    def _apply_series_match(
        series: Series, match: SeriesMatch, id_field: str, source_value: str
    ) -> None:
        # H3 (peer review v2): locked_fields protege campos concretos aunque
        # metadata_source no sea 'manual' (ese caso ya lo excluye la query
        # de _enrich_series_batch, que es bloqueo total, no granular).
        locked = series.locked_fields or []
        if id_field not in locked:
            setattr(series, id_field, match.source_id)
        if "description" not in locked and not series.description:
            series.description = match.description
        if "cover_url" not in locked and not series.cover_url:
            series.cover_url = match.cover_url
        if "total_issues" not in locked and not series.total_issues and match.count_of_issues:
            series.total_issues = match.count_of_issues
        if series.metadata_source is None:
            series.metadata_source = source_value

    async def _find_cv_series_match(
        self, client: ComicVineClient, series: Series
    ) -> SeriesMatch | None:
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

    async def _find_anilist_match(
        self, client: AniListClient, series: Series
    ) -> SeriesMatch | None:
        """Mismo criterio conservador que Comic Vine: solo título exacto
        (romaji O inglés) tras normalizar. AniList no tiene "sort_title"
        separado, así que no hay desambiguación extra más allá del año."""
        candidates = await client.search_manga(series.title, limit=10)
        norm = normalize_title(series.title)
        matches = [
            c
            for c in candidates
            if norm
            in (normalize_title(c.title_romaji or ""), normalize_title(c.title_english or ""))
        ]
        chosen = self._pick_by_year(matches, series.start_year, lambda c: c.start_year)
        if chosen is None:
            return None
        return SeriesMatch(source_id=chosen.anilist_id, description=chosen.description,
                           cover_url=chosen.cover_url, count_of_issues=chosen.chapters,
                           genres=list(chosen.genres))

    async def _find_tebeosfera_match(
        self, client: TebeosferaClient, series: Series
    ) -> SeriesMatch | None:
        """Mismo criterio conservador: solo título exacto tras normalizar.

        TebeosferaClient ya limpia el sufijo "(año, editorial)" que el
        sitio concatena a cada resultado (ver tebeosfera.py), así que el
        título recibido aquí ya es comparable directamente contra
        Series.title. Sin sort_title propio, igual que AniList.
        """
        candidates = await client.search_series(series.title, limit=10)
        norm = normalize_title(series.title)
        matches = [c for c in candidates if normalize_title(c.title) == norm]
        chosen = self._pick_by_year(matches, series.start_year, lambda c: c.start_year)
        if chosen is None:
            return None
        return SeriesMatch(source_id=chosen.slug, description=chosen.description,
                           cover_url=chosen.cover_url, count_of_issues=chosen.count_of_issues)

    @staticmethod
    def _pick_by_year(matches: list, target_year: int | None, year_of):
        """Común a ambas fuentes: sin match exacto de título, nada; con uno
        solo, ese; con varios, el año de nuestra Series desempata (±1)."""
        if not matches:
            return None
        if len(matches) == 1 or not target_year:
            return matches[0]
        by_year = [
            c for c in matches if year_of(c) and abs(year_of(c) - target_year) <= _YEAR_TOLERANCE
        ]
        return by_year[0] if by_year else matches[0]

    # ── Issues (solo Comic Vine: ver docstring del módulo) ────────────────

    async def _enrich_issues_batch(self, client: ComicVineClient, limit: int,
                                    report: EnrichmentReport) -> None:
        if client is None:
            # B8: Comic Vine desactivada → los issues solo se enriquecen vía CV.
            return
        rows = (await self.db.execute(
            select(Issue, Series)
            .join(Series, Issue.series_id == Series.id)
            .where(Series.comic_vine_id.is_not(None))
            .where(Issue.comic_vine_id.is_(None))
            .where(Issue.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .where(Issue.issue_number.is_not(None))
            .where(or_(
                Issue.enrichment_attempted_at.is_(None),
                Issue.enrichment_attempted_at < datetime.now(UTC) - ENRICHMENT_RETRY_AFTER,
            ))
            .limit(limit)
        )).all()

        for issue, series in rows:
            label = f"{series.title} #{issue.issue_number}"
            try:
                match = await client.find_issue(series.comic_vine_id, issue.issue_number)
            except (CortesiaEnEspera, FuenteApagada) as exc:
                logger.info("enricher.source_sin_turno", source="comic_vine",
                            motivo=getattr(exc, "motivo", "apagada"))
                continue
            except Exception:
                # Igual que en series: fallo transitorio, no cuenta como
                # intento para la caché negativa de 30 días.
                logger.exception("enricher.issue_lookup_failed", issue=label)
                report.errors.append(f"issue {label}: error consultando Comic Vine")
                continue

            issue.enrichment_attempted_at = datetime.now(UTC)  # H2

            if match is None:
                report.issues_no_match.append(label)
                continue

            # H3: locked_fields protege la asignación manual desde la
            # bandeja de pendientes (review.py) sin bloquear el resto del
            # contenido — ver ReviewService.assign_to_series.
            locked = issue.locked_fields or []
            if "comic_vine_id" not in locked:
                issue.comic_vine_id = match.cv_id
            if "synopsis" not in locked and not issue.synopsis:
                issue.synopsis = match.description
            if "cover_url" not in locked and not issue.cover_url:
                issue.cover_url = match.image_url
            if issue.metadata_source is None:
                issue.metadata_source = MetadataSource.COMIC_VINE.value
            await self._apply_credits(issue, match.credits)
            await self._aplicar_personajes(issue, match.characters)
            await self.db.flush()
            report.issues_enriched.append(label)
            logger.info("enricher.issue_enriched", issue=label, cv_id=match.cv_id)

    async def _aplicar_generos(self, series: Series, generos: list[str]) -> int:
        """Puebla `Series.genres` solo si está vacío, no bloqueado y no es manual.

        No crea etiquetas ni toca B6; los géneros son la relación estructurada
        existente. Si la fuente no declara géneros, no se toca nada.
        """
        if not generos or "genres" in (series.locked_fields or []):
            return 0
        ya = (await self.db.execute(
            select(series_genres.c.genre_id).where(series_genres.c.series_id == series.id)
        )).first()
        if ya is not None:
            return 0
        creados = 0
        for nombre in _nombres_limpios(generos, maximo=100):
            genero = (await self.db.execute(
                select(Genre).where(func.lower(Genre.name) == nombre.casefold())
            )).scalar_one_or_none()
            if genero is None:
                genero = Genre(name=nombre)
                self.db.add(genero)
                await self.db.flush()
                creados += 1
            await self.db.execute(series_genres.insert().values(
                series_id=series.id, genre_id=genero.id))
            creados += 1
        return creados

    async def _aplicar_personajes(self, issue: Issue, personajes: list[str]) -> int:
        """Puebla `Issue.characters` solo si está vacío y no bloqueado; nombres tal cual."""
        if not personajes or "characters" in (issue.locked_fields or []):
            return 0
        ya = (await self.db.execute(
            select(issue_characters.c.character_id).where(issue_characters.c.issue_id == issue.id)
        )).first()
        if ya is not None:
            return 0
        creados = 0
        for nombre in _nombres_limpios(personajes, maximo=255):
            personaje = (await self.db.execute(
                select(Character).where(func.lower(Character.name) == nombre.casefold())
            )).scalar_one_or_none()
            if personaje is None:
                personaje = Character(name=nombre)
                self.db.add(personaje)
                await self.db.flush()
                creados += 1
            await self.db.execute(issue_characters.insert().values(
                issue_id=issue.id, character_id=personaje.id, is_main=False))
            creados += 1
        return creados

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
