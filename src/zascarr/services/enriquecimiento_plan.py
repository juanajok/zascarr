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
from zascarr.models import Issue, MetadataSource, Series
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient, CVIssueResult
from zascarr.services.enricher import EnrichmentService, SeriesMatch
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.services.tokens_revision import crear_token, verificar_token

logger = structlog.get_logger()

PROPOSITO = "enriquecimiento"
TTL_SEGUNDOS = 15 * 60

#: Máximo de números que se consultan en una vista previa. El enricher
#: procesa lotes pequeños; una serie con cientos de números no debe disparar
#: cientos de peticiones desde un botón. Los que no entran se avisan.
MAX_NUMEROS_PREVIA = 50

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
    entidad: str = "serie"
    issue_id: str | None = None

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
    avisos: tuple[str, ...] = ()

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
BuscadorIssues = Callable[
    [Series, SeriesMatch, list[Issue]], Awaitable[dict[UUID, CVIssueResult | None]]
]


def _huella(series: Series, id_field: str, issues: list[Issue]) -> str:
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
        "issues": [
            {
                "id": str(issue.id),
                "comic_vine_id": issue.comic_vine_id,
                "synopsis": issue.synopsis,
                "cover_url": issue.cover_url,
                "metadata_source": issue.metadata_source,
                "locked_fields": sorted(issue.locked_fields or []),
            }
            for issue in sorted(issues, key=lambda i: str(i.id))
        ],
    }
    crudo = json.dumps(datos, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(crudo).hexdigest()


def _campo(clave: str, etiqueta: str, actual, propuesto, fuente: str, accion: str,
           observacion: str, *, entidad: str = "serie", issue_id: str | None = None) -> CampoPlan:
    return CampoPlan(clave=clave, etiqueta=etiqueta, actual=actual, propuesto=propuesto,
                     procedencia=fuente, observacion=observacion, accion=accion,
                     entidad=entidad, issue_id=issue_id)


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


def construir_campos_issue(issue: Issue, match: CVIssueResult,
                          fuente: str) -> tuple[CampoPlan, ...]:
    """Campos de un número que el enricher gestiona por Comic Vine.

    Los créditos quedan fuera de esta iteración: crear creadores y relaciones
    merece su propio contrato y no se mezcla con los campos escalares.
    """
    locked = set(issue.locked_fields or [])
    prefijo = f"issue:{issue.id}:"
    numero = f"#{issue.issue_number} · " if issue.issue_number else "Número sin número · "

    def campo(nombre: str, etiqueta: str, actual, propuesto) -> CampoPlan:
        clave = prefijo + nombre
        if nombre in locked:
            return _campo(clave, numero + etiqueta, actual, propuesto, fuente, BLOQUEADO,
                          "Protegido: el enriquecimiento no sobrescribe este campo.",
                          entidad="issue", issue_id=str(issue.id))
        if propuesto is None or (isinstance(propuesto, str) and not propuesto.strip()):
            return _campo(clave, numero + etiqueta, actual, None, fuente, OMITIR_POR_AUSENCIA,
                          "La fuente no aporta este dato; no se borra nada.",
                          entidad="issue", issue_id=str(issue.id))
        if actual is None or (isinstance(actual, str) and not actual.strip()):
            return _campo(clave, numero + etiqueta, actual, propuesto, fuente, ANADIR,
                          "Se añadirá este dato.", entidad="issue", issue_id=str(issue.id))
        if actual == propuesto:
            return _campo(clave, numero + etiqueta, actual, propuesto, fuente, CONSERVAR,
                          "El valor coincide; no hay nada que cambiar.",
                          entidad="issue", issue_id=str(issue.id))
        return _campo(clave, numero + etiqueta, actual, propuesto, fuente, PROPONER_SUSTITUCION,
                      "La fuente propone otro valor; no se cambia sin tu decisión.",
                      entidad="issue", issue_id=str(issue.id))

    return (
        campo("comic_vine_id", "Identidad en la fuente", issue.comic_vine_id, match.cv_id),
        campo("synopsis", "Sinopsis", issue.synopsis, match.description),
        campo("cover_url", "Portada", issue.cover_url, match.image_url),
    )


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


async def _buscar_issues_con_fuente(
    db: AsyncSession, series: Series, match: SeriesMatch, issues: list[Issue],
) -> dict[UUID, CVIssueResult | None]:
    """Consulta cada número candidato en Comic Vine, con el volumen de la serie."""
    if not issues:
        return {}
    settings = get_settings()
    if not settings.comicvine_enabled:
        raise FuenteApagada("Comic Vine está desactivada en Ajustes.")
    volume_id = series.comic_vine_id or match.source_id
    if not isinstance(volume_id, int):
        return {}
    resultados: dict[UUID, CVIssueResult | None] = {}
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(ComicVineClient())
        for issue in issues:
            try:
                resultados[issue.id] = await client.find_issue(volume_id, issue.issue_number)
            except Exception as exc:
                logger.warning("enriquecimiento.issue_lookup_failed",
                               issue=str(issue.id), error=type(exc).__name__)
                raise ErrorDePlan(
                    "No se pudieron consultar los números de esta serie; vuelve a intentarlo."
                ) from exc
    return resultados


class EnriquecimientoPlanService:
    """Previsualiza y aplica un plan de enriquecimiento de una serie."""

    def __init__(self, db: AsyncSession, secret: str, *,
                 buscador: Buscador | None = None,
                 buscador_issues: BuscadorIssues | None = None) -> None:
        self.db = db
        self.secret = secret
        self._buscador = buscador or (lambda serie, source: _buscar_con_fuente(db, serie, source))
        self._buscador_issues = buscador_issues or (
            lambda serie, match, issues: _buscar_issues_con_fuente(db, serie, match, issues)
        )

    async def _series(self, series_id: UUID) -> Series:
        series = (await self.db.execute(
            select(Series).where(Series.id == series_id)
        )).scalar_one_or_none()
        if series is None:
            raise SinSerie("Esa serie no existe.")
        return series

    async def _issues_candidatas(self, series_id: UUID) -> tuple[list[Issue], tuple[str, ...]]:
        """Números que el enricher podría tocar, con aviso si se recorta la lista."""
        filas = (await self.db.execute(
            select(Issue)
            .where(Issue.series_id == series_id)
            .where(Issue.issue_number.is_not(None))
            .where(Issue.comic_vine_id.is_(None))
            .where(Issue.metadata_source.is_distinct_from(MetadataSource.MANUAL.value))
            .order_by(Issue.sort_order.asc().nulls_last(), Issue.issue_number)
            .limit(MAX_NUMEROS_PREVIA + 1)
        )).scalars().all()
        avisos: list[str] = []
        if len(filas) > MAX_NUMEROS_PREVIA:
            filas = filas[:MAX_NUMEROS_PREVIA]
            avisos.append(
                f"Se revisan los primeros {MAX_NUMEROS_PREVIA} números; "
                "el resto no entra en esta vista previa."
            )
        return list(filas), tuple(avisos)

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
        campos = list(construir_campos(series, match, id_field, label))
        issues: list[Issue] = []
        avisos: tuple[str, ...] = ()
        if source_value == MetadataSource.COMIC_VINE.value:
            issues, avisos = await self._issues_candidatas(series.id)
            matches = await self._buscador_issues(series, match, issues)
            for issue in issues:
                issue_match = matches.get(issue.id)
                if issue_match is not None:
                    campos.extend(construir_campos_issue(issue, issue_match, label))
        datos = {
            "v": _huella(series, id_field, issues),
            "fuente": source_value,
            "campos": [
                {"k": c.clave, "a": c.accion, "p": c.propuesto, "l": c.etiqueta,
                 "e": c.entidad, "iid": c.issue_id}
                for c in campos
            ],
        }
        token = crear_token(PROPOSITO, str(series.id), datos, self.secret,
                            ttl=TTL_SEGUNDOS)
        return Plan(series_id=series.id, titulo=series.title, fuente=source_value,
                    fuente_etiqueta=label, campos=tuple(campos), token=token,
                    avisos=avisos)

    async def aplicar(self, token: str, seleccion: list[str] | tuple[str, ...],
                      series_id: UUID | None = None) -> Resultado:
        """Aplica exactamente el plan firmado; solo las claves seleccionadas.

        `series_id` es la ficha de la URL: si el token es de otra, no se aplica
        aunque la firma sea válida.
        """
        payload = _payload(token)
        contexto = payload.get("c") if payload else None
        datos = verificar_token(token, PROPOSITO, contexto or "", self.secret) if contexto else None
        if not datos:
            raise TokenInvalido("La vista previa no es válida o ha caducado; vuelve a revisarla.")
        try:
            token_series_id = UUID(str(payload["c"]))
        except (ValueError, KeyError) as exc:
            raise TokenInvalido("La vista previa no es válida; vuelve a revisarla.") from exc
        if series_id is not None and token_series_id != series_id:
            raise TokenInvalido("La vista previa pertenece a otra serie; vuelve a revisarla.")
        series = await self._series(token_series_id)
        campos_token = datos.get("campos")
        if not isinstance(campos_token, list):
            raise TokenInvalido("La vista previa no es válida; vuelve a revisarla.")
        source = EnrichmentService._source_for(series.tradition)
        id_field = source[0] if source else None
        issues: list[Issue] = []
        if source and source[1] == MetadataSource.COMIC_VINE.value:
            issues, _avisos = await self._issues_candidatas(series.id)
        if not id_field or _huella(series, id_field, issues) != datos.get("v"):
            raise PlanDesactualizado(
                "La ficha cambió desde que viste la propuesta; vuelve a revisarla antes de aplicar."
            )

        seleccionadas = {str(k) for k in (seleccion or [])}
        issues_por_id = {str(issue.id): issue for issue in issues}
        por_clave = {str(c.get("k")): c for c in campos_token if isinstance(c, dict)}
        resultado: list[ResultadoCampo] = []
        aplicados: list[str] = []
        aplicado_serie = False
        for clave, campo in por_clave.items():
            etiqueta = str(campo.get("l") or clave)
            accion = str(campo.get("a") or "")
            entidad = str(campo.get("e") or "serie")
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
            propuesto = campo.get("p")
            if entidad == "issue":
                issue = issues_por_id.get(str(campo.get("iid") or ""))
                nombre = clave.rsplit(":", 1)[-1]
                if issue is None:
                    resultado.append(ResultadoCampo(clave, etiqueta, accion, "no_aplicado",
                                                    "El número ya no está en la ficha."))
                    continue
                if nombre in set(issue.locked_fields or []):
                    resultado.append(ResultadoCampo(clave, etiqueta, accion, "bloqueado",
                                                    "Protegido; no se toca."))
                    continue
                if nombre == "comic_vine_id":
                    issue.comic_vine_id = propuesto if isinstance(propuesto, int) else None
                elif nombre == "synopsis":
                    issue.synopsis = propuesto if isinstance(propuesto, str) else None
                elif nombre == "cover_url":
                    issue.cover_url = propuesto if isinstance(propuesto, str) else None
                else:
                    resultado.append(ResultadoCampo(clave, etiqueta, accion, "no_aplicado",
                                                    "Campo desconocido; no se aplica."))
                    continue
                if issue.metadata_source is None:
                    issue.metadata_source = MetadataSource.COMIC_VINE.value
            else:
                if clave in set(series.locked_fields or []):
                    resultado.append(ResultadoCampo(clave, etiqueta, accion, "bloqueado",
                                                    "Protegido; no se toca."))
                    continue
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
                aplicado_serie = True
            aplicados.append(clave)
            resultado.append(ResultadoCampo(clave, etiqueta, accion, "aplicado",
                                            "Aplicado a la ficha."))

        if aplicado_serie and series.metadata_source is None:
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
