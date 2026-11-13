# ruff: noqa: E501
"""Catálogo OPDS 1.2 de **solo catálogo** (#160, BL-C5).

No hay enlaces de adquisición/descarga: el cliente navega por series,
tradiciones, editoriales y números, nada más. El contrato está en
`docs/design/especificacion-BL-C5-opds.md`.

El XML se construye con ElementTree (escapado automático). Las rutas de
archivo, los hashes y los `File` no entran aquí: este router solo lee Series,
Issue, Creator e Publisher.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime
from urllib.parse import urlencode
from uuid import UUID
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import (
    ComicTradition,
    Creator,
    CreatorRole,
    Issue,
    IssueCreator,
    Publisher,
    Series,
)
from zascarr.services.series import SeriesService

ATOM = "http://www.w3.org/2005/Atom"
OPDS = "http://opds-spec.org/2010/catalog"
DC = "http://purl.org/dc/terms/"
_TIPO_NAV = "application/atom+xml;profile=opds-catalog;kind=navigation"
_TIPO_XML = "application/xml; charset=utf-8"
_PAGE_SIZE = 50
_VERSION = 1
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

ET.register_namespace("", ATOM)
ET.register_namespace("opds", OPDS)
ET.register_namespace("dc", DC)

router = APIRouter(prefix="/opds", tags=["opds"])

_TRADICIONES = {
    ComicTradition.AMERICAN: "Grapa americana",
    ComicTradition.FRANCO_BELGIAN: "Franco-belga (BD)",
    ComicTradition.MANGA: "Manga",
    ComicTradition.TEBEO: "Tebeo español",
    ComicTradition.FUMETTI: "Fumetti",
    ComicTradition.MANHWA: "Manhwa",
    ComicTradition.MANHUA: "Manhua",
    ComicTradition.BRITISH: "Británico",
    ComicTradition.OTHER: "Otra",
}


def _tag(ns: str, nombre: str) -> str:
    return f"{{{ns}}}{nombre}"


def _fecha(valor: datetime | date | None) -> str:
    if valor is None:
        return _EPOCH.isoformat().replace("+00:00", "Z")
    if isinstance(valor, date) and not isinstance(valor, datetime):
        valor = datetime(valor.year, valor.month, valor.day, tzinfo=UTC)
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _etag(actualizado: datetime | None, request: Request, *, extra: str = "") -> str:
    material = f"{_VERSION}|{_fecha(actualizado)}|{request.url.path}|{request.url.query}|{extra}"
    return '"' + hashlib.sha256(material.encode()).hexdigest() + '"'


def _no_modificado(request: Request, etag: str) -> bool:
    cabecera = request.headers.get("if-none-match")
    if not cabecera:
        return False
    if cabecera.strip() == "*":
        return True
    return etag in {parte.strip() for parte in cabecera.split(",")}


def _respuesta(request: Request, cuerpo: bytes, actualizado: datetime | None, *, extra: str = "") -> Response:
    etag = _etag(actualizado, request, extra=extra)
    if _no_modificado(request, etag):
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=300"})
    return Response(
        content=cuerpo,
        headers={"Content-Type": _TIPO_NAV, "ETag": etag, "Cache-Control": "private, max-age=300"},
    )


def _xml_error(status: int, titulo: str, detalle: str) -> Response:
    raiz = ET.Element(_tag(ATOM, "error"))
    ET.SubElement(raiz, _tag(ATOM, "id")).text = f"urn:zascarr:opds:error:{status}"
    ET.SubElement(raiz, _tag(ATOM, "title")).text = titulo
    ET.SubElement(raiz, _tag(ATOM, "updated")).text = _fecha(datetime.now(UTC))
    ET.SubElement(raiz, _tag(ATOM, "summary")).text = detalle
    cuerpo = ET.tostring(raiz, encoding="utf-8", xml_declaration=True)
    return Response(content=cuerpo, status_code=status,
                    headers={"Content-Type": _TIPO_XML, "Cache-Control": "no-store"})


def _enlace(feed: ET.Element, rel: str, href: str, tipo: str | None = None) -> None:
    attrs = {"rel": rel, "href": href}
    if tipo:
        attrs["type"] = tipo
    ET.SubElement(feed, _tag(ATOM, "link"), attrs)


def _feed(url_self: str, titulo: str, actualizado: datetime | None,
          *, start: str = "/opds", up: str | None = None) -> ET.Element:
    feed = ET.Element(_tag(ATOM, "feed"))
    ET.SubElement(feed, _tag(ATOM, "id")).text = url_self
    ET.SubElement(feed, _tag(ATOM, "title")).text = titulo
    ET.SubElement(feed, _tag(ATOM, "updated")).text = _fecha(actualizado)
    _enlace(feed, "self", url_self, _TIPO_NAV)
    _enlace(feed, "start", start, _TIPO_NAV)
    if up:
        _enlace(feed, "up", up, _TIPO_NAV)
    return feed


def _entrada_nav(feed: ET.Element, *, ident: str, titulo: str, href: str,
                 actualizado: datetime | None, resumen: str | None = None) -> ET.Element:
    entrada = ET.SubElement(feed, _tag(ATOM, "entry"))
    ET.SubElement(entrada, _tag(ATOM, "id")).text = ident
    ET.SubElement(entrada, _tag(ATOM, "title")).text = titulo
    ET.SubElement(entrada, _tag(ATOM, "updated")).text = _fecha(actualizado)
    if resumen:
        ET.SubElement(entrada, _tag(ATOM, "summary")).text = resumen
    _enlace(entrada, "subsection", href, _TIPO_NAV)
    return entrada


def _entrada_serie(feed: ET.Element, serie: Series, autores: list[str]) -> None:
    entrada = ET.SubElement(feed, _tag(ATOM, "entry"))
    ident = f"urn:zascarr:serie:{serie.id}"
    ET.SubElement(entrada, _tag(ATOM, "id")).text = ident
    ET.SubElement(entrada, _tag(ATOM, "title")).text = serie.title
    ET.SubElement(entrada, _tag(ATOM, "updated")).text = _fecha(serie.updated_at)
    if serie.description:
        ET.SubElement(entrada, _tag(ATOM, "summary")).text = serie.description
    for nombre in autores:
        autor = ET.SubElement(entrada, _tag(ATOM, "author"))
        ET.SubElement(autor, _tag(ATOM, "name")).text = nombre
    tradicion = serie.tradition.value if hasattr(serie.tradition, "value") else str(serie.tradition or "")
    etiqueta = _TRADICIONES.get(serie.tradition, tradicion)
    ET.SubElement(entrada, _tag(ATOM, "category"), {"term": tradicion, "label": etiqueta})
    _enlace(entrada, "subsection", f"/opds/series/{serie.id}", _TIPO_NAV)
    _enlace(entrada, "alternate", f"/ui/series/{serie.id}", "text/html")


def _entrada_issue(feed: ET.Element, issue: Issue, serie: Series) -> None:
    entrada = ET.SubElement(feed, _tag(ATOM, "entry"))
    etiqueta = f"{serie.title} #{issue.issue_number}" if issue.issue_number else serie.title
    ET.SubElement(entrada, _tag(ATOM, "id")).text = f"urn:zascarr:serie:{serie.id}:numero:{issue.issue_number or issue.id}"
    ET.SubElement(entrada, _tag(ATOM, "title")).text = issue.title or etiqueta
    ET.SubElement(entrada, _tag(ATOM, "updated")).text = _fecha(issue.updated_at)
    if issue.synopsis:
        ET.SubElement(entrada, _tag(ATOM, "summary")).text = issue.synopsis
    if issue.issue_number:
        ET.SubElement(entrada, _tag(ATOM, "dc:identifier")).text = f"{serie.title} #{issue.issue_number}"
    if issue.release_date:
        ET.SubElement(entrada, _tag(DC, "issued")).text = issue.release_date.isoformat()
    _enlace(entrada, "alternate", f"/ui/series/{serie.id}", "text/html")


def _pagina_links(entrada: ET.Element, base: str, page: int, pages: int, filtros: dict[str, str]) -> None:
    def url(n: int) -> str:
        params = dict(filtros)
        params["page"] = str(n)
        return f"{base}?{urlencode(params)}"
    if page > 1:
        _enlace(entrada, "previous", url(page - 1), _TIPO_NAV)
    if pages and page < pages:
        _enlace(entrada, "next", url(page + 1), _TIPO_NAV)


async def _max_actualizado(db: AsyncSession, *condiciones) -> datetime | None:
    consulta = select(func.max(Series.updated_at))
    for condicion in condiciones:
        consulta = consulta.where(condicion)
    valor = (await db.execute(consulta)).scalar()
    return valor


def _validar_tradicion(valor: str | None) -> ComicTradition | None:
    if not valor:
        return None
    try:
        return ComicTradition(valor)
    except ValueError:
        raise _ErrorOpds(400, "Tradición no válida", "La tradición pedida no existe en ZascArr.") from None


def _validar_uuid(valor: str | None) -> UUID | None:
    if not valor:
        return None
    try:
        return UUID(valor)
    except (ValueError, TypeError):
        raise _ErrorOpds(400, "Editorial no válida", "El identificador de editorial no es válido.") from None


class _ErrorOpds(Exception):  # noqa: N818
    def __init__(self, status: int, titulo: str, detalle: str):
        super().__init__(detalle)
        self.status = status
        self.titulo = titulo
        self.detalle = detalle


def _respuesta_error(exc: _ErrorOpds) -> Response:
    return _xml_error(exc.status, exc.titulo, exc.detalle)


@router.get("", response_class=Response)
async def raiz(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    actualizado = await _max_actualizado(db)
    feed = _feed(str(request.url), "ZascArr — catálogo", actualizado)
    _entrada_nav(feed, ident="urn:zascarr:opds:series", titulo="Todas las series",
                 href="/opds/series", actualizado=actualizado,
                 resumen="Navega por todas las series del catálogo.")
    _entrada_nav(feed, ident="urn:zascarr:opds:tradiciones", titulo="Por tradición",
                 href="/opds/tradiciones", actualizado=actualizado)
    _entrada_nav(feed, ident="urn:zascarr:opds:editoriales", titulo="Por editorial",
                 href="/opds/editoriales", actualizado=actualizado)
    return _respuesta(request, ET.tostring(feed, encoding="utf-8", xml_declaration=True), actualizado)


@router.get("/series", response_class=Response)
async def series(request: Request, page: str = "1", tradition: str | None = None,
                 publisher_id: str | None = None, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        tradicion = _validar_tradicion(tradition)
        editorial = _validar_uuid(publisher_id)
        try:
            numero_pagina = max(1, int(page))
        except (TypeError, ValueError):
            numero_pagina = 1
        filtros: dict[str, str] = {}
        if tradicion:
            filtros["tradition"] = tradicion.value
        if editorial:
            filtros["publisher_id"] = str(editorial)
        actualizado = await _max_actualizado(
            db,
            *([Series.tradition == tradicion] if tradicion else []),
            *([Series.publisher_id == editorial] if editorial else []),
        )
        servicio = SeriesService(db)
        items, total, pagina_servida = await servicio.list_series_paginado(
            page=numero_pagina, page_size=_PAGE_SIZE,
            tradition=tradicion.value if tradicion else None,
            publisher_id=editorial, orden="titulo")
        if pagina_servida != numero_pagina:
            items = []
        pages = math.ceil(total / _PAGE_SIZE) if total else 0
        autores = await _autores_de_series(db, [s.id for s in items])
        feed = _feed(str(request.url), "Series", actualizado)
        _pagina_links(feed, "/opds/series", numero_pagina, pages, filtros)
        for serie in items:
            _entrada_serie(feed, serie, autores.get(serie.id, []))
        cuerpo = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
        return _respuesta(request, cuerpo, actualizado, extra=f"{total}|{numero_pagina}")
    except _ErrorOpds as exc:
        return _respuesta_error(exc)


async def _autores_de_series(db: AsyncSession, ids: list[UUID]) -> dict[UUID, list[str]]:
    if not ids:
        return {}
    resultado = await db.execute(
        select(Issue.series_id, Creator.name)
        .join(IssueCreator, IssueCreator.issue_id == Issue.id)
        .join(Creator, Creator.id == IssueCreator.creator_id)
        .where(Issue.series_id.in_(ids), IssueCreator.role == CreatorRole.WRITER)
        .distinct()
        .order_by(Issue.series_id, Creator.name)
    )
    salida: dict[UUID, list[str]] = {}
    for serie_id, nombre in resultado.all():
        salida.setdefault(serie_id, []).append(nombre)
    return salida


@router.get("/series/{serie_id}", response_class=Response)
async def serie_detalle(serie_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        uuid = UUID(serie_id)
    except (ValueError, TypeError):
        return _xml_error(404, "Serie no encontrada", "Esa serie no está en el catálogo.")
    serie = await db.get(Series, uuid)
    if serie is None:
        return _xml_error(404, "Serie no encontrada", "Esa serie no está en el catálogo.")
    issues = list((await db.execute(
        select(Issue).where(Issue.series_id == uuid)
        .order_by(Issue.sort_order.asc().nulls_last(), Issue.issue_number.asc().nulls_last())
    )).scalars().all())
    actualizado = serie.updated_at
    for issue in issues:
        if issue.updated_at and (actualizado is None or issue.updated_at > actualizado):
            actualizado = issue.updated_at
    feed = _feed(str(request.url), serie.title, actualizado, up="/opds/series")
    for issue in issues:
        _entrada_issue(feed, issue, serie)
    cuerpo = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
    return _respuesta(request, cuerpo, actualizado, extra=str(uuid))


@router.get("/tradiciones", response_class=Response)
async def tradiciones(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    filas = (await db.execute(
        select(Series.tradition).distinct().order_by(Series.tradition)
    )).scalars().all()
    actualizado = await _max_actualizado(db)
    feed = _feed(str(request.url), "Tradiciones", actualizado)
    for valor in filas:
        tradicion = valor if isinstance(valor, ComicTradition) else ComicTradition(valor)
        _entrada_nav(feed, ident=f"urn:zascarr:opds:tradicion:{tradicion.value}",
                     titulo=_TRADICIONES.get(tradicion, tradicion.value),
                     href=f"/opds/series?{urlencode({'tradition': tradicion.value})}",
                     actualizado=actualizado)
    return _respuesta(request, ET.tostring(feed, encoding="utf-8", xml_declaration=True), actualizado)


@router.get("/editoriales", response_class=Response)
async def editoriales(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    filas = (await db.execute(
        select(Publisher.id, Publisher.name)
        .join(Series, Series.publisher_id == Publisher.id)
        .distinct()
        .order_by(Publisher.name)
    )).all()
    actualizado = await _max_actualizado(db)
    feed = _feed(str(request.url), "Editoriales", actualizado)
    for publisher_id, nombre in filas:
        _entrada_nav(feed, ident=f"urn:zascarr:opds:editorial:{publisher_id}",
                     titulo=nombre,
                     href=f"/opds/series?{urlencode({'publisher_id': str(publisher_id)})}",
                     actualizado=actualizado)
    return _respuesta(request, ET.tostring(feed, encoding="utf-8", xml_declaration=True), actualizado)
