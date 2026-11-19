"""Adaptadores de issue para la CCM (Fase 4).

Solo se consulta por el identificador que ya está en la fila. No hay búsqueda
por número ni emparejamiento por título.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
    ResultadoFetch,
    hash_payload,
)
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.fandom import FandomClient
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada

VERSION = 1


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    return texto or None


def _entero(valor: object) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _fecha(valor: object) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:10] if len(texto) >= 10 else None


def _ficha(fuente: str, external_id: str, url: str | None, licencia: str | None,
           raw: dict[str, Any], normalizado: dict[str, Any],
           hash_previo: str | None) -> ResultadoFetch:
    payload = {"schema_version": 1, "normalizer_version": VERSION,
               "raw_acotado": raw, "normalizado": normalizado, "sugerencias_id": []}
    digest = hash_payload(payload)
    ficha = FichaRecolectada(
        fuente=fuente, entidad="issue", external_id=external_id, url=url,
        licencia=licencia, raw_acotado=raw, normalizado=normalizado,
        normalizer_version=VERSION, payload_hash=digest,
        observado_en=datetime.now(UTC),
    )
    if hash_previo == digest:
        return ResultadoFetch(EstadoFetch.NO_MODIFICADO, ficha)
    return ResultadoFetch(EstadoFetch.OK, ficha)


def _error(exc: Exception) -> ResultadoFetch:
    if isinstance(exc, (CortesiaEnEspera, FuenteApagada)):
        return ResultadoFetch(EstadoFetch.CUOTA_AGOTADA, detalle_error=type(exc).__name__)
    return ResultadoFetch(EstadoFetch.ERROR_RED, detalle_error=type(exc).__name__)


class AdaptadorComicVineIssue:
    nombre = "comic_vine"
    licencia = "Comic Vine API Terms (uso no comercial)"

    def __init__(self, cliente: ComicVineClient):
        self._cliente = cliente

    async def fetch_issue(self, external_id: str, *, hash_previo: str | None = None):
        try:
            cv_id = int(external_id)
        except (TypeError, ValueError):
            return ResultadoFetch(EstadoFetch.ERROR_PARSEO, detalle_error="id_no_numerico")
        try:
            raw = await self._cliente.get_issue_detail(cv_id)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if not isinstance(raw, dict) or not raw:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = {
            "edition_scope": {
                k: v for k, v in {
                    "title": _texto(raw.get("name")),
                    "release_date": _fecha(raw.get("store_date") or raw.get("cover_date")),
                    "page_count": _entero(raw.get("page_count")),
                    "isbn": _texto(raw.get("isbn")),
                }.items() if v is not None
            },
            "work_scope": {
                k: v for k, v in {
                    "synopsis": _texto(raw.get("description")),
                }.items() if v is not None
            },
        }
        raw_acotado = {k: raw[k] for k in ("id", "name", "issue_number", "store_date",
                                            "cover_date", "page_count", "isbn")
                       if raw.get(k) is not None}
        return _ficha("comic_vine", str(cv_id), None, self.licencia,
                      raw_acotado, normalizado, hash_previo)


class AdaptadorTebeosferaIssue:
    nombre = "tebeosfera"
    licencia = "Tebeosfera: uso local; fichas sin licencia abierta explícita"

    def __init__(self, cliente: TebeosferaClient):
        self._cliente = cliente

    async def fetch_issue(self, external_id: str, *, hash_previo: str | None = None):
        try:
            ficha = await self._cliente.get_numero(str(external_id))
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = {
            "edition_scope": {
                k: v for k, v in {
                    "release_date": _fecha(getattr(ficha, "fecha", None)),
                    "page_count": _entero(getattr(ficha, "paginas", None)),
                }.items() if v is not None
            },
            "work_scope": {},
        }
        raw = {k: getattr(ficha, k, None) for k in
               ("slug", "numero_publicacion", "fecha", "paginas", "formato_fuente",
                "url_ficha") if getattr(ficha, k, None) is not None}
        return _ficha("tebeosfera", str(external_id),
                      getattr(ficha, "url_ficha", None), self.licencia,
                      raw, normalizado, hash_previo)


class AdaptadorFandomIssue:
    licencia = "Fandom: texto CC BY-SA; portadas fair use"

    def __init__(self, cliente: FandomClient, nombre: str):
        self._cliente = cliente
        self.nombre = nombre

    async def fetch_issue(self, external_id: str, *, hash_previo: str | None = None):
        try:
            ficha = await self._cliente.get_issue(str(external_id))
        except Exception as exc:  # noqa: BLE001
            return _error(exc)
        if ficha is None:
            return ResultadoFetch(EstadoFetch.NO_ENCONTRADO)
        normalizado = {
            "edition_scope": {
                k: v for k, v in {
                    "title": _texto(getattr(ficha, "story_title", None)),
                    "release_date": _fecha(getattr(ficha, "release_date", None)),
                }.items() if v is not None
            },
            "work_scope": {
                k: v for k, v in {
                    "synopsis": _texto(getattr(ficha, "synopsis", None)),
                }.items() if v is not None
            },
        }
        raw = {k: getattr(ficha, k, None) for k in
               ("page_title", "release_date", "story_title") if getattr(ficha, k, None) is not None}
        return _ficha(self.nombre, str(external_id), None, self.licencia,
                      raw, normalizado, hash_previo)
