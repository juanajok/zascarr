"""Adaptadores de las fuentes actuales al contrato de la CCM.

Envoltorios finos sobre los clientes ya existentes. La Fase 1 solo cubre
**series** de CV, Tebeosfera y GCD; no se añaden búsquedas por título ni
métodos de issue que los clientes no tengan.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from zascarr.config import get_settings
from zascarr.core.consolidacion.normalizadores import (
    normalizar_anilist_serie,
    normalizar_comic_vine_serie,
    normalizar_fandom_serie,
    normalizar_gcd_serie,
    normalizar_metron_serie,
    normalizar_open_library_serie,
    normalizar_tebeosfera_serie,
    raw_acotado_anilist,
    raw_acotado_comic_vine,
    raw_acotado_fandom,
    raw_acotado_gcd,
    raw_acotado_metron,
    raw_acotado_open_library,
    raw_acotado_tebeosfera,
)
from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
    ResultadoFetch,
    hash_payload,
)
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.fandom import FandomClient
from zascarr.services.gcd import GCDClient
from zascarr.services.metron import MetronClient
from zascarr.services.open_library import OpenLibraryClient
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada

NORMALIZER_VERSION = 1
MAX_RAW_KEYS = 40


def _ficha(
    *, fuente: str, external_id: str, url: str | None, licencia: str | None,
    raw: dict[str, Any], normalizado: dict[str, Any],
    hash_previo: str | None, ahora: datetime,
) -> ResultadoFetch:
    payload = {
        "schema_version": 1,
        "normalizer_version": NORMALIZER_VERSION,
        "raw_acotado": dict(list(raw.items())[:MAX_RAW_KEYS]),
        "normalizado": normalizado,
        "sugerencias_id": [],
    }
    digest = hash_payload(payload)
    ficha = FichaRecolectada(
        fuente=fuente, entidad="series", external_id=external_id,
        url=url, licencia=licencia, raw_acotado=payload["raw_acotado"],
        normalizado=normalizado, normalizer_version=NORMALIZER_VERSION,
        payload_hash=digest, observado_en=ahora,
    )
    if hash_previo is not None and hash_previo == digest:
        return ResultadoFetch(EstadoFetch.NO_MODIFICADO, ficha)
    return ResultadoFetch(EstadoFetch.OK, ficha)


def _error(exc: Exception) -> ResultadoFetch:
    if isinstance(exc, CortesiaEnEspera):
        return ResultadoFetch(EstadoFetch.CUOTA_AGOTADA, detalle_error="cortesia")
    if isinstance(exc, FuenteApagada):
        return ResultadoFetch(EstadoFetch.CUOTA_AGOTADA, detalle_error="apagada")
    return ResultadoFetch(EstadoFetch.ERROR_RED, detalle_error=type(exc).__name__)


class AdaptadorComicVine:
    nombre = "comic_vine"
    capacidades_serie = frozenset({
        "title", "start_year", "publisher_name", "total_issues", "description",
    })
    licencia = "Comic Vine API Terms (uso no comercial)"
    base_url = "https://comicvine.gamespot.com/volume/4050-{id}/"

    def __init__(self, cliente: ComicVineClient):
        self._cliente = cliente

    async def fetch_serie(
        self, external_id: str, *, hash_previo: str | None = None
    ) -> ResultadoFetch:
        try:
            volume_id = int(external_id)
        except (TypeError, ValueError):
            return ResultadoFetch(EstadoFetch.ERROR_PARSEO, detalle_error="id_no_numerico")
        try:
            ficha = await self._cliente.get_volume(volume_id)
        except Exception as exc:  # noqa: BLE001 — el adaptador traduce el fallo
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = normalizar_comic_vine_serie(ficha)
        raw = raw_acotado_comic_vine(ficha)
        url = str(raw.get("site_url") or self.base_url.format(id=volume_id))
        return _ficha(
            fuente=self.nombre, external_id=str(volume_id), url=url,
            licencia=self.licencia, raw=raw, normalizado=normalizado,
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorTebeosfera:
    nombre = "tebeosfera"
    capacidades_serie = frozenset({
        "title", "start_year", "end_year", "publisher_name", "imprint_name",
        "country", "language",
    })
    licencia = "Tebeosfera: uso local; fichas sin licencia abierta explícita"

    def __init__(self, cliente: TebeosferaClient):
        self._cliente = cliente

    async def fetch_serie(
        self, external_id: str, *, hash_previo: str | None = None
    ) -> ResultadoFetch:
        try:
            ficha = await self._cliente.get_collection(str(external_id))
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = normalizar_tebeosfera_serie(ficha)
        raw = raw_acotado_tebeosfera(ficha)
        return _ficha(
            fuente=self.nombre, external_id=str(external_id),
            url=str(raw.get("url_ficha") or "") or None, licencia=self.licencia,
            raw=raw, normalizado=normalizado,
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorGCD:
    nombre = "gcd"
    capacidades_serie = frozenset({
        "title", "start_year", "end_year", "country", "language", "total_issues",
    })
    licencia = "CC BY-SA 4.0 (Grand Comics Database)"

    def __init__(self, cliente: GCDClient):
        self._cliente = cliente

    async def fetch_serie(
        self, external_id: str, *, hash_previo: str | None = None
    ) -> ResultadoFetch:
        try:
            gcd_id = int(external_id)
        except (TypeError, ValueError):
            return ResultadoFetch(EstadoFetch.ERROR_PARSEO, detalle_error="id_no_numerico")
        try:
            ficha = await self._cliente.get_series(gcd_id)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = normalizar_gcd_serie(ficha)
        raw = raw_acotado_gcd(ficha)
        return _ficha(
            fuente=self.nombre, external_id=str(gcd_id),
            url=getattr(ficha, "site_url", None), licencia=self.licencia,
            raw=raw, normalizado=normalizado,
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorAniList:
    nombre = "anilist"
    capacidades_serie = frozenset({"title", "start_year", "total_issues", "description"})
    licencia = "AniList Terms of Use (no comercial)"

    def __init__(self, cliente: AniListClient):
        self._cliente = cliente

    async def fetch_serie(self, external_id: str, *, hash_previo: str | None = None):
        try:
            anilist_id = int(external_id)
        except (TypeError, ValueError):
            return ResultadoFetch(EstadoFetch.ERROR_PARSEO, detalle_error="id_no_numerico")
        try:
            ficha = await self._cliente.get_manga(anilist_id)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        return _ficha(
            fuente=self.nombre, external_id=str(anilist_id),
            url=getattr(ficha, "site_url", None), licencia=self.licencia,
            raw=raw_acotado_anilist(ficha),
            normalizado=normalizar_anilist_serie(ficha),
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorMetron:
    nombre = "metron"
    capacidades_serie = frozenset({
        "title", "start_year", "end_year", "publisher_name", "language",
        "total_issues", "description",
    })
    licencia = "CC BY-SA 4.0 (Metron)"

    def __init__(self, cliente: MetronClient):
        self._cliente = cliente

    async def fetch_serie(self, external_id: str, *, hash_previo: str | None = None):
        try:
            metron_id = int(external_id)
        except (TypeError, ValueError):
            return ResultadoFetch(EstadoFetch.ERROR_PARSEO, detalle_error="id_no_numerico")
        try:
            ficha = await self._cliente.get_series(metron_id)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        return _ficha(
            fuente=self.nombre, external_id=str(metron_id),
            url=getattr(ficha, "site_url", None), licencia=self.licencia,
            raw=raw_acotado_metron(ficha),
            normalizado=normalizar_metron_serie(ficha),
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorOpenLibrary:
    nombre = "open_library"
    capacidades_serie = frozenset({
        "title", "start_year", "publisher_name", "language",
    })
    licencia = "Open Library: datos de Internet Archive; ver términos"

    def __init__(self, cliente: OpenLibraryClient):
        self._cliente = cliente

    async def fetch_serie(self, external_id: str, *, hash_previo: str | None = None):
        try:
            ficha = await self._cliente.get_work(str(external_id))
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        return _ficha(
            fuente=self.nombre, external_id=str(external_id),
            url=getattr(ficha, "site_url", None), licencia=self.licencia,
            raw=raw_acotado_open_library(ficha),
            normalizado=normalizar_open_library_serie(ficha),
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


class AdaptadorFandom:
    licencia = "Fandom: texto CC BY-SA; portadas fair use"

    def __init__(self, cliente: FandomClient, fuente: str):
        self._cliente = cliente
        self.nombre = fuente
        self.capacidades_serie = frozenset({
            "title", "start_year", "end_year", "total_issues", "description",
        })

    async def fetch_serie(self, external_id: str, *, hash_previo: str | None = None):
        # Los slugs nuevos usan `_` (id firmable); Fandom espera el título con espacios.
        titulo = str(external_id).replace("_", " ") if "_" in str(external_id) else str(external_id)
        try:
            ficha = await self._cliente.get_volume(titulo, incluir_portada=False)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        return _ficha(
            fuente=self.nombre, external_id=str(external_id), url=None,
            licencia=self.licencia, raw=raw_acotado_fandom(ficha),
            normalizado=normalizar_fandom_serie(ficha),
            hash_previo=hash_previo, ahora=datetime.now(UTC),
        )


async def abrir_adaptadores(settings=None) -> dict[str, Any]:
    """Abre solo las fuentes encendidas con datos de configuración suficientes.

    Devuelve adaptadores listos para usar. El llamante es responsable de cerrar
    los clientes: se devuelven junto a un `AsyncExitStack` ya abierto.
    """
    from contextlib import AsyncExitStack

    ajustes = settings or get_settings()
    pila = AsyncExitStack()
    adaptadores: dict[str, Any] = {}
    try:
        if getattr(ajustes, "comicvine_enabled", False) and str(
                getattr(ajustes, "comicvine_api_key", "") or "").strip():
            adaptadores["comic_vine"] = AdaptadorComicVine(
                await pila.enter_async_context(ComicVineClient()))
        if getattr(ajustes, "tebeosfera_enabled", False):
            adaptadores["tebeosfera"] = AdaptadorTebeosfera(
                await pila.enter_async_context(TebeosferaClient()))
        if getattr(ajustes, "gcd_enabled", False):
            adaptadores["gcd"] = AdaptadorGCD(
                await pila.enter_async_context(GCDClient()))
        if getattr(ajustes, "anilist_enabled", False):
            adaptadores["anilist"] = AdaptadorAniList(
                await pila.enter_async_context(AniListClient()))
        if (getattr(ajustes, "metron_enabled", False)
                and str(getattr(ajustes, "metron_token", "") or "").strip()):
            adaptadores["metron"] = AdaptadorMetron(
                await pila.enter_async_context(MetronClient()))
        if getattr(ajustes, "open_library_enabled", False):
            adaptadores["open_library"] = AdaptadorOpenLibrary(
                await pila.enter_async_context(OpenLibraryClient()))
        dc = bool(getattr(ajustes, "fandom_dc_enabled", False))
        marvel = bool(getattr(ajustes, "fandom_marvel_enabled", False))
        if dc or marvel:
            from zascarr.database import async_session_factory
            from zascarr.utils.cache_http import CacheHttp
            cache = CacheHttp(async_session_factory)
            if dc:
                adaptadores["fandom_dc"] = AdaptadorFandom(
                    await pila.enter_async_context(
                        FandomClient("dc.fandom.com", cache=cache)), "fandom_dc")
            if marvel:
                adaptadores["fandom_marvel"] = AdaptadorFandom(
                    await pila.enter_async_context(
                        FandomClient("marvel.fandom.com", cache=cache)), "fandom_marvel")
    except BaseException:
        await pila.aclose()
        raise
    return {"adaptadores": adaptadores, "pila": pila}
