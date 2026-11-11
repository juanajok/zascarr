"""
Biblioteca (C1) — /ui/biblioteca. Primera pantalla de navegación real:
hasta ahora solo existían pantallas de un único propósito (pendientes,
wishlist) y una ficha de serie (C2) alcanzable solo por URL directa.

BL-IT01 (#283, 2026-11-05): los filtros dejan de reiniciarse al elegir un
personaje o una saga. El estado de la vista es **la URL**: `q`, tradición,
editorial, personaje, saga y página. Cada filtro activo se pinta como un
chip con su propia retirada; «Limpiar todos» es una acción aparte y
explícita. El recuento y los chips viven dentro del fragmento que se
intercambia, y el servidor empuja a la URL de la PÁGINA completa (no a la
del fragmento) tras cada intercambio.

La lógica de consulta sigue en `SeriesService` (CLAUDE.md §3.1); aquí solo
se normaliza la entrada, se construyen URLs y se elige qué plantilla se
sirve.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace
from urllib.parse import urlencode
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.coleccion import TIPOS as COLECCION_TIPOS
from zascarr.services.comicinfo import (
    TEXTOS_COMICINFO,
    archivos_para_leer,
    leer_archivos_vinculados,
)
from zascarr.services.etiquetas import (
    ExpresionEtiquetas,
    facetas_etiquetas,
    parse_expresion,
    resolver_etiquetas,
    sugerencias_filtro,
)
from zascarr.services.series import SeriesService
from zascarr.web.iconos import icono
from zascarr.web.retorno import url_de_ficha
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()
templates.env.globals["icono"] = icono

router = APIRouter(prefix="/ui/biblioteca", tags=["ui"])

_PAGE_SIZE = 24

_TRADICION_LABEL = {
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
_TRADICIONES_VALIDAS = {t.value for t in ComicTradition}


def _texto_buscador(valor: str) -> str:
    """Texto libre de un buscador auxiliar: sin controles y acotado a 200.

    Los buscadores de personaje/saga no pasan por `_leer_filtros` (no son
    filtros de la URL canónica), pero sí deben respetar el mismo contrato de
    entrada que el resto de la pantalla (#283, AC-05/AC-07).
    """
    texto = (valor or "").strip()
    texto = "".join(
        caracter for caracter in texto
        if ord(caracter) >= 32 and ord(caracter) != 127
    )
    return texto[:200]


def _etiqueta_tradicion(tradicion) -> str:
    """La etiqueta del filtro también en la tarjeta: antes la tarjeta enseñaba el valor interno
    («franco_belgian», «american») justo debajo de un filtro que ya decía «Franco-belga (BD)»."""
    if not tradicion:
        return ""
    try:
        return _TRADICION_LABEL[ComicTradition(tradicion)]
    except (ValueError, KeyError):
        return str(tradicion)


templates.env.filters["tradicion"] = _etiqueta_tradicion


@dataclass(frozen=True)
class Filtros:
    """Filtros ya normalizados de la biblioteca.

    Los UUID se guardan como texto porque la URL canónica se reconstruye con
    ellos; la conversión a `UUID` ocurre al consultar. Un valor inválido se
    descarta y se explica en `avisos`: nunca debe acabar en un 500 ni en una
    biblioteca vacía silenciosa (#283, criterio 5).
    """

    q: str = ""
    tradition: str = ""
    publisher_id: str = ""
    character_id: str = ""
    story_arc_id: str = ""
    etiquetas: str = ""
    leido: str = ""
    orden: str = "titulo"
    coleccion: str = ""
    page: int = 1
    vista: str = "tarjetas"
    avisos: tuple[str, ...] = ()

    def uuid(self, nombre: str) -> UUID | None:
        """UUID del filtro, o None si está vacío. No lanza: `_leer_filtros` ya validó."""

        valor = getattr(self, nombre)
        return UUID(valor) if valor else None


@dataclass(frozen=True)
class FiltroActivo:
    """Un filtro activo y sus dos URLs: página completa (sin htmx) y fragmento."""

    clave: str
    etiqueta: str
    url_quitar: str
    url_quitar_fragmento: str


def _leer_filtros(
    page: str | int,
    q: str,
    tradition: str,
    publisher_id: str,
    character_id: str,
    story_arc_id: str,
    vista: str = "tarjetas",
    etiquetas: str = "",
    leido: str = "",
    orden: str = "",
    coleccion: str = "",
) -> Filtros:
    """Normaliza y valida la entrada de la URL; nunca lanza por un valor inválido.

    Se conservan los filtros válidos y se explican los descartados. Un
    `page<1` se corrige a 1; una página posterior al final se corrige tras
    conocer el total, en `_contexto`.
    """
    avisos: list[str] = []
    bruto = q or ""
    if any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in bruto):
        bruto = "".join(
            caracter for caracter in bruto
            if ord(caracter) >= 32 and ord(caracter) != 127
        )
        avisos.append("La búsqueda tenía caracteres no válidos; se han quitado.")
    texto = bruto.strip()
    if len(texto) > 200:
        texto = texto[:200]
        avisos.append("La búsqueda era demasiado larga; se han usado los primeros 200 caracteres.")

    tradicion = (tradition or "").strip()
    if tradicion and tradicion not in _TRADICIONES_VALIDAS:
        avisos.append("La tradición de ese filtro no existe; se ha quitado.")
        tradicion = ""

    def _uuid(valor: str, nombre: str) -> str:
        limpio = (valor or "").strip()
        if not limpio:
            return ""
        try:
            UUID(limpio)
        except ValueError:
            avisos.append(f"El filtro de {nombre} no es válido; se ha quitado.")
            return ""
        return limpio

    try:
        pagina = int(page)
    except (TypeError, ValueError):
        pagina = 1
        avisos.append("La página pedida no es válida; se muestra la primera.")
    if pagina < 1:
        pagina = 1
        avisos.append("La página pedida no existe; se muestra la primera.")

    vista_limpia = (vista or "").strip().lower()
    if vista_limpia not in ("", "tarjetas", "lista"):
        avisos.append("La presentación pedida no existe; se muestran tarjetas.")
        vista_limpia = "tarjetas"
    expresion = parse_expresion(etiquetas)
    avisos.extend(expresion.avisos)
    texto_etiquetas = " ".join(
        ["-" + t for t in expresion.negativas] + list(expresion.positivas)
    )
    leido = (leido or "").strip().lower()
    if leido not in ("", "si", "no", "leyendo"):
        avisos.append("El filtro de lectura no es válido; se ha quitado.")
        leido = ""
    orden = (orden or "").strip().lower()
    if orden not in ("titulo", "titulo_desc", "anio_desc", "anio_asc", "reciente"):
        orden = "titulo"
    coleccion = (coleccion or "").strip().lower()
    if coleccion and coleccion not in COLECCION_TIPOS:
        avisos.append("El filtro de estado de colección no es válido; se ha quitado.")
        coleccion = ""
    return Filtros(
        q=texto,
        tradition=tradicion,
        publisher_id=_uuid(publisher_id, "editorial"),
        character_id=_uuid(character_id, "personaje"),
        story_arc_id=_uuid(story_arc_id, "saga"),
        etiquetas=texto_etiquetas,
        leido=leido,
        orden=orden,
        coleccion=coleccion,
        page=pagina,
        vista="lista" if vista_limpia == "lista" else "tarjetas",
        avisos=tuple(avisos),
    )


def _qs(filtros: Filtros, *, page: int, omitir: str | None = None) -> str:
    """Query string canónica: valores vacíos fuera, `page` SIEMPRE presente.

    `page=1` se escribe aunque sea la primera: así la URL canónica, el
    `HX-Push-Url` y la que abre un marcador son la misma cadena.
    """
    valores = {
        "q": filtros.q,
        "tradition": filtros.tradition,
        "publisher_id": filtros.publisher_id,
        "character_id": filtros.character_id,
        "story_arc_id": filtros.story_arc_id,
        "etiquetas": filtros.etiquetas,
        "leido": filtros.leido,
        "orden": "" if filtros.orden == "titulo" else filtros.orden,
        "coleccion": filtros.coleccion,
        "vista": "lista" if filtros.vista == "lista" else "",
    }
    if omitir:
        valores[omitir] = ""
    valores["page"] = str(page)
    return urlencode({clave: valor for clave, valor in valores.items() if valor})


def _con_query(base: str, filtros: Filtros, *, page: int, omitir: str | None = None) -> str:
    return f"{base}?{_qs(filtros, page=page, omitir=omitir)}"


def _url_pagina(filtros: Filtros, *, page: int, omitir: str | None = None) -> str:
    return _con_query("/ui/biblioteca", filtros, page=page, omitir=omitir)


def _url_fragmento(filtros: Filtros, *, page: int, omitir: str | None = None) -> str:
    return _con_query("/ui/biblioteca/resultados", filtros, page=page, omitir=omitir)


def _filtros_activos(filtros: Filtros, nombres: dict[str, str | None]) -> list[FiltroActivo]:
    """Chips visibles: qué filtra, con nombre legible y su retirada individual."""
    activos: list[FiltroActivo] = []

    def _anadir(clave: str, etiqueta: str) -> None:
        activos.append(FiltroActivo(
            clave=clave,
            etiqueta=etiqueta,
            url_quitar=_url_pagina(filtros, page=1, omitir=clave),
            url_quitar_fragmento=(
                _url_fragmento(filtros, page=1, omitir=clave) + f"&quitar={clave}"
            ),
        ))

    if filtros.q:
        _anadir("q", f"Búsqueda: «{filtros.q}»")
    if filtros.tradition:
        _anadir("tradition", f"Tradición: {_TRADICION_LABEL[ComicTradition(filtros.tradition)]}")
    if filtros.publisher_id:
        _anadir("publisher_id", f"Editorial: {nombres.get('publisher') or 'desconocida'}")
    if filtros.character_id:
        _anadir("character_id", f"Personaje: {nombres.get('character') or 'desconocido'}")
    if filtros.story_arc_id:
        _anadir("story_arc_id", f"Saga: {nombres.get('story_arc') or 'desconocida'}")
    if filtros.leido:
        _anadir("leido", {"si": "Leídos", "no": "Sin leer", "leyendo": "Leyendo"}[filtros.leido])
    if filtros.coleccion:
        _anadir("coleccion", {
            "completa": "Completas",
            "faltan": "Te faltan números",
            "no_calculable": "No se puede calcular",
            "no_completar": "No la vas a completar",
        }[filtros.coleccion])
    return activos


def _expresion_con(filtros: Filtros, token: str) -> str:
    """Añade o cambia el signo de un token, conservando el resto."""
    partes = filtros.etiquetas.split()
    nombre = token.lstrip("-")
    partes = [p for p in partes if p.lstrip("-") != nombre]
    partes.append(token)
    return " ".join(partes)


def _url_con_etiqueta(filtros: Filtros, token: str) -> str:
    return _url_pagina(replace(filtros, etiquetas=_expresion_con(filtros, token)), page=1)


def _url_fragmento_con_etiqueta(filtros: Filtros, token: str) -> str:
    return _url_fragmento(replace(filtros, etiquetas=_expresion_con(filtros, token)), page=1)


def _texto_recuento_etiquetas(total: int, activas: list[dict]) -> str | None:
    """Frase exacta de AC-06 cuando hay etiquetas; None si no hay."""
    positivas = [a["nombre"] for a in activas if not a["negativa"]]
    negativas = [a["nombre"] for a in activas if a["negativa"]]
    if not positivas and not negativas:
        return None
    base = "1 serie" if total == 1 else f"{total} series"
    if positivas:
        if len(positivas) == 1:
            base += f" con {positivas[0]}"
        elif len(positivas) == 2:
            base += f" con {positivas[0]} y {positivas[1]}"
        else:
            base += " con " + ", ".join(positivas[:-1]) + f" y {positivas[-1]}"
    if negativas:
        base += ". No se muestran las de " + ", ".join(negativas)
    return base + "."


def _texto_recuento(total: int, con_filtros: bool) -> str:
    if total == 0:
        return (
            "Ninguna serie coincide con estos filtros."
            if con_filtros
            else "Tu biblioteca todavía no tiene series."
        )
    if total == 1:
        return "1 serie coincide con estos filtros." if con_filtros else "1 serie catalogada."
    serie = "series"
    if con_filtros:
        return f"{total} {serie} coinciden con estos filtros."
    return f"{total} {serie} catalogadas."


async def _contexto(
    db: AsyncSession, filtros: Filtros, publisher_conocido: str | None = None,
) -> dict:
    """Consulta la página y prepara TODO lo que pinta el fragmento.

    `publisher_conocido`: la página ya trae la lista de editoriales; pasar el
    nombre evita un SELECT extra por el chip (BL-IT01, AC-08: ≤5 por página).
    """
    service = SeriesService(db)
    nombres: dict[str, str | None] = {}
    if publisher_conocido is not None:
        nombres["publisher"] = publisher_conocido
    avisos = list(filtros.avisos)
    total = 0
    items = []
    pagina = filtros.page
    error = False
    etiquetas_activas: list[dict] = []
    facetas: list[dict] = []
    expresion: ExpresionEtiquetas = parse_expresion(filtros.etiquetas)
    positivas: tuple[str, ...] = ()
    negativas: tuple[str, ...] = ()

    try:
        resueltas = await resolver_etiquetas(
            db, list(expresion.positivas) + list(expresion.negativas))
        for normalizado in list(expresion.positivas) + list(expresion.negativas):
            if normalizado not in resueltas:
                avisos.append(
                    f"No conocemos la etiqueta «{normalizado}». Búscala en la lista de etiquetas."
                )
        positivas = tuple(n for n in expresion.positivas if n in resueltas)
        negativas = tuple(n for n in expresion.negativas if n in resueltas)
        for normalizado in list(expresion.positivas) + list(expresion.negativas):
            if normalizado in resueltas:
                negativa = normalizado in expresion.negativas
                sin = " ".join(
                    p for p in filtros.etiquetas.split()
                    if p.lstrip("-") != normalizado
                )
                sin_filtros = replace(filtros, etiquetas=sin)
                etiquetas_activas.append({
                    "nombre": resueltas[normalizado].name,
                    "negativa": negativa,
                    "url_quitar": _url_pagina(sin_filtros, page=1),
                    "url_quitar_fragmento": (
                        _url_fragmento(sin_filtros, page=1) + "&quitar=etiquetas"),
                })
        items, total, pagina = await service.list_series_paginado(
            page=pagina,
            page_size=_PAGE_SIZE,
            tradition=filtros.tradition or None,
            search=filtros.q or None,
            publisher_id=filtros.uuid("publisher_id"),
            character_id=filtros.uuid("character_id"),
            story_arc_id=filtros.uuid("story_arc_id"),
            etiquetas_positivas=positivas,
            etiquetas_negativas=negativas,
            leido=filtros.leido or None,
            orden=filtros.orden,
            coleccion=filtros.coleccion or None,
        )
        if pagina != filtros.page and total:
            avisos.append("La página pedida no existe; se muestra la última.")
        if not error and (positivas or negativas):
            facetas = [
                {
                    "nombre": tag.name,
                    "total": cantidad,
                    "url_anadir": _url_con_etiqueta(filtros, tag.name),
                    "url_excluir": _url_con_etiqueta(filtros, "-" + tag.name),
                }
                for tag, cantidad in await facetas_etiquetas(db, positivas)
            ]
        if any((filtros.publisher_id, filtros.character_id, filtros.story_arc_id)):
            try:
                nombres.update(await service.nombres_de_filtros(
                    publisher_id=None if publisher_conocido is not None
                    else filtros.uuid("publisher_id"),
                    character_id=filtros.uuid("character_id"),
                    story_arc_id=filtros.uuid("story_arc_id"),
                ))
            except SQLAlchemyError as exc:
                # Los resultados ya están; un fallo al leer solo los nombres no
                # debe borrarlos. El chip sale sin nombre, pero se puede quitar.
                logger.warning("biblioteca.nombres_filtros_fallidos", error=type(exc).__name__)
                with contextlib.suppress(Exception):
                    await db.rollback()
                avisos.append(
                    "No se pudieron leer los nombres de los filtros; se muestran sin nombre."
                )
    except SQLAlchemyError as exc:
        # Solo la clase del error: nunca valores del coleccionista (CLAUDE.md §5.4).
        logger.warning("biblioteca.consulta_fallida", error=type(exc).__name__)
        with contextlib.suppress(Exception):
            await db.rollback()
        error = True
        items = []
        total = 0
        pagina = 1

    paginas = (total + _PAGE_SIZE - 1) // _PAGE_SIZE if total else 0
    recuento_lectura_texto = None
    if filtros.leido:
        # Denominador y numerador REALES con el resto de filtros, no la página actual.
        base = dict(
            page=1, page_size=1, tradition=filtros.tradition or None,
            search=filtros.q or None, publisher_id=filtros.uuid("publisher_id"),
            character_id=filtros.uuid("character_id"), story_arc_id=filtros.uuid("story_arc_id"),
            etiquetas_positivas=positivas,
            etiquetas_negativas=negativas, con_issues=True,
            coleccion=filtros.coleccion or None)
        try:
            total_sin = (await service.list_series_paginado(**base))[1]
            if filtros.leido == "leyendo":
                con = (await service.list_series_paginado(**base, leido="leyendo"))[1]
                recuento_lectura_texto = f"{con} de {total_sin} series con algún número en lectura."
            elif filtros.leido == "no":
                con = (await service.list_series_paginado(**base, leido="si"))[1]
                recuento_lectura_texto = (
                    f"{total_sin - con} de {total_sin} series sin ningún número leído.")
            else:
                con = (await service.list_series_paginado(**base, leido="si"))[1]
                recuento_lectura_texto = f"{con} de {total_sin} series con algún número leído."
        except SQLAlchemyError:
            recuento_lectura_texto = None
    filtros_finales = Filtros(
        q=filtros.q,
        tradition=filtros.tradition,
        publisher_id=filtros.publisher_id,
        character_id=filtros.character_id,
        story_arc_id=filtros.story_arc_id,
        etiquetas=filtros.etiquetas,
        leido=filtros.leido,
        orden=filtros.orden,
        coleccion=filtros.coleccion,
        page=pagina,
        vista=filtros.vista,
        avisos=tuple(avisos),
    )
    activos = _filtros_activos(filtros_finales, nombres)
    num_filtros = sum(bool(v) for v in (
        filtros_finales.q, filtros_finales.tradition, filtros_finales.publisher_id,
        filtros_finales.character_id, filtros_finales.story_arc_id,
        filtros_finales.leido, filtros_finales.coleccion)) + len(etiquetas_activas)
    recuento = (_texto_recuento_etiquetas(total, etiquetas_activas)
                or _texto_recuento(total, bool(activos) or bool(etiquetas_activas)))
    if error:
        contador_corto = "—"
        contador_largo = "No se pudo cargar el contador."
    else:
        contador_corto = f"{total} serie" if total == 1 else f"{total} series"
        contador_largo = recuento
        if recuento_lectura_texto:
            contador_largo = f"{contador_largo} {recuento_lectura_texto}"
    url_canonica = _url_pagina(filtros_finales, page=pagina)
    return {
        "items": items,
        "total": total,
        "page": pagina,
        "pages": paginas,
        "error": error,
        "avisos": avisos,
        "filtros": filtros_finales,
        "tradiciones": [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition],
        "ordenes": (
            ("titulo", "A-Z"), ("titulo_desc", "Z-A"),
            ("anio_desc", "Recientes"), ("anio_asc", "Antiguas"),
            ("reciente", "Añadidas"),
        ),
        "vista": filtros_finales.vista,
        "filtros_activos": activos,
        "etiquetas_activas": etiquetas_activas,
        "facetas": facetas,
        "hay_filtros": bool(activos) or bool(etiquetas_activas),
        "coleccion": filtros.coleccion,
        "recuento": recuento,
        "num_filtros": num_filtros,
        "contador_corto": contador_corto,
        "contador_largo": contador_largo,
        "url_canonica": url_canonica,
        "url_serie": lambda series_id: url_de_ficha(series_id, url_canonica),
        "url_pagina": lambda p: _url_pagina(filtros_finales, page=p),
        "url_fragmento": lambda p: _url_fragmento(filtros_finales, page=p),
        "recuento_lectura": recuento_lectura_texto,
        "url_reintento": url_canonica,
        "url_reintento_fragmento": _url_fragmento(filtros_finales, page=pagina),
        "url_vista_tarjetas": _url_pagina(replace(filtros_finales, vista="tarjetas"), page=pagina),
        "url_vista_lista": _url_pagina(replace(filtros_finales, vista="lista"), page=pagina),
        "url_vista_tarjetas_fragmento": _url_fragmento(
            replace(filtros_finales, vista="tarjetas"), page=pagina),
        "url_vista_lista_fragmento": _url_fragmento(
            replace(filtros_finales, vista="lista"), page=pagina),
        "url_limpiar": _url_pagina(replace(
            filtros_finales, q="", tradition="", publisher_id="", character_id="",
            story_arc_id="", etiquetas="", leido="", coleccion=""), page=1),
        "url_limpiar_fragmento": _url_fragmento(
            replace(filtros_finales, q="", tradition="", publisher_id="", character_id="",
                    story_arc_id="", etiquetas="", leido="", coleccion=""), page=1)
            + "&quitar=todos",
    }


async def _respuesta_fragmento(
        request: Request, ctx: dict, db: AsyncSession | None = None) -> Response:
    """Fragmento HTMX: la URL que se empuja es siempre la de la PÁGINA completa.

    `HX-Push-Url` evita que recargar o marcar deje HTML sin layout (riesgo alto
    del benchmark BL-IT01). `no-store` evita mezclar filtros con el botón Atrás.
    """
    ctx["es_fragmento"] = True
    if request.headers.get("HX-Request") == "true" and db is not None:
        try:
            ctx["publishers"] = await SeriesService(db).list_publishers_with_series()
        except Exception:  # noqa: BLE001 — el panel ya tiene su OOB mínimo
            ctx["publishers"] = []
    respuesta = templates.TemplateResponse(request, "_rejilla_biblioteca.html", ctx)
    respuesta.headers["HX-Push-Url"] = ctx["url_canonica"]
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _respuesta_auxiliar(request: Request, plantilla: str, ctx: dict) -> Response:
    """Parcial de los buscadores de personaje/saga: sin caché, como el resto."""
    respuesta = templates.TemplateResponse(request, plantilla, ctx)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/etiquetas/sugerir", response_class=HTMLResponse)
async def sugerir_etiquetas(
    request: Request, etiquetas: str = "", q: str = "", tradition: str = "",
    publisher_id: str = "", character_id: str = "", story_arc_id: str = "",
    vista: str = "", coleccion: str = "", db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filtros = _leer_filtros(
        1, q, tradition, publisher_id, character_id, story_arc_id, vista, etiquetas,
        coleccion=coleccion)
    tokens = etiquetas.strip().split()
    prefijo = tokens[-1].lstrip("-") if tokens else ""
    sin_prefijo = replace(filtros, etiquetas=" ".join(tokens[:-1]))
    sugerencias = []
    if len(prefijo) >= 2:
        sugerencias = await sugerencias_filtro(db, prefijo)
    aplicadas = set(parse_expresion(" ".join(tokens[:-1])).positivas) | set(
        parse_expresion(" ".join(tokens[:-1])).negativas)
    datos = [
        {"nombre": tag.name, "total": total,
         "url_anadir": _url_con_etiqueta(sin_prefijo, tag.name),
         "url_excluir": _url_con_etiqueta(sin_prefijo, "-" + tag.name)}
        for tag, total in sugerencias
        if tag.name_norm not in aplicadas
    ]
    respuesta = templates.TemplateResponse(
        request, "_sugerencias_etiquetas.html",
        {"sugerencias": datos},
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/comicinfo", response_class=HTMLResponse)
async def comicinfo_accion(request: Request, offset: int = 0,
                           db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    cbz, cbr = await archivos_para_leer(db)
    respuesta = templates.TemplateResponse(
        request, "comicinfo_accion.html",
        {"textos": TEXTOS_COMICINFO, "cbz": cbz, "cbr": cbr,
         "offset": max(0, offset), "resultado": None})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/comicinfo", response_class=HTMLResponse)
async def comicinfo_ejecutar(request: Request, offset: int = Form(default=0),
                             db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    resultado = await leer_archivos_vinculados(db, offset=max(0, offset))
    respuesta = templates.TemplateResponse(
        request, "comicinfo_accion.html",
        {"textos": TEXTOS_COMICINFO, "cbz": resultado.total, "cbr": resultado.cbr,
         "resultado": resultado})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("", response_class=HTMLResponse)
async def index(
    request: Request, page: str = "1", tradition: str = "", publisher_id: str = "",
    character_id: str = "", story_arc_id: str = "", q: str = "",
    vista: str = "", etiquetas: str = "", leido: str = "", orden: str = "",
    coleccion: str = "", db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filtros = _leer_filtros(
        page, q, tradition, publisher_id, character_id, story_arc_id, vista, etiquetas,
        leido, orden, coleccion)
    publishers: list = []
    editoriales_error = False
    try:
        publishers = await SeriesService(db).list_publishers_with_series()
    except SQLAlchemyError as exc:
        logger.warning("biblioteca.editoriales_fallidas", error=type(exc).__name__)
        editoriales_error = True
    publisher_conocido = None
    if filtros.publisher_id:
        publisher_conocido = next(
            (p.name for p in publishers if str(p.id) == filtros.publisher_id), ""
        )
    ctx = await _contexto(db, filtros, publisher_conocido)
    if editoriales_error and not ctx["error"]:
        ctx["avisos"].append("No se pudieron cargar las editoriales; puedes seguir filtrando.")
    ctx.update({
        "publishers": publishers,
        "tradiciones": [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition],
    })
    respuesta = templates.TemplateResponse(request, "biblioteca.html", ctx)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/resultados", response_class=HTMLResponse)
async def resultados(
    request: Request, page: str = "1", tradition: str = "", publisher_id: str = "",
    character_id: str = "", story_arc_id: str = "", q: str = "",
    vista: str = "", etiquetas: str = "", leido: str = "", orden: str = "",
    coleccion: str = "", db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filtros = _leer_filtros(
        page, q, tradition, publisher_id, character_id, story_arc_id, vista, etiquetas,
        leido, orden, coleccion)
    return await _respuesta_fragmento(request, await _contexto(db, filtros), db)


def _enlace_con_filtro(filtros: Filtros, clave: str, valor: str) -> str:
    """URL de página completa que añade/reemplaza `clave` y conserva el resto."""
    valores = {
        "q": filtros.q,
        "tradition": filtros.tradition,
        "publisher_id": filtros.publisher_id,
        "character_id": filtros.character_id,
        "story_arc_id": filtros.story_arc_id,
        "etiquetas": filtros.etiquetas,
        "leido": filtros.leido,
        "orden": "" if filtros.orden == "titulo" else filtros.orden,
        "coleccion": filtros.coleccion,
        "vista": "lista" if filtros.vista == "lista" else "",
        clave: valor,
        "page": "1",
    }
    return "/ui/biblioteca?" + urlencode({k: v for k, v in valores.items() if v})


async def _buscar(filtros: Filtros, clave: str, encontrados: list) -> list[tuple[str, str]]:
    """Convierte los modelos del servicio en `(nombre, URL)`; la plantilla no decide URLs."""
    return [
        (nombre, _enlace_con_filtro(filtros, clave, str(objeto.id)))
        for objeto, nombre in encontrados
    ]


@router.get("/buscar-personaje", response_class=HTMLResponse)
async def buscar_personaje(
    request: Request, personaje: str = "", q: str = "", tradition: str = "",
    publisher_id: str = "", character_id: str = "", story_arc_id: str = "",
    vista: str = "", etiquetas: str = "", coleccion: str = "",
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    texto = _texto_buscador(personaje)
    if not texto and q:
        # Compatibilidad con el contrato anterior (`?q=` era el texto del buscador).
        texto, q = _texto_buscador(q), ""
    filtros = _leer_filtros(
        1, q, tradition, publisher_id, character_id, story_arc_id, vista, etiquetas,
        coleccion=coleccion)
    service = SeriesService(db)
    encontrados: list = []
    try:
        if texto:
            encontrados = [(c, c.name) for c in await service.search_characters(texto)]
    except SQLAlchemyError as exc:
        logger.warning("biblioteca.busqueda_personaje_fallida", error=type(exc).__name__)
    return _respuesta_auxiliar(
        request,
        "_resultados_personaje.html",
        {"resultados": await _buscar(filtros, "character_id", encontrados), "texto": texto},
    )


@router.get("/buscar-saga", response_class=HTMLResponse)
async def buscar_saga(
    request: Request, saga: str = "", q: str = "", tradition: str = "",
    publisher_id: str = "", character_id: str = "", story_arc_id: str = "",
    vista: str = "", etiquetas: str = "", coleccion: str = "",
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    texto = _texto_buscador(saga)
    if not texto and q:
        texto, q = _texto_buscador(q), ""
    filtros = _leer_filtros(
        1, q, tradition, publisher_id, character_id, story_arc_id, vista, etiquetas,
        coleccion=coleccion)
    service = SeriesService(db)
    encontrados: list = []
    try:
        if texto:
            encontrados = [(s, s.title) for s in await service.search_story_arcs(texto)]
    except SQLAlchemyError as exc:
        logger.warning("biblioteca.busqueda_saga_fallida", error=type(exc).__name__)
    return _respuesta_auxiliar(
        request,
        "_resultados_saga.html",
        {"resultados": await _buscar(filtros, "story_arc_id", encontrados), "texto": texto},
    )
