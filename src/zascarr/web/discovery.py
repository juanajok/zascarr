# ruff: noqa: E501
"""
Router de descubrimiento de series (C0) — /ui/descubrir.

Busca en fuentes externas (Comic Vine/AniList/Tebeosfera, vía DiscoveryService) y da de alta la `Series` local que
Wishlist y el matcher necesitan para funcionar. Dar de alta una serie es catalogar metadatos, no descargar nada: a
diferencia de `/ui/wishlist/anadir`, estas rutas NO llevan `require_legal_acknowledgment`.

La creación es en DOS PASOS y delega en `AltaDeSerie` (I2 de #114; ADR 0008 §2, ADR 0010 P-1): **Revisar** (vista previa,
no escribe nada) y **Crear** (confirmación con el token de la vista previa). El navegador nunca aporta los datos de la serie:
reenvía el token que el servidor firmó al buscar y la tradición que elige la persona.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.alta_serie import (
    AltaDeSerie,
    AltaError,
    DatosManuales,
    NoSePuedeDeshacerError,
    ParecidasNuevasError,
)
from zascarr.services.descubrimiento_grupo import GrupoNoEncontradoError
from zascarr.services.descubrimiento_libre import firmar_resultados
from zascarr.services.discovery import DiscoveryService
from zascarr.services.tokens_revision import (
    MAX_CLAVE_GRUPO,
    MAX_TITULO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_CANDIDATA_SIN_GRUPO,
    grupo_de_un_token,
)
from zascarr.utils.cover import cached_image_response, fetch_and_cache_cover
from zascarr.web.componentes import tipo_aviso
from zascarr.web.descubrir_texto import (
    enumerar,
    etiqueta_fuente,
    fuentes_que_se_consultan,
    resumir,
    texto_plano,
)
from zascarr.web.library import _TRADICION_LABEL
from zascarr.web.routes import crear_templates

templates = crear_templates()
# U14: la fuente se muestra con su nombre y la descripción como texto (nunca el HTML de la fuente).
templates.env.filters["etiqueta_fuente"] = etiqueta_fuente
templates.env.filters["texto_plano"] = texto_plano

router = APIRouter(prefix="/ui/descubrir", tags=["ui"])

# Portadas de RESULTADOS de búsqueda (aún sin Series creada, así que no
# hay /ui/series/{id}/portada al que apuntar). Este proxy es la única
# forma segura de mostrarlas sin hotlinkear el navegador directo al CDN
# externo (regla permanente, §3.1.4) — pero a diferencia del cascade de
# portadas ya existente, la URL la elige la petición, no la BD, así que
# hace falta una lista blanca de host por fuente: sin ella, este
# endpoint sería un proxy abierto de imágenes arbitrarias (SSRF real,
# no teórico — cualquiera podría usarlo para sondear red interna).
# Comic Vine: dominio de imagen no verificado en vivo todavía (sin
# COMICVINE_API_KEY a mano en esta sesión) — se permiten los dos
# dominios documentados/conocidos de CBS Interactive; revisar si
# alguna vez se ve un 400 real con una key configurada.
_ALLOWED_COVER_HOSTS: dict[MetadataSource, tuple[str, ...]] = {
    MetadataSource.COMIC_VINE: ("comicvine.gamespot.com", "cbsistatic.com"),
    MetadataSource.ANILIST: ("anilist.co",),
    MetadataSource.TEBEOSFERA: ("tebeosfera.com",),
    MetadataSource.GCD: ("comics.org",),
}


def _cover_host_allowed(url: str, source: MetadataSource) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    return any(
        host == dominio or host.endswith(f".{dominio}")
        for dominio in _ALLOWED_COVER_HOSTS.get(source, ())
    )


@router.get("", response_class=HTMLResponse)
async def index(request: Request, q: str = Query(default="", max_length=200)) -> HTMLResponse:
    """`?q=` (V4: «Buscar una serie» del Inicio) prellena la caja y lanza la búsqueda al cargar."""
    fuentes = fuentes_que_se_consultan(get_settings())
    return templates.TemplateResponse(request, "descubrir.html", {
        "q": q.strip(), "clave": None, "titulo": "", "anio": "", "error": None, "tradicion_elegida": "",
        "tradiciones": _tradiciones(), "pista": None,
        "buscando_en": enumerar(fuentes) if fuentes else None})


def _tradiciones() -> list[tuple[str, str]]:
    return [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]


def _fragmento_sin_clave(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_alta_error.html",
        {"texto": "ZascArr no tiene clave para firmar lo que ves: reinícialo e inténtalo de nuevo."})


@router.get("/buscar", response_class=HTMLResponse)
async def buscar(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    busqueda = await DiscoveryService(db).search_detallada(q)
    secreto = get_settings().secret_key
    if not secreto:
        return _fragmento_sin_clave(request)
    firmados, omitidas = firmar_resultados(busqueda.resultados, secreto)
    # U14: la web explica el estado de CADA fuente ella misma (qué no respondió y que las demás sí); los avisos
    # de texto del servicio ya no se pintan (llevaban `.env` y nombres de variables).
    resumen = resumir(busqueda.fuentes, len(firmados))
    avisos = list(resumen.avisos)
    if omitidas:
        avisos.append(f"Se han omitido {omitidas} resultado(s) cuyo título o identificador no se puede guardar.")
    return templates.TemplateResponse(
        request, "_resultados_descubrir.html",
        {"resultados": firmados, "avisos": avisos, "tradiciones": _tradiciones(),
         "hay_resultados": bool(busqueda.resultados), "anuncio": resumen.anuncio,
         "clase_aviso": tipo_aviso("amber").clase,       # el aspecto de «aviso», SIN su `role` (ver la plantilla)
         "consultadas": enumerar(resumen.consultadas), "hay_consultadas": bool(resumen.consultadas)},
    )


@router.get("/portada")
async def portada(request: Request, url: str, source: MetadataSource):
    """Portada de un candidato de búsqueda, antes de que exista una
    Series — bug real, reportado ("¿puede tener algo así como el
    pantallazo [de Sonarr]?"). Caché en disco por hash de la URL
    (content-addressed: no hay series_id todavía), mismas cabeceras
    de caché que el resto de portadas de la app."""
    if not _cover_host_allowed(url, source):
        raise HTTPException(status_code=400, detail="Host de portada no permitido")

    clave = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    cache_path = get_settings().covers_cache_path / "descubrir" / f"{clave}.jpg"

    if not await asyncio.to_thread(cache_path.exists):
        if not await fetch_and_cache_cover(url, cache_path):
            raise HTTPException(status_code=404, detail="Sin portada disponible")

    data = await asyncio.to_thread(cache_path.read_bytes)
    return cached_image_response(request, data, "image/jpeg", clave)


def _servicio(db: AsyncSession) -> AltaDeSerie | None:
    secreto = get_settings().secret_key
    return AltaDeSerie(db, secret=secreto) if secreto else None


#: Los `AltaError` cuyo mensaje YA está escrito para la persona. Cualquier otro código (o una excepción base) no muestra su
#: texto —podría ser un identificador, un UUID o un detalle interno—: sale el mensaje de reserva.
_CODIGOS_CON_MENSAJE_PROPIO = frozenset({
    "token_invalido", "datos_invalidos", "decision_invalida", "demasiadas_parecidas", "la_serie_ya_no_existe",
    "identificador_cambiado", "alta_deshecha", "alta_serie_ausente",
})
_MENSAJES_POR_CODIGO = {
    "serie_no_encontrada": "La serie ya no está en tu biblioteca; no hay nada que deshacer.",
}
_MENSAJE_DE_RESERVA = "No se ha podido completar la operación. Vuelve a buscar el título e inténtalo de nuevo."


def _texto_de(exc: AltaError) -> str:
    codigo = getattr(exc, "codigo", "")
    if codigo in _MENSAJES_POR_CODIGO:
        return _MENSAJES_POR_CODIGO[codigo]
    return str(exc) if codigo in _CODIGOS_CON_MENSAJE_PROPIO else _MENSAJE_DE_RESERVA


def _error(request: Request, texto: str, **extra) -> HTMLResponse:
    """Los fallos recuperables se pintan DENTRO de la tarjeta (con 200): htmx no sustituye una respuesta 4xx."""
    return templates.TemplateResponse(request, "_alta_error.html", {"texto": texto, **extra})


def _campos_de_origen(candidata: str | None, titulo: str | None, anio: int | None, clave: str | None) -> list[tuple[str, str]]:
    """Lo que hay que reenviar para poder REVISAR DE NUEVO: la candidata firmada, o los datos escritos a mano (y el grupo
    del que se parte, si lo hay). La persona los escribió; lo que ejecuta la confirmación sigue siendo solo el token."""
    if candidata:
        return [("candidata", candidata), *([("clave", clave)] if clave else [])]
    campos = [("titulo", titulo or ""), ("anio", "" if anio is None else str(anio))]
    if clave:
        campos.append(("clave", clave))
    return campos


def _anio_de(texto: str | None) -> int | None:
    """El año escrito a mano: vacío = sin año. Lo demás tiene que ser un número; el rango lo valida el servicio."""
    t = (texto or "").strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        raise ValueError("El año debe ser un número (por ejemplo, 1987) o dejarse en blanco.") from None


def _plantilla_formulario_a_mano(*, clave: str | None, titulo: str, anio: str, error: str | None,
                                 tradicion: str = "") -> tuple[str, dict]:
    """El formulario de alta a mano, con el motivo del error y lo que la persona había escrito (nada se pierde)."""
    return "_alta_manual_form.html", {
        "clave": clave, "titulo": titulo, "anio": anio, "error": error, "tradicion_elegida": tradicion,
        "tradiciones": _tradiciones(), "pista": None}


async def preparar_vista_previa(
    request: Request, db: AsyncSession, *, candidata: str | None, titulo: str | None, anio: str | None,
    clave: str | None, tradition: ComicTradition, decision: Literal["reutilizar", "crear_igualmente"] | None = None,
    serie_id: UUID | None = None,
) -> tuple[str, dict]:
    """La vista previa del alta como (plantilla, contexto), SIN escribir nada. La comparten `POST /revisar` y el GET gemelo
    del asistente de carpeta (U19, que la reconstruye al volver): una sola definición. Una candidata puede venir con la
    carpeta (`clave`, la del asistente: el token de la candidata está firmado para ella) o sin ella (Descubrir libre)."""
    servicio = _servicio(db)
    a_mano = not candidata
    if servicio is None:
        return "_fragmento_sin_clave", {}
    elegida = tradition
    anio_valor: int | None = None
    if a_mano:
        try:
            anio_valor = _anio_de(anio)
        except ValueError as exc:
            return _plantilla_formulario_a_mano(clave=clave, titulo=titulo or "", anio=anio or "", error=str(exc),
                                                tradicion=elegida.value)
    try:
        if a_mano:
            datos = DatosManuales(titulo=titulo or "", anio=anio_valor)
            if clave:
                vista = await servicio.previsualizar(clave, tradicion=elegida, manual=datos, decision=decision,
                                                     serie_id=serie_id)
            else:
                vista = await servicio.previsualizar_sin_grupo(
                    tradicion=elegida, manual=datos, decision=decision, serie_id=serie_id)
        elif clave:
            vista = await servicio.previsualizar(clave, tradicion=elegida, candidata=candidata, decision=decision,
                                                 serie_id=serie_id)
        else:
            vista = await servicio.previsualizar_sin_grupo(
                tradicion=elegida, candidata=candidata, decision=decision, serie_id=serie_id)
    except GrupoNoEncontradoError:
        return "_alta_error.html", {"texto": "Esa carpeta ya no tiene registros pendientes: la serie se puede crear desde Descubrir."}
    except AltaError as exc:
        if a_mano and getattr(exc, "codigo", "") in ("datos_invalidos", "demasiadas_parecidas"):
            return _plantilla_formulario_a_mano(clave=clave, titulo=titulo or "", anio=anio or "",
                                                error=_texto_de(exc), tradicion=elegida.value)
        return "_alta_error.html", {"texto": _texto_de(exc)}
    return "_alta_vista_previa.html", {
        "vista": vista, "campos_origen": _campos_de_origen(candidata, vista.titulo, vista.anio, clave),
        "tradicion": elegida.value, "tradicion_etiqueta": _TRADICION_LABEL[elegida], "tradiciones": _tradiciones(),
        "clave": clave,
    }


@router.post("/revisar", response_class=HTMLResponse)
async def revisar(
    request: Request,
    candidata: str | None = Form(default=None, max_length=MAX_TOKEN_CANDIDATA_SIN_GRUPO),
    titulo: str | None = Form(default=None, max_length=MAX_TITULO),
    anio: str | None = Form(default=None, max_length=100),
    clave: str | None = Form(default=None, max_length=MAX_CLAVE_GRUPO),
    tradition: ComicTradition = Form(...),
    decision: Literal["reutilizar", "crear_igualmente"] | None = Form(default=None),
    serie_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Paso 1: la vista previa de lo que pasaría. NO escribe nada. La tradición la elige la persona (sin valor por defecto).

    Dos orígenes, ninguno consulta fuentes en este paso: una candidata firmada al buscar (Descubrir, o el asistente de una
    carpeta, con su `clave`) o los datos a mano —título, año opcional y tradición—, con o sin la carpeta de la que se parte
    (`clave`). #189, U19."""
    plantilla, contexto = await preparar_vista_previa(
        request, db, candidata=candidata, titulo=titulo, anio=anio, clave=clave, tradition=tradition,
        decision=decision, serie_id=serie_id)
    if plantilla == "_fragmento_sin_clave":
        return _fragmento_sin_clave(request)
    return templates.TemplateResponse(request, plantilla, contexto)


MENSAJE_RESULTADO_DESCONOCIDO = (
    "No se sabe si la serie llegó a crearse. No la des por hecha ni por fallida: comprueba el resultado. Repetirlo es "
    "seguro: si ya se creó verás la misma serie y no se duplica.")


@router.post("/crear", response_class=HTMLResponse)
async def crear(
    request: Request,
    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_ALTA),
    candidata: str | None = Form(default=None, max_length=MAX_TOKEN_CANDIDATA_SIN_GRUPO),
    titulo: str | None = Form(default=None, max_length=MAX_TITULO),
    anio: str | None = Form(default=None, max_length=100),
    clave: str | None = Form(default=None, max_length=MAX_CLAVE_GRUPO),
    tradition: ComicTradition | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Paso 2: ejecuta EXACTAMENTE lo que enseñó la vista previa (solo el token). Ya no acepta los datos de la serie.

    Escribe como mucho UNA fila de `series` y su comprobante; no vincula ni toca archivos. Si el alta parte de una carpeta
    (el grupo va DENTRO del token firmado), el resultado ofrece pasar a la revisión de archivos (#119), que tiene su propia
    confirmación; sin carpeta dice que no hay nada que vincular."""
    servicio = _servicio(db)
    if servicio is None:
        return _fragmento_sin_clave(request)
    try:
        anio_valor = _anio_de(anio)
    except ValueError:
        anio_valor = None
    origen = _campos_de_origen(candidata, titulo, anio_valor, clave)
    try:
        resultado = await servicio.confirmar(token)
    except ParecidasNuevasError as exc:
        return _error(request, "Han aparecido series parecidas desde la vista previa: revísalas y decide de nuevo.",
                      parecidas=exc.nuevas, campos_origen=origen,
                      tradicion=tradition.value if tradition else None, tradiciones=_tradiciones(), clave=clave)
    except AltaError as exc:
        return _error(request, _texto_de(exc))
    except Exception:
        # Un fallo que no es del contrato (la conexión, p. ej.): no se sabe si se llegó a crear. El mismo token es
        # idempotente (comprobante en `alta_operaciones`): repetirlo devuelve la serie o la crea UNA vez.
        return templates.TemplateResponse(request, "_alta_error.html", {
            "texto": MENSAJE_RESULTADO_DESCONOCIDO, "reintentar_token": token, "campos_origen": origen,
            "tradicion": tradition.value if tradition else None, "clave": clave})
    grupo = grupo_de_un_token(token, get_settings().secret_key)
    return templates.TemplateResponse(request, "_alta_resultado.html", {"r": resultado, "grupo": grupo})


_MOTIVOS_DE_NO_DESHACER = {
    "no_creada_por_esta_operacion": "Esa serie no la creó esta operación, así que no se puede deshacer desde aquí.",
    "tiene_archivos": "La serie ya tiene archivos vinculados, así que no se puede deshacer.",
    "tiene_numeros": "La serie ya tiene números, así que no se puede deshacer.",
    "operacion_viva": "La serie tiene una operación en curso: espera a que termine.",
    "tiene_deseados": "La serie ya tiene deseados o una política de búsqueda, así que no se puede deshacer.",
}


@router.post("/deshacer", response_class=HTMLResponse)
async def deshacer(
    request: Request, series_id: UUID = Form(...), operacion_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Deshace el alta SOLO si la creó esa operación y nada depende de la serie (lo comprueba el servicio)."""
    servicio = _servicio(db)
    if servicio is None:
        return _fragmento_sin_clave(request)
    try:
        hecho = await servicio.deshacer(series_id, operacion_id)
    except NoSePuedeDeshacerError as exc:
        return _error(request, _MOTIVOS_DE_NO_DESHACER.get(exc.motivo, "No se puede deshacer."))
    except AltaError as exc:
        return _error(request, _texto_de(exc))
    return templates.TemplateResponse(request, "_alta_deshecha.html", {"hecho": hecho})
