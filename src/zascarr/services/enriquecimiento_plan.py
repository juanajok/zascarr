"""Plan de enriquecimiento por campo (#128, MIT-M6-US02).

La vista previa **no escribe**: consulta la fuente, construye un plan por
campo y lo firma. La aplicación consume el MISMO plan firmado; no vuelve a
consultar la fuente ni reconstruye la lista de cambios. El plan caduca y se
rechaza si la ficha cambió entre la vista y la aplicación.

Alcance de esta entrega: campos de la **serie** que gestiona el enricher
(identidad externa, sinopsis, portada y total). Los campos de los números
quedan fuera de esta vertical y no se presentan como si estuvieran cubiertos.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import MetadataSource, Series
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.enricher import EnrichmentService, SeriesMatch
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.services.tokens_revision import crear_token, verificar_token

logger = structlog.get_logger()

PROPOSITO = "enriquecimiento"
TTL_SEGUNDOS = 15 * 60

#: Acciones del contrato de #128. Solo las dos primeras se pueden aplicar.
ANADIR = "anadir"
CONSERVAR = "conservar"
PROPONER_SUSTITUCION = "proponer_sustitucion"
OMITIR_POR_AUSENCIA = "omitir_por_ausencia"
BLOQUEADO = "bloqueado"
_APLICABLES = frozenset({ANADIR, PROPONER_SUSTITUCION})


class ErrorDePlan(Exception):  # noqa: N818 — nombre de dominio en español
    """Error de negocio con mensaje ya en español para la UI."""


class SinSerie(ErrorDePlan):
    pass


class SinFuente(ErrorDePlan):
    pass


class FuenteApagada(ErrorDePlan):
    pass


class SinCoincidencia(ErrorDePlan):
    pass


class TokenInvalido(ErrorDePlan):
    pass


class PlanDesactualizado(ErrorDePlan):
    pass


@dataclass(frozen=True)
class CampoPlan:
    clave: str
    etiqueta: str
    actual: object | None
    propuesto: object | None
    procedencia: str
    observacion: str
    accion: str

    @property
    def aplicable(self) -> bool:
        return self.accion in _APLICABLES


@dataclass(frozen=True)
class Plan:
    series_id: UUID
    titulo: str
    fuente: str
    fuente_etiqueta: str
    campos: tuple[CampoPlan, ...]
    token: str

    @property
    def aplicables(self) -> tuple[CampoPlan, ...]:
        return tuple(c for c in self.campos if c.aplicable)


@dataclass(frozen=True)
class ResultadoCampo:
    clave: str
    etiqueta: str
    accion: str
    estado: str
    motivo: str


@dataclass(frozen=True)
class Resultado:
    series_id: UUID
    titulo: str
    campos: tuple[ResultadoCampo, ...]

    @property
    def aplicados(self) -> tuple[ResultadoCampo, ...]:
        return tuple(c for c in self.campos if c.estado == "aplicado")


Buscador = Callable[[Series, tuple[str, str, str]], Awaitable[SeriesMatch | None]]


def _huella(series: Series, id_field: str) -> str:
    """Huella de lo que el plan vio. Si cambia, el plan está desactualizado."""
    datos = {
        "id": str(series.id),
        "id_field": id_field,
        "id_externo": getattr(series, id_field, None),
        "description": series.description,
        "cover_url": series.cover_url,
        "total_issues": series.total_issues,
        "metadata_source": series.metadata_source,
        "locked_fields": sorted(series.locked_fields or []),
    }
    crudo = json.dumps(datos, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(crudo).hexdigest()


def _campo(clave: str, etiqueta: str, actual, propuesto, fuente: str, accion: str,
           observacion: str) -> CampoPlan:
    return CampoPlan(clave=clave, etiqueta=etiqueta, actual=actual, propuesto=propuesto,
                     procedencia=fuente, observacion=observacion, accion=accion)


def construir_campos(series: Series, match: SeriesMatch, id_field: str,
                     fuente: str) -> tuple[CampoPlan, ...]:
    """Plan por campo, sin escribir ni consultar. Reglas de #128 y del enricher.

    - Un campo bloqueado se muestra con la propuesta, pero no se aplica.
    - La ausencia de propuesta se registra como omisión, nunca como borrado.
    - Una sustitución solo se propone cuando hay un valor actual y otro distinto;
      la persona decide si la aplica.
    """
    locked = set(series.locked_fields or [])

    def campo(clave: str, etiqueta: str, actual, propuesto) -> CampoPlan:
        if clave in locked:
            return _campo(clave, etiqueta, actual, propuesto, fuente, BLOQUEADO,
                          "Protegido: el enriquecimiento no sobrescribe este campo.")
        if propuesto is None or (isinstance(propuesto, str) and not propuesto.strip()):
            return _campo(clave, etiqueta, actual, None, fuente, OMITIR_POR_AUSENCIA,
                          "La fuente no aporta este dato; no se borra nada.")
        if actual is None or (isinstance(actual, str) and not actual.strip()):
            return _campo(clave, etiqueta, actual, propuesto, fuente, ANADIR,
                          "Se añadirá este dato.")
        if actual == propuesto:
            return _campo(clave, etiqueta, actual, propuesto, fuente, CONSERVAR,
                          "El valor coincide; no hay nada que cambiar.")
        return _campo(clave, etiqueta, actual, propuesto, fuente, PROPONER_SUSTITUCION,
                      "La fuente propone otro valor; no se cambia sin tu decisión.")

    campos = [campo(id_field, "Identidad en la fuente", getattr(series, id_field, None),
                    match.source_id)]
    # La identidad no se sustituye por otra: si ya hay un id distinto, se
    # conserva y se explica. El enricher tampoco la pisa.
    if len(campos) == 1 and campos[0].accion == PROPONER_SUSTITUCION:
        campos[0] = _campo(id_field, "Identidad en la fuente", getattr(series, id_field, None),
                           match.source_id, fuente, CONSERVAR,
                           "La ficha ya tiene otra identidad; no se propone sustituirla.")
    campos.extend([
        campo("description", "Sinopsis", series.description, match.description),
        campo("cover_url", "Portada", series.cover_url, match.cover_url),
        campo("total_issues", "Números en total", series.total_issues, match.count_of_issues),
    ])
    return tuple(campos)


async def _buscar_con_fuente(db: AsyncSession, series: Series,
                             source: tuple[str, str, str]) -> SeriesMatch | None:
    id_field, source_value, _label = source
    settings = get_settings()
    if source_value == MetadataSource.COMIC_VINE.value and not settings.comicvine_enabled:
        raise FuenteApagada("Comic Vine está desactivada en Ajustes.")
    if source_value == MetadataSource.ANILIST.value and not settings.anilist_enabled:
        raise FuenteApagada("AniList está desactivada en Ajustes.")
    if source_value == MetadataSource.TEBEOSFERA.value and not settings.tebeosfera_enabled:
        raise FuenteApagada("Tebeosfera está desactivada en Ajustes.")
    async with AsyncExitStack() as stack:
        if source_value == MetadataSource.COMIC_VINE.value:
            client = await stack.enter_async_context(ComicVineClient())
            return await EnrichmentService(db)._find_cv_series_match(client, series)
        if source_value == MetadataSource.ANILIST.value:
            client = await stack.enter_async_context(AniListClient())
            return await EnrichmentService(db)._find_anilist_match(client, series)
        client = await stack.enter_async_context(TebeosferaClient())
        return await EnrichmentService(db)._find_tebeosfera_match(client, series)


class EnriquecimientoPlanService:
    """Previsualiza y aplica un plan de enriquecimiento de una serie."""

    def __init__(self, db: AsyncSession, secret: str, *,
                 buscador: Buscador | None = None) -> None:
        self.db = db
        self.secret = secret
        self._buscador = buscador or (lambda serie, source: _buscar_con_fuente(db, serie, source))

    async def _series(self, series_id: UUID) -> Series:
        series = (await self.db.execute(
            select(Series).where(Series.id == series_id)
        )).scalar_one_or_none()
        if series is None:
            raise SinSerie("Esa serie no existe.")
        return series

    async def previsualizar(self, series_id: UUID) -> Plan:
        if not self.secret:
            raise ErrorDePlan("No hay clave del servidor para firmar la vista previa.")
        series = await self._series(series_id)
        if series.metadata_source == MetadataSource.MANUAL.value:
            raise SinFuente("Esta serie está marcada como manual; no se enriquece automáticamente.")
        source = EnrichmentService._source_for(series.tradition)
        if source is None:
            raise SinFuente("Esta tradición todavía no tiene una fuente de enriquecimiento.")
        id_field, source_value, label = source
        match = await self._buscador(series, source)
        if match is None:
            raise SinCoincidencia("La fuente no tiene una coincidencia inequívoca para esta serie.")
        campos = construir_campos(series, match, id_field, label)
        datos = {
            "v": _huella(series, id_field),
            "fuente": source_value,
            "campos": [
                {"k": c.clave, "a": c.accion, "p": c.propuesto}
                for c in campos
            ],
        }
        token = crear_token(PROPOSITO, str(series.id), datos, self.secret,
                            ttl=TTL_SEGUNDOS)
        return Plan(series_id=series.id, titulo=series.title, fuente=source_value,
                    fuente_etiqueta=label, campos=campos, token=token)

    async def aplicar(self, token: str, seleccion: list[str] | tuple[str, ...]) -> Resultado:
        """Aplica exactamente el plan firmado; solo las claves seleccionadas."""
        payload = _payload(token)
        contexto = payload.get("c") if payload else None
        datos = verificar_token(token, PROPOSITO, contexto or "", self.secret) if contexto else None
        if not datos:
            raise TokenInvalido("La vista previa no es válida o ha caducado; vuelve a revisarla.")
        try:
            series_id = UUID(str(payload["c"]))
        except (ValueError, KeyError) as exc:
            raise TokenInvalido("La vista previa no es válida; vuelve a revisarla.") from exc
        series = await self._series(series_id)
        campos_token = datos.get("campos")
        if not isinstance(campos_token, list):
            raise TokenInvalido("La vista previa no es válida; vuelve a revisarla.")
        source = EnrichmentService._source_for(series.tradition)
        id_field = source[0] if source else None
        if not id_field or _huella(series, id_field) != datos.get("v"):
            raise PlanDesactualizado(
                "La ficha cambió desde que viste la propuesta; vuelve a revisarla antes de aplicar."
            )

        seleccionadas = {str(k) for k in (seleccion or [])}
        por_clave = {str(c.get("k")): c for c in campos_token if isinstance(c, dict)}
        resultado: list[ResultadoCampo] = []
        aplicados: list[str] = []
        por_etiqueta = {
            "comic_vine_id": "Identidad en la fuente",
            "anilist_id": "Identidad en la fuente",
            "tebeosfera_slug": "Identidad en la fuente",
            "description": "Sinopsis",
            "cover_url": "Portada",
            "total_issues": "Números en total",
        }
        for clave, campo in por_clave.items():
            etiqueta = por_etiqueta.get(clave, clave)
            accion = str(campo.get("a") or "")
            if accion == BLOQUEADO:
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "bloqueado",
                                                "Protegido; no se toca."))
                continue
            if accion == OMITIR_POR_AUSENCIA:
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "omitido",
                                                "La fuente no aporta este dato."))
                continue
            if accion == CONSERVAR:
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "conservado",
                                                "El valor ya era el de la fuente."))
                continue
            if clave not in seleccionadas:
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "no_aplicado",
                                                "No lo seleccionaste."))
                continue
            if clave in set(series.locked_fields or []):
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "bloqueado",
                                                "Protegido; no se toca."))
                continue
            propuesto = campo.get("p")
            if clave == "description":
                series.description = propuesto if isinstance(propuesto, str) else None
            elif clave == "cover_url":
                series.cover_url = propuesto if isinstance(propuesto, str) else None
            elif clave == "total_issues":
                series.total_issues = propuesto if isinstance(propuesto, int) else None
            elif clave == id_field:
                setattr(series, id_field, propuesto)
            else:
                resultado.append(ResultadoCampo(clave, etiqueta, accion, "no_aplicado",
                                                "Campo desconocido; no se aplica."))
                continue
            aplicados.append(clave)
            resultado.append(ResultadoCampo(clave, etiqueta, accion, "aplicado",
                                            "Aplicado a la ficha."))

        if aplicados and series.metadata_source is None:
            series.metadata_source = datos.get("fuente")
        await self.db.flush()
        return Resultado(series_id=series.id, titulo=series.title, campos=tuple(resultado))

def _payload(token: str) -> dict | None:
    """Contexto del token sin verificar; la firma ya se comprobó antes."""
    import base64
    try:
        crudo = token.rsplit(".", 1)[0]
        datos = json.loads(base64.urlsafe_b64decode(crudo.encode()).decode())
    except (ValueError, UnicodeDecodeError, KeyError):
        return None
    if not isinstance(datos, dict) or not isinstance(datos.get("c"), str):
        return None
    return datos
