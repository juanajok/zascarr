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
    normalizar_comic_vine_serie,
    normalizar_gcd_serie,
    normalizar_tebeosfera_serie,
    raw_acotado_comic_vine,
    raw_acotado_gcd,
    raw_acotado_tebeosfera,
)
from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
    ResultadoFetch,
    hash_payload,
)
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.gcd import GCDClient
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
    except BaseException:
        await pila.aclose()
        raise
    return {"adaptadores": adaptadores, "pila": pila}
