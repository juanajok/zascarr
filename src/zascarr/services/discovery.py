"""
DiscoveryService — C0: buscar series en fuentes externas y darlas de alta.

Cierra el círculo vicioso confirmado en producción: Wishlist
(WishlistService.search_series) y el matcher (core/matcher.py) SOLO
trabajan contra `Series` que YA existen en la BD local — en una
instalación nueva (tabla `series` vacía) no hay nada que buscar ni con
qué emparejar un archivo bien nombrado. Este servicio es el paso de alta
que falta: busca en las mismas fuentes que ya usa el enricher (Comic
Vine, AniList, Tebeosfera) — las REUTILIZA para buscar, nunca las toca
para nada de descarga — y da de alta la `Series` local que el resto del
sistema necesita para funcionar.

Un fallo de una fuente (sin API key, sitio caído, rate limit agotado) no
tumba la búsqueda entera: se registra y se sigue con las demás — mismo
criterio de tolerancia a fallos que enricher.py.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.gcd import GCDClient
from zascarr.services.tebeosfera import TebeosferaClient

logger = structlog.get_logger()

# Traducción fuente → columna de identidad externa en Series. Cada serie
# solo lleva UNA de las cuatro (igual que en enricher.py): la que
# corresponde a la fuente donde se encontró.
_EXTERNAL_ID_FIELD: dict[MetadataSource, str] = {
    MetadataSource.COMIC_VINE: "comic_vine_id",
    MetadataSource.ANILIST: "anilist_id",
    MetadataSource.TEBEOSFERA: "tebeosfera_slug",
    MetadataSource.GCD: "gcd_id",
}
_TEXT_ID_FIELDS = {"tebeosfera_slug"}


@dataclass
class DiscoveryResult:
    source: MetadataSource
    external_id: str  # texto siempre: unifica el int de CV/AniList y el slug de Tebeosfera
    title: str
    start_year: int | None
    description: str | None
    cover_url: str | None
    # Enlace a la ficha real en la fuente (bug real, reportado: sin esto no
    # hay forma de confirmar CUÁL de varias ediciones/resultados similares
    # es la correcta antes de darla de alta — un "Thorgal" en Tebeosfera
    # son 10 ediciones españolas distintas, cada una con su propia ficha).
    site_url: str | None
    # Punto de partida editable en el formulario de alta, NO una asignación
    # definitiva: Comic Vine también indexa BRITISH, Tebeosfera también
    # indexa FRANCO_BELGIAN. El coleccionista corrige antes de confirmar.
    tradition_guess: ComicTradition


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, limit: int = 10) -> tuple[list[DiscoveryResult], list[str]]:
        """Devuelve (resultados, avisos). Los avisos son texto en español
        listo para mostrar — bug real reportado: sin esto, "Comic Vine no
        devuelve nada" era indistinguible de "no está configurado" (sin
        COMICVINE_API_KEY), y el coleccionista no tenía forma de saberlo."""
        query = query.strip()
        if not query:
            return [], []

        avisos: list[str] = []
        if not get_settings().comicvine_api_key:
            avisos.append(
                "Comic Vine no está configurado — añade COMICVINE_API_KEY en tu .env "
                "para incluirlo en la búsqueda."
            )

        fuentes = (
            ("Comic Vine", self._search_comic_vine(query, limit)),
            ("AniList", self._search_anilist(query, limit)),
            ("Tebeosfera", self._search_tebeosfera(query, limit)),
            ("GCD", self._search_gcd(query, limit)),
        )
        outcomes = await asyncio.gather(*(coro for _, coro in fuentes), return_exceptions=True)

        results: list[DiscoveryResult] = []
        for (nombre, _), outcome in zip(fuentes, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                logger.warning("discovery.source_failed", source=nombre, error=str(outcome))
                avisos.append(f"{nombre}: no se pudo consultar ahora mismo.")
                continue
            results.extend(outcome)
        return results, avisos

    async def _search_comic_vine(self, query: str, limit: int) -> list[DiscoveryResult]:
        # Sin API key, la petición está condenada (401) — no la intentamos.
        if not get_settings().comicvine_api_key:
            return []
        async with ComicVineClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.COMIC_VINE, external_id=str(h.cv_id),
                title=h.name, start_year=h.start_year, description=h.description,
                cover_url=h.image_url, site_url=h.site_url,
                tradition_guess=ComicTradition.AMERICAN,
            )
            for h in hits
        ]

    async def _search_anilist(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with AniListClient() as client:
            hits = await client.search_manga(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.ANILIST, external_id=str(h.anilist_id),
                title=h.title_romaji or h.title_english or "?",
                start_year=h.start_year, description=h.description,
                cover_url=h.cover_url, site_url=h.site_url,
                tradition_guess=ComicTradition.MANGA,
            )
            for h in hits
        ]

    async def _search_tebeosfera(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with TebeosferaClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.TEBEOSFERA, external_id=h.slug,
                title=h.title, start_year=h.start_year, description=h.description,
                cover_url=h.cover_url, site_url=h.site_url,
                tradition_guess=ComicTradition.TEBEO,
            )
            for h in hits
        ]

    async def _search_gcd(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with GCDClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.GCD, external_id=str(h.gcd_id),
                title=h.name, start_year=h.year_began,
                # La API de búsqueda de GCD no trae sinopsis ni portada a
                # nivel de serie (solo datos bibliográficos) — ver
                # docstring de services/gcd.py.
                description=None, cover_url=None, site_url=h.site_url,
                tradition_guess=ComicTradition(h.tradition_guess),
            )
            for h in hits
        ]

    async def get_or_create_series(
        self,
        source: MetadataSource,
        external_id: str,
        title: str,
        tradition: ComicTradition,
        start_year: int | None = None,
        description: str | None = None,
        cover_url: str | None = None,
    ) -> tuple[Series, bool]:
        """Devuelve (serie, creada). Nunca duplica: si el ID externo ya
        está registrado (búsqueda repetida, o ya se importó antes por otra
        vía), reutiliza la fila existente en vez de violar el UNIQUE."""
        field = _EXTERNAL_ID_FIELD.get(source)
        if field is None:
            raise ValueError(f"Fuente de descubrimiento desconocida: {source}")

        value: int | str = external_id if field in _TEXT_ID_FIELDS else int(external_id)
        existing = (await self.db.execute(
            select(Series).where(getattr(Series, field) == value)
        )).scalar_one_or_none()
        if existing:
            return existing, False

        series = Series(
            title=title,
            tradition=tradition,
            start_year=start_year,
            description=description,
            cover_url=cover_url,
            metadata_source=source.value,
            **{field: value},
        )
        self.db.add(series)
        await self.db.flush()
        await self.db.refresh(series)
        return series, True
